"""Application Agent 테스트가 같이 쓰는 공고 · 평가 기준과 가짜 모델 대본.

모델 호출은 문서별 추출 · 영역별 판정 · 재확인이 동시에 나가므로
FakeLlm에는 호출 내용을 보고 답하는 대본(Script)을 넣는다.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from hiremate_ai.agents.analysis.application.achievements import Ledger
from hiremate_ai.agents.analysis.application.digest import PortfolioDigest, ResumeDigest
from hiremate_ai.agents.analysis.application.extract import (
    ExtractedFacts,
    ExtractedPeriod,
    ExtractionCorrections,
    LetterSummary,
)
from hiremate_ai.agents.analysis.application.job_career import JobCareer, JobFit
from hiremate_ai.agents.analysis.application.judge import CriteriaJudgement, CriterionVerdict
from hiremate_ai.agents.analysis.application.review import ClaimReview, ReviewJudgement
from hiremate_ai.agents.analysis.application.types import Criterion, EvaluationRules, ScreeningRubric
from hiremate_ai.agents.analysis.application.warnings import _Warnings
from hiremate_ai.contract import CriterionCategory, CriterionType, PostingContent
from hiremate_ai.llm.fake import FakeLlm, LlmCall

type ReviewVerdict = Literal["SUPPORTED", "OVERSTATED", "UNSUPPORTED"]
type Level = Literal["MET", "PARTIAL", "NOT_MET", "UNKNOWN"]

TODAY = date(2026, 10, 21)
COMPANY_ID = UUID("2b8e4c1d-6f3a-4e5b-9c7d-0a1b2c3d4e50")
RECRUITMENT_ID = UUID("7a1e2b3c-4d5e-4f60-8a9b-0c1d2e3f4a51")
CRITERIA_VERSION = "test-1"

QUALIFICATIONS = [
    "Java 또는 Kotlin 기반 서버 개발 경력 3년 이상",
    "Spring Boot로 REST API를 개발한 경험",
    "RDBMS 설계와 SQL 작성 경험",
    "Git 기반 협업 경험",
]
PREFERRED = [
    "외부 시스템 연동 인터페이스를 설계한 경험",
    "빌드 · 배포 자동화를 구성한 경험",
    "정보처리기사 자격증 보유",
]


def make_posting(base: PostingContent) -> PostingContent:
    """가상 공고에 이 테스트의 자격요건 4개 · 우대사항 3개를 넣는다."""
    return base.model_copy(update={"qualifications": QUALIFICATIONS, "preferred": PREFERRED})


def _criterion(
    criterion_id: str,
    text: str,
    criterion_type: CriterionType,
    *,
    important: bool = False,
    partial: str | None = None,
    certificates: Sequence[str] = (),
) -> Criterion:
    category = CriterionCategory.QUALIFICATION if criterion_id.startswith("Q") else CriterionCategory.PREFERENCE
    return Criterion(
        criterion_id=criterion_id,
        category=category,
        text=text,
        important=important,
        criterion_type=criterion_type,
        evaluation_rules=EvaluationRules(
            met=f"{text}을 본인이 했다", partial=partial, unmet="서류에서 확인되지 않는다"
        ),
        certificates=list(certificates),
    )


def make_rubric() -> ScreeningRubric:
    """자격요건 4개(Q-01 경력 · 중요), 우대사항 3개(P-01 복합 · 중요, P-02 복합, P-03 자격증)."""
    return ScreeningRubric(
        company_id=COMPANY_ID,
        recruitment_id=RECRUITMENT_ID,
        criteria_version=CRITERIA_VERSION,
        hire_count=1,
        criteria=[
            _criterion("Q-01", QUALIFICATIONS[0], CriterionType.CONDITION, important=True),
            _criterion("Q-02", QUALIFICATIONS[1], CriterionType.SINGLE),
            _criterion("Q-03", QUALIFICATIONS[2], CriterionType.SINGLE),
            _criterion("Q-04", QUALIFICATIONS[3], CriterionType.SINGLE),
            _criterion(
                "P-01", PREFERRED[0], CriterionType.COMPOSITE, important=True, partial="설계의 일부만 본인이 했다"
            ),
            _criterion("P-02", PREFERRED[1], CriterionType.COMPOSITE, partial="빌드 스크립트 등 일부만 구성했다"),
            _criterion("P-03", PREFERRED[2], CriterionType.CONDITION, certificates=["정보처리기사"]),
        ],
    )


def verdict(
    criterion_id: str,
    level: Level,
    *evidence: str,
    role: Literal["SELF", "TEAM", "UNCLEAR"] = "SELF",
    periods: Sequence[int] = (),
    shortfall: str = "",
) -> CriterionVerdict:
    """판정 대본 한 줄. 부분 충족이면 충족 · 미충족 부분을 함께 채운다."""
    partial = level == "PARTIAL"
    return CriterionVerdict(
        criterion_id=criterion_id,
        relevance="관련 업무",
        role=role,
        scope="수행 범위",
        verdict=level,
        reason=f"{criterion_id} {level} 판정",
        satisfied_parts=["설계서 작성"] if partial else [],
        unsatisfied_parts=["오류 처리 명세"] if partial else [],
        unknown_parts=["본인 역할"] if level == "UNKNOWN" else [],
        evidence=list(evidence),
        career_periods=list(periods),
        shortfall=shortfall,
    )


@dataclass
class Script:
    """호출 내용을 보고 답하는 가짜 모델의 대본.

    extract: 문서 본문 일부 → 추출 결과. verdicts: 항목 id → 첫 판정 (없으면 NOT_MET).
    rechecks: (항목 id, 재확인 차수) → 재확인 판정 (없으면 첫 판정을 다시 쓴다).
    reviews: 주장 id → 검토 결과 (없으면 SUPPORTED). omit: 답에서 빠뜨릴 항목 id. summary: 자기소개서 요약.
    warnings: 서류 주의 신호 (없으면 신호 없음). jobs: 회사 → 직무 관련 판단 (없으면 YES).
    ledger: 지원자 단위 성과 장부 (없으면 성과 없음).
    """

    extract: dict[str, ExtractedFacts] = field(default_factory=dict)
    verdicts: dict[str, CriterionVerdict] = field(default_factory=dict)
    rechecks: dict[tuple[str, int], CriterionVerdict] = field(default_factory=dict)
    reviews: dict[str, ReviewVerdict] = field(default_factory=dict)
    omit: set[str] = field(default_factory=set)
    summary: LetterSummary = field(default_factory=LetterSummary)
    resume_digest: ResumeDigest = field(default_factory=ResumeDigest)
    portfolio_digest: PortfolioDigest = field(default_factory=PortfolioDigest)
    ledger: Ledger = field(default_factory=Ledger)
    warnings: _Warnings = field(default_factory=lambda: _Warnings(items=[]))
    jobs: dict[str, str] = field(default_factory=dict)

    def __call__(self, call: LlmCall) -> BaseModel:
        if call.output is ExtractedFacts:
            return next((value for key, value in self.extract.items() if key in call.user), ExtractedFacts())
        if call.output is ExtractionCorrections:
            return ExtractionCorrections()
        if call.output is LetterSummary:
            return self.summary
        if call.output is ResumeDigest:
            return self.resume_digest
        if call.output is PortfolioDigest:
            return self.portfolio_digest
        if call.output is Ledger:
            return self.ledger
        if call.output is _Warnings:
            return self.warnings
        if call.output is JobCareer:
            listed = re.findall(r"^(\d+)\. (.+?) \|", call.user, re.MULTILINE)
            return JobCareer(
                periods=[
                    JobFit(number=int(number), reason="맡은 일", related=self.jobs.get(company, "YES"))
                    for number, company in listed
                ]
            )
        if call.output is CriteriaJudgement:
            ids = re.findall(r"^\[([QP]-\d+)\]", call.user, re.MULTILINE)
            found = re.search(r"([12])차 재확인", call.user)
            round_no = int(found.group(1)) if found else 0
            answers = []
            for criterion_id in [found for found in ids if found not in self.omit]:
                first = self.verdicts.get(criterion_id, verdict(criterion_id, "NOT_MET"))
                answers.append(self.rechecks.get((criterion_id, round_no), first) if round_no else first)
            return CriteriaJudgement(verdicts=answers)
        if call.output is ReviewJudgement:
            ids = re.findall(r"^([QP]-\d+|F\d+|R\d+)\. 주장", call.user, re.MULTILINE)
            return ReviewJudgement(
                reviews=[
                    ClaimReview(id=id, verdict=self.reviews.get(id, "SUPPORTED"), reason="검토 이유") for id in ids
                ]
            )
        raise AssertionError(f"대본에 없는 호출이다: {call.output.__name__}")


def scripted(script: Script, calls: int = 40) -> FakeLlm:
    """대본으로 답하는 FakeLlm. 응답을 calls번까지 쓴다."""
    return FakeLlm(*[script] * calls)


YUMIN_API = "카드 결제 승인 · 정산 API를 Java와 Spring Boot로 개발했습니다."
YUMIN_PERIOD = "한빛카드 결제플랫폼팀 2022.03 ~ 현재"
# 정유민(가상 지원자)이 자격요건을 모두 채우고 우대사항 P-01만 충족한 대본.
# 자격요건 50점, 우대사항 50 × 1.5 ÷ 3.5 = 21.4점, 총점 71.4점
YUMIN_SUMMARY = {
    "careerYears": 4,
    "lastCompany": "한빛카드",
    "criteriaVersion": CRITERIA_VERSION,
    "shortfalls": [],
    "criterionMarks": {
        "Q-01": "MET",
        "Q-02": "MET",
        "Q-03": "MET",
        "Q-04": "MET",
        "P-01": "MET",
        "P-02": "NOT_MET",
        "P-03": "NOT_MET",
    },
}


def yumin_script() -> Script:
    period = ExtractedPeriod(
        company="한빛카드", role="결제플랫폼팀", kind="EMPLOYMENT", start="2022-03", evidence=[YUMIN_PERIOD]
    )
    return Script(
        extract={"결제플랫폼팀": ExtractedFacts(periods=[period])},
        verdicts={
            "Q-01": verdict("Q-01", "MET", YUMIN_API, periods=[1]),
            "Q-02": verdict("Q-02", "MET", YUMIN_API),
            "Q-03": verdict("Q-03", "MET", YUMIN_API),
            "Q-04": verdict("Q-04", "MET", YUMIN_API),
            "P-01": verdict("P-01", "MET", YUMIN_API),
        },
    )
