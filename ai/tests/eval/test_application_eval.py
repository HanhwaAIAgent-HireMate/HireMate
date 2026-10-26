"""Application Agent 실제 모델 평가. LLM_EVAL=true일 때만 돈다: `LLM_EVAL=true uv run pytest tests/eval -v -s`.

지원자는 저장소 루트 scripts/demo/applicants.json의 가상 인물이고, 평가 기준은 backend application.yml의 더미와 같다.
자격요건 75% 통과 판단 · 점수 보류 · 미충족 표시가 지원자마다 기대값과 맞는지 보고 정확도를 출력한다.
점수 숫자는 모델마다 달라 순서만 확인한다.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import pytest

from hiremate_ai.agents.analysis.application.graph import ReviewInput, run_review
from hiremate_ai.agents.analysis.application.service import match_criteria
from hiremate_ai.agents.analysis.application.types import (
    VERDICT_LABEL,
    Criterion,
    EvaluationRules,
    ScreeningRubric,
)
from hiremate_ai.config import settings
from hiremate_ai.contract import (
    AnalysisStatus,
    ApplicantDetail,
    ApplicantDocument,
    ApplicantInfo,
    CriterionCategory,
    CriterionType,
    DocumentType,
    PostingContent,
    QualificationStatus,
)
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm

pytestmark = [
    pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때만 실제 모델로 돈다"),
    pytest.mark.asyncio(loop_scope="module"),
]

DEMO = Path(__file__).resolve().parents[3] / "scripts" / "demo"
RECRUITMENT = UUID("00000000-0000-4000-8000-0000000000aa")
MIN_ACCURACY = 0.8
C, S, X = CriterionType.CONDITION, CriterionType.SINGLE, CriterionType.COMPOSITE

# backend application.yml의 hiremate.dummy.screening-rubric과 같다: (id, 문장, 유형, 충족, 부분 충족, 미충족)
ROWS: list[tuple[str, str, CriterionType, str, str | None, str]] = [
    (
        "Q-01",
        "Java 또는 Kotlin 기반 서버 개발 경력 3년 이상",
        C,
        "Java · Kotlin으로 서버를 개발한 재직 경력이 3년 이상이다 (기간은 경력표로 계산한다).",
        None,
        "Java · Kotlin 서버 개발 재직 경력이 3년에 못 미치거나 서류에서 확인되지 않는다.",
    ),
    (
        "Q-02",
        "Spring Boot로 REST API를 개발 · 운영한 경험",
        S,
        "Spring Boot로 REST API를 본인이 개발하거나 운영했다.",
        None,
        "Spring Boot로 REST API를 개발 · 운영한 기록이 서류에서 확인되지 않는다.",
    ),
    (
        "Q-03",
        "MySQL · PostgreSQL 등 RDBMS 스키마 설계와 SQL 작성 경험",
        X,
        "RDBMS 스키마(테이블 · 인덱스)를 본인이 설계하고 SQL을 작성했다.",
        "SQL 작성이나 쿼리 튜닝은 했지만 스키마 설계는 드러나지 않는다 (또는 그 반대).",
        "RDBMS를 다룬 기록이 서류에서 확인되지 않는다.",
    ),
    (
        "Q-04",
        "Git 기반 코드 리뷰와 협업 경험",
        X,
        "Git으로 협업하며 코드 리뷰(PR 리뷰 등)를 주고받았다.",
        "Git으로 협업한 기록은 있지만 코드 리뷰는 드러나지 않는다.",
        "Git 협업 기록이 서류에서 확인되지 않는다.",
    ),
    (
        "Q-05",
        "JUnit 등으로 테스트 코드를 작성한 경험",
        S,
        "JUnit 등 테스트 도구로 테스트 코드를 본인이 작성했다.",
        None,
        "테스트 코드를 작성한 기록이 서류에서 확인되지 않는다.",
    ),
    (
        "P-01",
        "외부 시스템 연동 인터페이스를 설계한 경험",
        X,
        "외부 · 내부 시스템 간 연동 인터페이스를 본인이 설계했다. 연동 대상과 송수신 데이터를 정하고, "
        "송수신 방식(API · 메시지 명세)과 오류 시 처리 방안까지 명세한 근거가 있다.",
        "인터페이스 설계의 일부만 본인이 했다. 연동 대상 · 송수신 데이터를 정하거나 API 명세를 썼지만 "
        "오류 시 처리 방안까지는 드러나지 않는다.",
        "연동 기능을 쓰거나 구현만 했고 설계한 기록이 서류에서 확인되지 않는다.",
    ),
    (
        "P-02",
        "연동 API를 구현하고 오류 · 보안 처리를 적용한 경험",
        X,
        "외부 · 내부 모듈과의 연동 기능을 본인이 구현했고, 실패 시 예외 처리(재시도 · 타임아웃 · 보상 처리 등)와 "
        "보안 처리(인증 · 암호화 · 서명 검증 등)를 모두 적용했다.",
        "연동 기능을 본인이 구현했고 예외 처리와 보안 처리 가운데 하나만 드러난다.",
        "연동 기능을 구현한 기록이 없거나, 구현했어도 예외 · 보안 처리가 서류에서 확인되지 않는다.",
    ),
    (
        "P-03",
        "요구사항을 분석 · 확인해 개발 범위를 정한 경험",
        X,
        "현행 시스템이나 업무 요구사항을 본인이 분석 · 검토해 개발 범위나 목표 시스템을 정했다 "
        "(예: 요구사항 정의서 작성, 범위 협의를 이끎).",
        "요구사항 분석 · 검토에 참여해 의견을 냈지만 개발 범위를 정한 데까지는 드러나지 않는다.",
        "정해진 요구사항대로 구현한 기록만 있다.",
    ),
    (
        "P-04",
        "빌드 · 배포 자동화(CI/CD)를 구성한 경험",
        X,
        "빌드 · 배포 파이프라인(도구 · 스크립트 · 환경 설정)을 본인이 구성해 운영 환경에 배포했고, "
        "배포 후 확인이나 실패 시 이전 버전으로 되돌리는 절차까지 있다.",
        "빌드 스크립트나 파이프라인 일부(테스트 · 빌드 단계 등)만 본인이 구성했고, "
        "운영 배포나 복원 절차는 드러나지 않는다.",
        "이미 구성된 파이프라인을 쓴 기록만 있거나 서류에서 확인되지 않는다.",
    ),
    (
        "P-05",
        "클래스 · 데이터 모델 등 정적 모델을 설계한 경험",
        X,
        "클래스 · 엔티티 · 데이터 모델(ERD 등)을 본인이 상세 설계하고 설계서나 다이어그램으로 남겼다.",
        "엔티티 · 테이블 설계를 본인이 했지만 설계서나 다이어그램 같은 결과물은 드러나지 않는다.",
        "정적 모델을 설계한 기록이 서류에서 확인되지 않는다.",
    ),
]
CRITERIA = [
    Criterion(
        criterion_id=criterion_id,
        category=CriterionCategory.QUALIFICATION if criterion_id.startswith("Q") else CriterionCategory.PREFERENCE,
        text=text,
        important=False,
        criterion_type=kind,
        evaluation_rules=EvaluationRules(met=met, partial=partial, unmet=unmet),
    )
    for criterion_id, text, kind, met, partial, unmet in ROWS
]

P, F, U = QualificationStatus.PASSED, QualificationStatus.FAILED, QualificationStatus.UNDETERMINED
# 이름 → (75% 통과 판단, 미충족 · 확인 필요 표시가 있는가). 결과가 규칙으로 분명한 지원자만 둔다.
# 양시우(테스트 코드 근거 없음 + RDBMS 쿼리 튜닝만)는 RDBMS가 충족 · 부분 충족 경계라 70 ~ 80%를 오가서 뺐다.
# 점수 보류는 근거가 애매한 정도에 따라 생기는 결과라 기대값에 두지 않고, 이유를 출력해 사람이 본다.
EXPECTED: dict[str, tuple[QualificationStatus, bool]] = {
    "김도현": (P, False),
    "이서윤": (P, False),
    "이도윤": (F, True),  # 신입 · Git 협업 없음
    "서민재": (F, True),  # 프론트엔드
    "최지우": (F, True),  # 데이터 분석
    "윤태오": (U, False),  # 글자 없는 PDF
    "한예린": (P, False),
}
# 총점의 순서: (높아야 하는 지원자, 낮아야 하는 지원자)
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
    categories = {CriterionCategory.QUALIFICATION: "qualifications", CriterionCategory.PREFERENCE: "preferred"}
    posting = sample_posting.model_copy(
        update={field: [c.text for c in CRITERIA if c.category == category] for category, field in categories.items()}
    )
    rubric = ScreeningRubric(
        company_id=RECRUITMENT,
        recruitment_id=RECRUITMENT,
        criteria_version="dummy-2026-10-22",
        hire_count=1,
        criteria=CRITERIA,
    )
    criteria, notes = match_criteria(posting, rubric)
    assert not notes  # 공고 문장과 평가 기준이 모두 짝지어진다
    llm = build_llm(MemoryCallLog())

    names = sorted({*EXPECTED, *(name for pair in HIGHER for name in pair)})
    reviews = {}
    for name in names:
        context = ReviewInput(
            applicant=applicants[name],
            posting=posting,
            criteria=criteria,
            criteria_version=rubric.criteria_version,
            notes=notes,
            input_hash="eval",
            today=date(2026, 10, 21),
        )
        reviews[name] = await run_review(llm, context)

    hits = 0
    for name, expected in EXPECTED.items():
        review = reviews[name]
        shortfalls = [result.shortfall for result in review.qualifications if result.shortfall]
        actual = (review.qualification_status, bool(shortfalls))
        hits += actual == expected
        mark = "OK" if actual == expected else "NG"
        verdicts = " · ".join(f"{r.criterion_id} {VERDICT_LABEL[r.verdict]}" for r in review.criteria)
        print(f"{mark} {name}: 기대 {expected} 결과 {actual}")
        print(
            f"   총점 {review.document_score} (자격 {review.qualification_score} · 우대 {review.preference_score})"
            f" 충족률 {review.qualification_rate} 표시 {shortfalls}"
        )
        print(f"   {verdicts}")
        for note in review.holds:
            print(f"   보류: {note.text}")
    for high, low in HIGHER:
        print(f"순서 {high} {reviews[high].document_score} > {low} {reviews[low].document_score}")
        assert (reviews[high].document_score or 0) > (reviews[low].document_score or 0)

    assert reviews["윤태오"].held  # 글자를 읽지 못한 서류는 반드시 보류다
    accuracy = hits / len(EXPECTED)
    print(f"정확도 {accuracy:.0%}")
    assert accuracy >= MIN_ACCURACY
