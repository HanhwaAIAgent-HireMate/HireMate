# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.28", "fpdf2>=2.8"]
# ///
"""서류 전형 데모 데이터: 더미 공고(자격요건 5 · 우대사항 5)를 게시하고 가상 지원자(applicants.json)를 제출한다.

    uv run scripts/demo/seed.py --email hr@example.com --password <12자 이상>

backend(8080)와 ai(8001)가 떠 있어야 한다. 지원서는 실제 지원 화면과 같은 공개 지원 API로 제출하므로
접수할 때마다 Application Agent가 분석한다. 마지막에 접수를 마감하고 서류 전형 화면 주소를 알려 준다.
우대사항 글은 backend 설정의 더미 평가 기준(hiremate.dummy.screening-rubric)과 같아야 짝이 맞는다.
--fixtures면 서류 평가 데이터셋(fixtures/의 지원자 30명)과 그 공고(자격요건 2 · 우대사항 3)를 쓴다. 평가 기준이
backend fixtures 프로필(application-fixtures.yml)에 있으므로 backend를 SPRING_PROFILES_ACTIVE=fixtures로 띄운다.
지원자는 모두 가상 인물이다. 비밀번호는 코드에 쓰지 않고 인자나 HIREMATE_DEMO_PASSWORD로 받는다.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fpdf import FPDF

HERE = Path(__file__).resolve().parent
# 글꼴을 PDF에 넣을 때 fontTools가 쓰지 않는 표를 버린다는 경고를 남긴다. 결과에는 영향이 없다
logging.getLogger("fontTools").setLevel(logging.ERROR)

POSTING = {
    "title": "응용 소프트웨어 엔지니어 (백엔드)",
    "jobCategory": "백엔드 개발",
    "employmentType": "정규직",
    "career": "경력 3년 이상",
    "location": "서울 중구",
    "intro": "외부 기관 · 파트너와 연동하는 서비스를 설계하고 만드는 백엔드 엔지니어를 찾습니다.",
    "duties": ["외부 시스템 연동 API 설계와 구현", "서비스 요구사항 분석과 개발 범위 정의", "빌드 · 배포 자동화 운영"],
    "qualifications": [
        "Java 또는 Kotlin 기반 서버 개발 경력 3년 이상",
        "Spring Boot로 REST API를 개발 · 운영한 경험",
        "MySQL · PostgreSQL 등 RDBMS 스키마 설계와 SQL 작성 경험",
        "Git 기반 코드 리뷰와 협업 경험",
        "JUnit 등으로 테스트 코드를 작성한 경험",
    ],
    "preferred": [
        "외부 시스템 연동 인터페이스를 설계한 경험",
        "연동 API를 구현하고 오류 · 보안 처리를 적용한 경험",
        "요구사항을 분석 · 확인해 개발 범위를 정한 경험",
        "빌드 · 배포 자동화(CI/CD)를 구성한 경험",
        "클래스 · 데이터 모델 등 정적 모델을 설계한 경험",
    ],
    "benefits": ["유연 근무", "자기계발비 지원"],
    # 공고 작성 화면의 [필수] 표시. 서류 전형 기준선은 이 줄들을 모두 충족했는지로 가른다.
    # 다른 공고가 이 사전을 이어 써도 그 공고 본문에 없는 줄의 표시는 backend가 버린다
    "requiredQualifications": [
        "Java 또는 Kotlin 기반 서버 개발 경력 3년 이상",
        "Spring Boot로 REST API를 개발 · 운영한 경험",
    ],
}
# 서류 평가 데이터셋(fixtures/)의 공고. 자격요건 · 우대사항 글은 application-fixtures.yml의 평가 기준과 같다
FIXTURES_POSTING = {
    **POSTING,
    "title": "백엔드 엔지니어 (금융 서비스 API · 30명 데이터셋)",
    "career": "경력 무관",
    "intro": "결제 · 대출 · 보험 같은 서비스의 API와 외부 연동을 만들고 운영하는 백엔드 엔지니어를 찾습니다.",
    "duties": ["REST API 개발과 운영", "외부 시스템 연동 설계와 구현", "장애 대응과 빌드 · 배포 자동화"],
    "qualifications": ["REST API를 개발하고 운영한 경험", "SQL을 작성하고 DB 성능을 개선한 경험"],
    "preferred": [
        "외부 시스템 연동을 설계하고 구현한 경험",
        "장애 원인을 분석하고 복구한 경험",
        "빌드 · 배포 자동화(CI/CD)를 구성한 경험",
    ],
}

STAGE_PLAN = "전형은 서류, 직무역량 평가, 1차 면접, 최종 면접 순으로 해줘"

FONTS = [
    Path("C:/Windows/Fonts/malgun.ttf"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/Library/Fonts/NanumGothic.ttf"),
]


class Api:
    """세션 쿠키와 CSRF 토큰을 유지하는 클라이언트. 로그인 · 로그아웃 뒤에는 토큰을 다시 받는다."""

    def __init__(self, base_url: str) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=120)
        self._csrf: str | None = None

    def reset_csrf(self) -> None:
        self._csrf = None

    def csrf(self) -> dict[str, str]:
        if self._csrf is None:
            self._csrf = self.http.get("/api/auth/csrf").raise_for_status().json()["token"]
        return {"X-CSRF-TOKEN": self._csrf}

    def post(self, path: str, body: object = None, *, expect: tuple[int, ...] = (200, 201, 204)) -> httpx.Response:
        response = self.http.post(path, json=body, headers=self.csrf())
        return _check(response, expect)

    def put(self, path: str, body: object) -> httpx.Response:
        return _check(self.http.put(path, json=body, headers=self.csrf()), (200,))

    def get(self, path: str) -> httpx.Response:
        return _check(self.http.get(path), (200,))


def _check(response: httpx.Response, expect: tuple[int, ...]) -> httpx.Response:
    if response.status_code not in expect:
        sys.exit(f"{response.request.method} {response.request.url.path} → {response.status_code}: {response.text}")
    return response


def pdf(text: str, font: Path) -> bytes:
    """글을 한 쪽 이상의 PDF로 만든다. 글이 비면 글자 없는 PDF다 (스캔본처럼 글자를 읽지 못하는 서류)."""
    document = FPDF()
    document.add_page()
    if text:
        document.add_font("body", fname=str(font))
        document.set_font("body", size=11)
        for line in text.split("\n"):
            document.multi_cell(0, 7, line or " ", new_x="LMARGIN", new_y="NEXT")
    return bytes(document.output())


def login(api: Api, email: str, password: str) -> None:
    signup = api.post(
        "/api/auth/signup",
        {"companyName": "하이메이트 데모", "name": "데모 담당자", "email": email, "password": password},
        expect=(201, 409),
    )
    if signup.status_code == 409:
        print(f"이미 가입한 이메일이라 로그인만 한다: {email}")
    api.post("/api/auth/login", {"email": email, "password": password})
    api.reset_csrf()


def publish(api: Api, posting: dict[str, object]) -> tuple[str, str]:
    draft = api.post("/api/recruitments").json()
    recruitment_id, posting_id = draft["recruitmentId"], draft["postingId"]
    base = f"/api/recruitments/{recruitment_id}/posting"
    api.put(base, posting)
    # 서류 전형을 확정해도 채용이 끝나지 않고 다음 전형으로 넘어가게 전형을 넷으로 둔다 (Posting Agent 수정안).
    # 수정안이 공고 문장을 바꾸면 평가 기준과 짝이 어긋나므로 적용한 뒤 공고 본문을 다시 넣는다
    api.post(f"{base}/ai-requests", {"message": STAGE_PLAN})
    api.post(f"{base}/suggestion/apply")
    api.put(base, posting)
    now = datetime.now(UTC)
    api.post(
        f"{base}/publish",
        {"openAt": (now - timedelta(hours=1)).isoformat(), "closeAt": (now + timedelta(days=7)).isoformat()},
    )
    return recruitment_id, posting_id


def apply(base_url: str, posting_id: str, applicant: dict[str, str | None], font: Path) -> None:
    """지원자 한 명을 공개 지원 API로 제출한다. 지원자마다 새 세션을 쓴다."""
    api = Api(base_url)
    files = {
        "resume": (f"{applicant['name']}_이력서.pdf", pdf(applicant["resume"] or "", font), "application/pdf"),
        "coverLetter": (
            f"{applicant['name']}_자기소개서.pdf",
            pdf(applicant["coverLetter"] or "", font),
            "application/pdf",
        ),
    }
    if applicant.get("portfolio"):
        files["portfolio"] = (
            f"{applicant['name']}_포트폴리오.pdf",
            pdf(applicant["portfolio"] or "", font),
            "application/pdf",
        )
    data = {
        "name": applicant["name"],
        "email": applicant["email"],
        "phone": "010-0000-0000",
        "consentPrivacy": "true",
        "consentAi": "true",
    }
    if applicant.get("certificates"):
        data["certificates"] = applicant["certificates"]
    response = api.http.post(
        f"/api/public/postings/{posting_id}/applications", data=data, files=files, headers=api.csrf()
    )
    _check(response, (201,))


def wait_for_analysis(api: Api, stage_id: str, total: int, minutes: float) -> None:
    deadline = time.monotonic() + minutes * 60
    while True:
        items = api.get(f"/api/stages/{stage_id}/candidates?size=200").json()["items"]
        pending = sum(item["analysisStatus"] == "PENDING" for item in items)
        failed = sum(item["analysisStatus"] == "FAILED" for item in items)
        print(f"\r분석 중 {pending}명 · 실패 {failed}명 · 전체 {total}명", end="", flush=True)
        if pending == 0:
            print()
            return
        if time.monotonic() > deadline:
            print("\n기다리는 시간이 지났다. 화면에서 남은 분석을 확인한다.")
            return
        time.sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser(description="서류 전형 데모 데이터를 넣는다")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--app-url", default="http://localhost:5173", help="화면 주소 (frontend)")
    parser.add_argument("--email", default="demo-hr@example.com")
    parser.add_argument("--password", default=os.environ.get("HIREMATE_DEMO_PASSWORD"))
    parser.add_argument("--font", type=Path, help="한글 TTF 글꼴. 비우면 맑은 고딕 · 나눔고딕을 찾는다")
    parser.add_argument("--wait-minutes", type=float, default=40)
    parser.add_argument("--fixtures", action="store_true", help="서류 평가 데이터셋(fixtures/)을 넣는다")
    args = parser.parse_args()
    if not args.password:
        sys.exit("--password 또는 HIREMATE_DEMO_PASSWORD로 HR 비밀번호(12자 이상)를 준다")
    font = args.font or next((path for path in FONTS if path.exists()), None)
    if font is None:
        sys.exit("한글 글꼴을 찾지 못했다. --font로 TTF 파일을 준다")

    folder = HERE / "fixtures" if args.fixtures else HERE
    applicants = json.loads((folder / "applicants.json").read_text(encoding="utf-8"))
    api = Api(args.base_url)
    login(api, args.email, args.password)
    recruitment_id, posting_id = publish(api, FIXTURES_POSTING if args.fixtures else POSTING)
    print(f"공고를 게시했다: {recruitment_id}")
    for index, applicant in enumerate(applicants, start=1):
        apply(args.base_url, posting_id, applicant, font)
        print(f"\r지원서 제출 {index}/{len(applicants)}", end="", flush=True)
    print()
    closed = api.post(f"/api/recruitments/{recruitment_id}/posting/close").json()
    stage_id = closed["stages"][0]["id"]
    wait_for_analysis(api, stage_id, len(applicants), args.wait_minutes)
    print(f"서류 전형 화면: {args.app_url}/hr/recruitments/{recruitment_id}/stages/{stage_id}")


if __name__ == "__main__":
    main()
