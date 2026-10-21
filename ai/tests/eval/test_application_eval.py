"""Application Agent 실제 모델 평가. LLM_EVAL=true일 때만 돈다: `LLM_EVAL=true uv run pytest tests/eval -v -s`.

지원자는 저장소 루트 scripts/demo/applicants.json의 가상 인물이고, NCS 평가 조건은 로컬 DB에서 읽는다
(먼저 `uv run python scripts/ncs_load.py`). 자격요건 통과 · 점수 보류 · 못 채운 자격요건 표시가
지원자마다 기대값과 맞는지 보고 정확도를 출력한다. 점수 숫자는 모델마다 달라 기대값으로 두지 않는다.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import pytest

from hiremate_ai.agents.analysis.application.graph import ReviewInput, run_review
from hiremate_ai.agents.analysis.application.ncs import ncs_units
from hiremate_ai.agents.analysis.application.service import preference_tasks
from hiremate_ai.agents.analysis.application.types import RubricPreference, ScreeningRubric
from hiremate_ai.config import settings
from hiremate_ai.contract import (
    AnalysisStatus,
    ApplicantDetail,
    ApplicantDocument,
    ApplicantInfo,
    DocumentType,
    PostingContent,
)
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm

pytestmark = [
    pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때만 실제 모델로 돈다"),
    pytest.mark.asyncio(loop_scope="module"),
]

DEMO = Path(__file__).resolve().parents[3] / "scripts" / "demo"
RECRUITMENT = UUID("00000000-0000-4000-8000-0000000000aa")
MIN_ACCURACY = 0.8

QUALIFICATIONS = [
    "Java 또는 Kotlin 기반 서버 개발 경력 3년 이상",
    "Spring Boot로 REST API를 개발 · 운영한 경험",
    "MySQL · PostgreSQL 등 RDBMS 스키마 설계와 SQL 작성 경험",
    "Git 기반 코드 리뷰와 협업 경험",
    "JUnit 등으로 테스트 코드를 작성한 경험",
]
# backend application.yml의 hiremate.dummy.screening-rubric과 같다
PREFERRED = [
    RubricPreference(
        text="외부 시스템 연동 인터페이스를 설계한 경험",
        weight=5,
        ncs_unit_code="2001020218_23v6",
        certificates=["정보처리기사"],
    ),
    RubricPreference(
        text="연동 API를 구현하고 오류 · 보안 처리를 적용한 경험",
        weight=4,
        ncs_unit_code="2001020212_23v6",
        certificates=["정보처리기사"],
    ),
    RubricPreference(
        text="요구사항을 분석 · 확인해 개발 범위를 정한 경험",
        weight=3,
        ncs_unit_code="2001020201_23v5",
        certificates=["정보처리기사"],
    ),
    RubricPreference(
        text="빌드 · 배포 자동화(CI/CD)를 구성한 경험", weight=3, ncs_unit_code="2001020214_23v6", certificates=[]
    ),
    RubricPreference(
        text="클래스 · 데이터 모델 등 정적 모델을 설계한 경험",
        weight=2,
        ncs_unit_code="2001020222_23v6",
        certificates=["정보처리기사"],
    ),
]

# 이름 → (자격요건 통과, 점수 보류, 못 채운 자격요건이 있는가). 결과가 규칙으로 분명한 지원자만 둔다
EXPECTED: dict[str, tuple[bool, bool, bool]] = {
    "김도현": (True, False, False),
    "이서윤": (True, False, False),
    "안소율": (True, False, False),
    "양시우": (True, False, True),  # 테스트 코드 근거 없음 → 4/5 통과, ✕
    "이도윤": (False, False, True),  # 신입 · Git 협업 없음 → 60%
    "서민재": (False, False, True),  # 프론트엔드
    "최지우": (False, False, True),  # 데이터 분석
    "윤태오": (False, True, False),  # 글자 없는 PDF → 보류
    "한예린": (True, False, False),
}
# AI 적합도 점수의 순서: (높아야 하는 지원자, 낮아야 하는 지원자)
HIGHER = [("김도현", "안소율"), ("이서윤", "백승호"), ("김도현", "한예린")]


class MemoryCallLog:
    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def record(self, record: CallRecord) -> None:
        self.records.append(record)


def applicant_of(index: int, raw: dict[str, Any]) -> ApplicantDetail:
    documents = [
        ApplicantDocument(
            type=kind, file_id=uuid5(RECRUITMENT, f"{raw['email']}{kind}"), file_name="", size=1, text=raw[key] or ""
        )
        for kind, key in (
            (DocumentType.RESUME, "resume"),
            (DocumentType.COVER_LETTER, "coverLetter"),
            (DocumentType.PORTFOLIO, "portfolio"),
        )
        if key != "portfolio" or raw.get("portfolio")
    ]
    info = ApplicantInfo(
        application_id=uuid5(RECRUITMENT, raw["email"]),
        recruitment_id=RECRUITMENT,
        application_no=index,
        name=raw["name"],
        email=raw["email"],
        career_years=None,
        last_company=None,
        document_score=None,
        passed=False,
        analysis_status=AnalysisStatus.PENDING,
        submitted_at="2026-10-21T00:00:00Z",
    )
    return ApplicantDetail(info=info, phone="010-0000-0000", certificates=raw.get("certificates"), documents=documents)


async def test_demo_applicants_match_expected_outcomes(sample_posting: PostingContent) -> None:
    raws = json.loads((DEMO / "applicants.json").read_text(encoding="utf-8"))
    applicants = {raw["name"]: applicant_of(index, raw) for index, raw in enumerate(raws, start=1)}
    posting = sample_posting.model_copy(
        update={"qualifications": QUALIFICATIONS, "preferred": [preference.text for preference in PREFERRED]}
    )
    rubric = ScreeningRubric(company_id=RECRUITMENT, recruitment_id=RECRUITMENT, hire_count=1, preferred=PREFERRED)
    async with session_factory()() as session:
        units = await ncs_units(session, [preference.ncs_unit_code for preference in PREFERRED])
    if len(units) < len(PREFERRED):
        pytest.skip("NCS 능력단위가 DB에 없다. scripts/ncs_load.py로 먼저 넣는다")
    llm = build_llm(MemoryCallLog())

    names = sorted({*EXPECTED, *(name for pair in HIGHER for name in pair)})
    reviews = {}
    for name in names:
        context = ReviewInput(
            applicant=applicants[name],
            posting=posting,
            tasks=preference_tasks(posting, rubric, units),
            related_certificates=("정보처리기사", "SQLD", "리눅스마스터", "AWS Solutions Architect"),
            input_hash="eval",
            today=date(2026, 10, 21),
        )
        reviews[name] = await run_review(llm, context)

    hits = 0
    for name, expected in EXPECTED.items():
        review = reviews[name]
        shortfalls = [result.shortfall for result in review.qualifications if not result.met]
        actual = (review.passed, review.held, bool(shortfalls))
        hits += actual == expected
        mark = "OK" if actual == expected else "NG"
        fit = {line.key: line.points for line in review.fit}
        print(f"{mark} {name}: 기대 {expected} 결과 {actual} 점수 {review.document_score}")
        print(f"   우대 {round(review.preference_points)}/60 적합도 {fit} 못 채운 자격요건 {shortfalls}")
    for high, low in HIGHER:
        print(f"순서 {high} {reviews[high].document_score} > {low} {reviews[low].document_score}")
        assert (reviews[high].document_score or 0) > (reviews[low].document_score or 0)

    accuracy = hits / len(EXPECTED)
    print(f"정확도 {accuracy:.0%}")
    assert accuracy >= MIN_ACCURACY
