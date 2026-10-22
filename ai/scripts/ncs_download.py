"""공공데이터포털 NCS API에서 고른 직무(세분류)의 능력단위 자료를 받아 src/hiremate_ai/tools/ncs_units.json을 만든다.

사용법 (ai 폴더에서):
    uv run python scripts/ncs_download.py 20010202 20010204

- 인자는 8자리 세분류 코드다. 예: 20010202 응용SW엔지니어링, 20010204 DB엔지니어링
- 인증키는 ai/.env의 NCS_API_KEY다. 공공데이터포털에서 "한국산업인력공단_국가직무능력표준 정보_GW"(15157547)를
  활용신청한 키여야 한다. 키는 출력하지 않는다.
- 받은 자료를 다듬고(앞 번호 떼기, 깨진 가운뎃점 되돌리기, 정렬) tools.ncs의 형식으로 검사한 뒤 저장한다.
- 훈련기준, 출제기준, 직무 직책은 채용에 쓰지 않아 받지 않는다.
- 능력단위의 "중요도 및 활용도" 현장 조사는 API에 없어 NCS 사이트의 보고서 화면에서 받는다
  (자격 요건 · 우대 사항을 쓸 때 능력단위의 우선순위).
  사이트 구조가 바뀌면 받지 못할 수 있다. --no-survey로 빼고 받을 수 있다.
"""

import argparse
import json
import re
import ssl
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from hiremate_ai.config import settings
from hiremate_ai.tools.ncs import DATA_FILE, UNIT_CODE, NcsData

BASE_URL = "https://apis.data.go.kr/B490007/ncsInfo"
SOURCE = "한국산업인력공단_국가직무능력표준 정보_GW (공공데이터포털 15157547, 이용허락범위 제한 없음)"
SITE_URL = "https://www.ncs.go.kr"
SITE_CIPHER = "AES256-GCM-SHA384"
SURVEY_SOURCE = (
    "NCS 국가직무능력표준 사이트(ncs.go.kr) NCS 및 학습모듈검색 › 3. 활용 참고자료 › NCS 중요도 및 활용도 "
    "(2019년 이후 개발 · 개선된 능력단위 현장 조사)"
)
SURVEY_REPORT = "/duf/develop/HTH02020608R_Ptuse_import"
SURVEY_FIELDS = {"중요도": "importance", "난이도": "difficulty", "활용빈도": "frequency"}
SURVEY_ORDER = ["importance", "difficulty", "frequency"]
"""보고서가 능력단위마다 줄을 놓는 순서. 코드는 난이도 줄에 있고, 쪽이 바뀌면 코드를 다시 적는다."""
# 보고서 화면이 값을 넘기기 전에 쓰는 자바스크립트 encodeURI가 그대로 두는 글자
_ENCODE_URI_SAFE = ";,/?:@&=+$-_.!~*'()#"
_TEXT = re.compile(r'<text x="([\d.-]+)"[^>]*y="([\d.-]+)"[^>]*>([^<]*)</text>')
_UID = re.compile(r"'uid':'([^']+)'")
_PAGES = re.compile(r"'count':(\d+)")
_REPORT_DONE = "'endReport':true"
_REPORT_TRIES = 30
_PERCENT = re.compile(r"\d+(?:\.\d+)?")
_WORD_GAP = 45
"""보고서 SVG는 글자를 한 자씩 놓는다. 같은 줄에서 이만큼 가까운 글자는 한 낱말로 묶는다."""
_PERCENT_X = 1000
"""상 · 중 · 하 비율 칸이 시작하는 가로 위치. 이보다 왼쪽의 숫자는 코드 · 이름이다."""
PAGE_SIZE = 1000
KSA_FIELDS = {"수행준거": "criteria", "지식": "knowledge", "기술": "skills", "태도": "attitudes"}
RETIRED = re.compile(r"\(구버전\)|\(오류버전\)|삭제|^공란$")

_NUMBER = re.compile(r"^\s*(\d+)\s*\.\s*")
# 원본의 가운뎃점이 전각 물음표나 반각 가운뎃점으로 들어 있다
_DOTS = str.maketrans({"？": "·", "･": "·"})
_SPACES = re.compile(r"\s+")

Row = dict[str, Any]


class NcsApiError(RuntimeError):
    """API가 오류를 돌려줬을 때. 메시지에 인증키나 요청 주소를 넣지 않는다."""


def main() -> None:
    parser = argparse.ArgumentParser(description="NCS 직무 자료를 받아 ncs_units.json을 만든다")
    parser.add_argument("duties", nargs="+", help="8자리 세분류 코드 (예: 20010202)")
    parser.add_argument("--output", type=Path, default=DATA_FILE, help="저장할 파일")
    parser.add_argument("--no-survey", action="store_true", help="중요도 및 활용도 조사를 받지 않는다")
    args = parser.parse_args()
    if bad := [code for code in args.duties if not re.fullmatch(r"\d{8}", code)]:
        parser.error(f"8자리 세분류 코드가 아니다: {', '.join(bad)}")
    key = settings.ncs_api_key.get_secret_value()
    if not key:
        parser.error("ai/.env에 NCS_API_KEY가 없다")

    with httpx.Client(timeout=60) as client, httpx.Client(timeout=60, verify=site_tls()) as site:
        data = build(Fetcher(client, key), None if args.no_survey else SurveyReport(site), args.duties)
    NcsData.model_validate(data)
    # Windows에서도 줄 끝을 LF로 쓴다
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    units = data["units"]
    criteria = sum(len(element["criteria"]) for unit in units for element in unit["elements"])
    print(f"저장: {args.output} ({args.output.stat().st_size / 1000:.0f}KB)")
    print(
        f"직무 {len(data['duties'])}개, 능력단위 {len(units)}개, 수행준거 {criteria}개, "
        f"중요도 조사 {len(data.get('surveys', {}))}개"
    )


def site_tls() -> ssl.SSLContext:
    """NCS 사이트 연결 설정. 사이트가 TLS 1.2의 RSA 키 교환 암호(SITE_CIPHER)만 받는데 파이썬 기본 목록에 없어 더한다.

    인증서 검사는 그대로 한다. 공공데이터포털 API 연결에는 쓰지 않는다.
    """
    context = ssl.create_default_context()
    context.set_ciphers(":".join([*(cipher["name"] for cipher in context.get_ciphers()), SITE_CIPHER]))
    return context


class Fetcher:
    def __init__(self, client: httpx.Client, key: str) -> None:
        self._client = client
        self._key = key

    def rows(self, operation: str, **params: str) -> list[Row]:
        """목록을 돌려주는 기능을 모든 쪽에 걸쳐 받는다. 결과가 없으면 빈 목록이다."""
        rows: list[Row] = []
        page = 1
        while True:
            body = self._get(operation, page, params)
            data = body.get("data")
            if not data:
                return rows
            rows += data
            if page >= int((body.get("dataInfo") or {}).get("totalPage") or 1):
                return rows
            page += 1

    def object(self, operation: str, **params: str) -> Row:
        """객체 하나를 돌려주는 기능(평가지침)을 받는다."""
        data = self._get(operation, 1, params).get("data")
        return data if isinstance(data, dict) else {}

    def _get(self, operation: str, page: int, params: dict[str, str]) -> Row:
        query: dict[str, str | int] = {
            "serviceKey": self._key,
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
            "returnType": "json",
            **params,
        }
        try:
            response = self._client.get(f"{BASE_URL}/{operation}", params=query)
        except httpx.HTTPError as error:
            raise NcsApiError(f"{operation} {params}: {type(error).__name__}") from None
        if response.status_code != 200:
            raise NcsApiError(f"{operation} {params}: HTTP {response.status_code}")
        body: Row = response.json()
        info = body.get("dataInfo") or {}
        code = str(info.get("code", "000"))
        if code not in ("000", "002"):
            raise NcsApiError(f"{operation} {params}: {info.get('message')}")
        return body


class SurveyReport:
    """NCS 사이트의 "중요도 및 활용도" 보고서. 보고서 화면(ClipReport)이 쪽마다 SVG를 주고, 글자를 한 자씩 놓는다.

    글자를 위치로 낱말로 묶고, 능력단위마다 중요도 · 난이도 · 활용빈도 줄의 상 · 중 · 하 비율을 꺼낸다.
    """

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def units(self, service_no: str) -> dict[str, Row]:
        """직무(직무서비스번호)의 능력단위코드 → {importance, difficulty, frequency}. 조사가 없으면 빈 사전이다."""
        query = json.dumps(
            {"loginUserId": "", "DUTY_SVC_NO": service_no, "NCS_COMPE_UNIT_Y": "", "NCS_COMPE_UNIT_CD": ""},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        viewer = self._post(
            "/clip/viewer.jsp",
            {"file": SURVEY_REPORT, "dbName": "oracle1", "data": quote(query, safe=_ENCODE_URI_SAFE)},
        )
        uid = _found(_UID, viewer, service_no)
        pages = self._pages(uid, service_no)
        lines: list[tuple[int, float, str, list[int]]] = []
        codes: list[tuple[int, float, str]] = []
        for page in range(pages):
            svg = self._post(
                "/clip/Clip.jsp",
                {
                    "ClipID": "R02",
                    "pageNumber": str(page),
                    "uid": uid,
                    "clipUID": uid,
                    "html5": "true",
                    "DPI": "96",
                    "necessaryCheck": "false",
                },
            )
            words = _words(svg)
            percents = [(x, y, text) for x, y, text in words if x > _PERCENT_X and _PERCENT.fullmatch(text)]
            for _, y, text in words:
                if text in SURVEY_FIELDS:
                    values = [round(float(value)) for _, vy, value in sorted(percents) if abs(vy - y) <= 3]
                    lines.append((page, y, SURVEY_FIELDS[text], values))
                elif UNIT_CODE.match(text):
                    codes.append((page, y, text))
        return _group(sorted(lines), [code for _, _, code in sorted(codes)], service_no)

    def _pages(self, uid: str, service_no: str) -> int:
        """보고서 쪽 수. 보고서는 서버에서 따로 만들어져서 다 만들어질 때까지(endReport) 다시 묻는다."""
        for _ in range(_REPORT_TRIES):
            report = self._post("/clip/Clip.jsp", {"ClipID": "R03", "uid": uid, "clipUID": uid, "s_time": "1"})
            if _REPORT_DONE in report:
                return int(_found(_PAGES, report, service_no))
            time.sleep(1)
        raise NcsApiError(f"중요도 및 활용도 보고서가 {_REPORT_TRIES}초 안에 만들어지지 않았다 ({service_no})")

    def _post(self, path: str, form: dict[str, str]) -> str:
        try:
            response = self._client.post(SITE_URL + path, data=form)
        except httpx.HTTPError as error:
            raise NcsApiError(f"중요도 및 활용도 {path}: {type(error).__name__}") from None
        if response.status_code != 200:
            raise NcsApiError(f"중요도 및 활용도 {path}: HTTP {response.status_code}")
        return response.text


def _found(pattern: re.Pattern[str], text: str, service_no: str) -> str:
    if not (match := pattern.search(text)):
        raise NcsApiError(f"중요도 및 활용도 보고서를 열지 못했다 ({service_no}). 사이트 구조가 바뀌었는지 확인한다")
    return match.group(1)


def _words(svg: str) -> list[tuple[float, float, str]]:
    """같은 줄(y)에서 가까운 글자를 낱말로 묶는다."""
    lines: defaultdict[float, list[tuple[float, str]]] = defaultdict(list)
    for x, y, char in _TEXT.findall(svg):
        lines[float(y)].append((float(x), char))
    words = []
    for y, chars in lines.items():
        start, end, text = 0.0, -_WORD_GAP, ""
        for x, char in sorted(chars):
            if text and x - end < _WORD_GAP:
                text += char
            else:
                if text:
                    words.append((start, y, text))
                start, text = x, char
            end = x
        if text:
            words.append((start, y, text))
    return words


def _group(lines: list[tuple[int, float, str, list[int]]], codes: list[str], service_no: str) -> dict[str, Row]:
    """줄을 능력단위마다 세 줄씩 묶어 코드에 붙인다. 쪽이 바뀌어 다시 적힌 코드는 하나로 본다."""
    unique = [code for index, code in enumerate(codes) if index == 0 or code != codes[index - 1]]
    blocks = [lines[i : i + 3] for i in range(0, len(lines), 3)]
    if len(blocks) != len(unique):
        raise NcsApiError(
            f"중요도 및 활용도 보고서를 읽지 못했다 ({service_no}): 능력단위 {len(unique)}개, 줄 묶음 {len(blocks)}개"
        )
    surveys: dict[str, Row] = {}
    for code, block in zip(unique, blocks, strict=True):
        if [field for _, _, field, _ in block] != SURVEY_ORDER or any(len(values) != 3 for *_, values in block):
            raise NcsApiError(f"중요도 및 활용도 보고서의 줄 순서가 다르다 ({service_no}, {code})")
        surveys[code] = {field: values for _, _, field, values in block}
    return surveys


def build(fetch: Fetcher, survey: SurveyReport | None, duty_codes: list[str]) -> Row:
    names = {
        row["ncsLclasCd"] + row["ncsMclasCd"] + row["ncsSclasCd"] + row["ncsSubdCd"]: row
        for row in fetch.rows("ncsCdInfo")
    }
    duties: list[Row] = []
    units: list[Row] = []
    surveys: dict[str, Row] = {}
    for duty_code in duty_codes:
        if duty_code not in names:
            raise NcsApiError(f"NCS 분류에 없는 세분류 코드다: {duty_code}")
        classification = names[duty_code]
        duty = fetch.rows("ncsDutyInfo", dutyCd=duty_code)
        duties.append(
            {
                "code": duty_code,
                "name": clean(classification["ncsSubdCdNm"]),
                "definition": clean(duty[0]["dutyDef"]) if duty else "",
            }
        )
        if survey and duty and (service_no := duty[0].get("dutySvcNo")):
            surveys |= survey.units(service_no)
        ksa = fetch.rows("ncsKsaInfo", dutyCd=duty_code)
        for row in fetch.rows("ncsCompeUnitInfo", dutyCd=duty_code):
            name = strip_number(row["compUnitName"])[1]
            if RETIRED.search(name) or not clean(row.get("compUnitDef") or "") or not UNIT_CODE.match(row["ncsClCd"]):
                continue
            number = row["compUnitCd"]
            evaluation = fetch.object("ncsEvalInfo", dutyCd=duty_code, compUnitCd=number)
            units.append(
                {
                    "code": row["ncsClCd"],
                    "name": name,
                    "level": int(row["compUnitLevel"]),
                    "definition": clean(row["compUnitDef"]),
                    "dutyCode": duty_code,
                    "major": clean(classification["ncsLclasCdNm"]),
                    "middle": clean(classification["ncsMclasCdNm"]),
                    "minor": clean(classification["ncsSclasCdNm"]),
                    "subdivision": clean(classification["ncsSubdCdNm"]),
                    "elements": elements([r for r in ksa if r["compUnitCd"] == number]),
                    "scope": scope(fetch.rows("ncsScopeInfo", dutyCd=duty_code, compUnitCd=number)),
                    "evaluationPoints": numbered(evaluation.get("csdrData") or [], "csdrmtrNo", "defText"),
                    "basicCompetencies": basic_competencies(
                        fetch.rows("ncsjobInfo", dutyCd=duty_code, compUnitCd=number)
                    ),
                }
            )
    codes = sorted(unit["code"] for unit in units)
    return {
        "source": SOURCE,
        **({"surveySource": SURVEY_SOURCE} if survey else {}),
        "retrievedAt": date.today().isoformat(),
        "duties": duties,
        "units": sorted(units, key=lambda unit: unit["code"]),
        # 빠진 능력단위(구버전 등)의 조사는 버린다
        **({"surveys": {code: surveys[code] for code in codes if code in surveys}} if survey else {}),
    }


def elements(rows: list[Row]) -> list[Row]:
    """수행준거 · KSA 줄을 능력단위요소별로 묶는다. 값은 앞 번호 순서로 놓는다 (원본은 1, 10, 2 순서다)."""
    grouped: dict[int, Row] = {}
    for row in rows:
        number = int(row["compUnitFactrNo"])
        name = strip_number(row["compUnitFactrName"])[1]
        element = grouped.setdefault(
            number, {"number": number, "name": name, **{field: [] for field in KSA_FIELDS.values()}}
        )
        if field := KSA_FIELDS.get(row["gbnName"]):
            element[field].append(strip_number(row["gbnVal"]))
    for element in grouped.values():
        for field in KSA_FIELDS.values():
            element[field] = unique(text for _, text in sorted(element[field], key=lambda pair: pair[0]))
    return [grouped[number] for number in sorted(grouped)]


def scope(rows: list[Row]) -> dict[str, list[str]]:
    """적용범위 및 작업상황을 항목(고려사항, 자료 및 관련 서류, 장비 및 도구 등)별로 묶는다."""
    grouped: defaultdict[str, list[Row]] = defaultdict(list)
    for row in rows:
        grouped[clean(row["itemName"])].append(row)
    return {name: numbered(items, "itemNo", "defText") for name, items in grouped.items()}


def basic_competencies(rows: list[Row]) -> list[Row]:
    grouped: dict[str, Row] = {}
    for row in sorted(rows, key=lambda r: (int(r["mainNo"]), int(r["subNo"]))):
        competency = grouped.setdefault(clean(row["mainName"]), {"name": clean(row["mainName"]), "subs": []})
        if (sub := clean(row.get("subName") or "")) and sub not in competency["subs"]:
            competency["subs"].append(sub)
    return list(grouped.values())


def numbered(rows: list[Row], number: str, text: str) -> list[str]:
    return unique(clean(row[text]) for row in sorted(rows, key=lambda r: int(r[number])) if row.get(text))


def strip_number(text: str) -> tuple[int, str]:
    """'11.서버프로그램 구현' → (11, '서버프로그램 구현'). 번호가 없으면 0이다."""
    match = _NUMBER.match(text)
    return (int(match.group(1)), clean(text[match.end() :])) if match else (0, clean(text))


def clean(text: str) -> str:
    return _SPACES.sub(" ", text.translate(_DOTS)).strip()


def unique(texts: Any) -> list[str]:
    return [text for text in dict.fromkeys(texts) if text]


if __name__ == "__main__":
    main()
