"""Application Agent 테스트가 같이 쓰는 공고 · 평가 기준 · NCS 평가 조건과 가짜 모델 대본.

모델 호출은 문서별 · 우대사항별로 동시에 나가므로 FakeLlm에는 호출 내용을 보고 답하는 대본(Script)을 넣는다.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from hiremate_ai.agents.analysis.application.extract import ExtractedFacts
from hiremate_ai.agents.analysis.application.fit import FitJudgement, FitScore
from hiremate_ai.agents.analysis.application.judge import (
    CriterionVerdict,
    PreferenceJudgement,
    QualificationJudgement,
    QualificationVerdict,
)
from hiremate_ai.agents.analysis.application.review import ClaimReview, ReviewJudgement
from hiremate_ai.agents.analysis.application.types import RubricPreference, ScreeningRubric
from hiremate_ai.contract import PostingContent
from hiremate_ai.llm.fake import FakeLlm, LlmCall
from hiremate_ai.tools.ncs import NcsElement, NcsUnit

type ReviewVerdict = Literal["SUPPORTED", "OVERSTATED", "UNSUPPORTED"]

TODAY = date(2026, 10, 21)
COMPANY_ID = UUID("2b8e4c1d-6f3a-4e5b-9c7d-0a1b2c3d4e50")
RECRUITMENT_ID = UUID("7a1e2b3c-4d5e-4f60-8a9b-0c1d2e3f4a51")
DESIGN = "2001020218_23v6"
DEPLOY = "2001020214_23v6"

QUALIFICATIONS = [
    "Java 또는 Kotlin 기반 서버 개발 경력 3년 이상",
    "Spring Boot로 REST API를 개발한 경험",
    "RDBMS 설계와 SQL 작성 경험",
    "Git 기반 협업 경험",
]
PREFERRED = ["외부 시스템 연동 인터페이스를 설계한 경험", "빌드 · 배포 자동화를 구성한 경험"]


def _element(number: int, name: str, criterion: str) -> NcsElement:
    return NcsElement(number=number, name=name, criteria=[criterion], knowledge=[], skills=[], attitudes=[])


def _unit(code: str, name: str, definition: str, elements: list[NcsElement]) -> NcsUnit:
    return NcsUnit(
        code=code,
        name=name,
        level=5,
        definition=definition,
        duty_code=code[:8],
        major="정보통신",
        middle="정보기술",
        minor="정보기술개발",
        subdivision="응용SW엔지니어링",
        elements=elements,
        scope={},
        evaluation_points=[],
        basic_competencies=[],
    )


UNITS = {
    DESIGN: _unit(
        DESIGN,
        "인터페이스 설계",
        "시스템 인터페이스 요구사항을 확인하고 인터페이스를 설계하는 능력이다.",
        [
            _element(1, "인터페이스 요구사항 확인하기", "인터페이스 기능 요구사항을 분석할 수 있다."),
            _element(2, "인터페이스 대상 식별하기", "인터페이스에 필요한 송수신 데이터를 식별할 수 있다."),
            _element(3, "인터페이스 상세 설계하기", "인터페이스 오류 시 처리 방안을 명세화할 수 있다."),
        ],
    ),
    DEPLOY: _unit(
        DEPLOY,
        "애플리케이션 배포",
        "애플리케이션을 빌드하여 운영 환경에 배포하는 능력이다.",
        [
            _element(3, "애플리케이션 빌드하기", "빌드 스크립트를 작성할 수 있다."),
            _element(4, "애플리케이션 배포하기", "배포 절차에 따라 운영 환경에 적용할 수 있다."),
        ],
    ),
}


def make_posting(base: PostingContent) -> PostingContent:
    """가상 공고에 이 테스트의 자격요건 4개 · 우대사항 2개를 넣는다."""
    return base.model_copy(update={"qualifications": QUALIFICATIONS, "preferred": PREFERRED})


def make_rubric() -> ScreeningRubric:
    return ScreeningRubric(
        company_id=COMPANY_ID,
        recruitment_id=RECRUITMENT_ID,
        hire_count=1,
        preferred=[
            RubricPreference(text=PREFERRED[0], weight=5, ncs_unit_code=DESIGN, certificates=["정보처리기사"]),
            RubricPreference(text=PREFERRED[1], weight=3, ncs_unit_code=DEPLOY, certificates=[]),
        ],
    )


def met(number: int, *evidence: str) -> QualificationVerdict:
    return QualificationVerdict(number=number, verdict="MET", reason="근거가 있다", evidence=list(evidence))


def not_met(number: int, shortfall: str) -> QualificationVerdict:
    return QualificationVerdict(number=number, verdict="NOT_MET", reason="근거가 없다", shortfall=shortfall)


def criterion(number: int, level: Literal["MET", "NONE"], *evidence: str) -> CriterionVerdict:
    return CriterionVerdict(number=number, level=level, reason=f"C{number} 판정", evidence=list(evidence))


def judged(*criteria: CriterionVerdict) -> PreferenceJudgement:
    return PreferenceJudgement(criteria=list(criteria))


def fitted(*scores: tuple[str, int, str]) -> FitJudgement:
    """직무 적합도 대본. (항목 key, 점수, 근거 문장)."""
    return FitJudgement(
        scores=[
            FitScore(key=key, points=points, reason=f"{key} 이유", evidence=[evidence] if evidence else [])
            for key, points, evidence in scores
        ]
    )


@dataclass
class Script:
    """호출 내용을 보고 답하는 가짜 모델의 대본.

    extract: 문서 본문 일부 → 추출 결과. qualify: 자격요건 판정. prefer: 우대사항 글 → 판정.
    fit: 직무 적합도 항목 점수. reviews: 주장 id → 검토 결과 (없으면 SUPPORTED).
    """

    extract: dict[str, ExtractedFacts] = field(default_factory=dict)
    qualify: QualificationJudgement = field(default_factory=lambda: QualificationJudgement(verdicts=[]))
    prefer: dict[str, PreferenceJudgement] = field(default_factory=dict)
    fit: FitJudgement = field(default_factory=lambda: FitJudgement(scores=[]))
    reviews: dict[str, ReviewVerdict] = field(default_factory=dict)

    def __call__(self, call: LlmCall) -> BaseModel:
        if call.output is ExtractedFacts:
            return next((value for key, value in self.extract.items() if key in call.user), ExtractedFacts())
        if call.output is QualificationJudgement:
            return self.qualify
        if call.output is PreferenceJudgement:
            return next(
                (value for key, value in self.prefer.items() if f"우대사항: {key}" in call.user),
                PreferenceJudgement(criteria=[]),
            )
        if call.output is FitJudgement:
            return self.fit
        if call.output is ReviewJudgement:
            ids = re.findall(r"^(Q\d+|P\d+-C\d+|F\d+)\. 주장", call.user, re.MULTILINE)
            return ReviewJudgement(
                reviews=[
                    ClaimReview(id=id, verdict=self.reviews.get(id, "SUPPORTED"), reason="검토 이유") for id in ids
                ]
            )
        raise AssertionError(f"대본에 없는 호출이다: {call.output.__name__}")


def scripted(script: Script, calls: int = 30) -> FakeLlm:
    """대본으로 답하는 FakeLlm. 응답을 calls번까지 쓴다."""
    return FakeLlm(*[script] * calls)
