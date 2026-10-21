"""공공데이터포털 NCS API에서 고른 직무(세분류)의 능력단위 자료를 받아 src/hiremate_ai/tools/ncs_units.json을 만든다.

사용법 (ai 폴더에서):
    uv run python scripts/ncs_download.py 20010202 20010204

- 인자는 8자리 세분류 코드다. 예: 20010202 응용SW엔지니어링, 20010204 DB엔지니어링
- 인증키는 ai/.env의 NCS_API_KEY다. 공공데이터포털에서 "한국산업인력공단_국가직무능력표준 정보_GW"(15157547)를
  활용신청한 키여야 한다. 키는 출력하지 않는다.
- 받은 자료를 다듬고(앞 번호 떼기, 깨진 가운뎃점 되돌리기, 정렬) tools.ncs의 형식으로 검사한 뒤 저장한다.
- 훈련기준, 출제기준, 직무 직책은 채용에 쓰지 않아 받지 않는다.
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from hiremate_ai.config import settings
from hiremate_ai.tools.ncs import DATA_FILE, UNIT_CODE, NcsData

BASE_URL = "https://apis.data.go.kr/B490007/ncsInfo"
SOURCE = "한국산업인력공단_국가직무능력표준 정보_GW (공공데이터포털 15157547, 이용허락범위 제한 없음)"
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
    args = parser.parse_args()
    if bad := [code for code in args.duties if not re.fullmatch(r"\d{8}", code)]:
        parser.error(f"8자리 세분류 코드가 아니다: {', '.join(bad)}")
    key = settings.ncs_api_key.get_secret_value()
    if not key:
        parser.error("ai/.env에 NCS_API_KEY가 없다")

    with httpx.Client(timeout=60) as client:
        data = build(Fetcher(client, key), args.duties)
    NcsData.model_validate(data)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    units = data["units"]
    criteria = sum(len(element["criteria"]) for unit in units for element in unit["elements"])
    print(f"저장: {args.output} ({args.output.stat().st_size / 1000:.0f}KB)")
    print(f"직무 {len(data['duties'])}개, 능력단위 {len(units)}개, 수행준거 {criteria}개")


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


def build(fetch: Fetcher, duty_codes: list[str]) -> Row:
    names = {
        row["ncsLclasCd"] + row["ncsMclasCd"] + row["ncsSclasCd"] + row["ncsSubdCd"]: row
        for row in fetch.rows("ncsCdInfo")
    }
    duties: list[Row] = []
    units: list[Row] = []
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
    return {
        "source": SOURCE,
        "retrievedAt": date.today().isoformat(),
        "duties": duties,
        "units": sorted(units, key=lambda unit: unit["code"]),
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
