"""Application Agent만 쓰는 타입.

- backend와 주고받는 계약: ScreeningRubric(posting.ScreeningRubric), ApplicationAnalysis(apply.ApplicationAnalysis).
  필드를 바꾸면 저장소 루트 contract/의 샘플도 고친다. 판정 · 유형 같은 공용 열거형은 contract.py에 있다.
- 요청 본문: AnalyzeRequest. ai 서버 경로와 AI 워커 작업(contract/Job.json의 payload)이 같이 쓴다.
- 분석 결과 원본: ApplicationReview. ai.application_reviews에 그대로 저장하고, backend에 돌려주는 값은 여기서 만든다.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from hiremate_ai.contract import (
    ApplicantDetail,
    CertificateStatus,
    ContractModel,
    CriterionCategory,
    CriterionType,
    DocumentType,
    PostingContent,
    QualificationStatus,
    ScoreStatus,
    Verdict,
)


class EvaluationRules(ContractModel):
    """항목 하나의 판정 기준. 부분 충족은 복합 경험형에만 있다."""

    met: str  # 충족(1) 기준
    partial: str | None = None  # 부분 충족(0.5) 기준
    unmet: str  # 미충족(0) 기준


class Criterion(ContractModel):
    """평가 항목 하나 (posting.ScreeningRubric.Criterion). 사람이 정해 저장하고 Agent는 바꾸지 않는다.

    text는 공고의 자격요건 · 우대사항 문장과 같아야 짝이 맞는다. 유형과 중요 표시는 지원자마다 바뀌지 않는다.
    """

    criterion_id: str  # 예: Q-01, P-01
    category: CriterionCategory
    text: str
    important: bool
    criterion_type: CriterionType
    evaluation_rules: EvaluationRules
    certificates: list[str] = []  # 자격증 보유 조건이면 인정하는 자격증 이름. 코드가 이름으로 확인한다
    ncs_unit_code: str | None = None  # 기준 초안을 쓸 때 참고한 NCS 능력단위 (출처로만 보관한다)


class ScreeningRubric(ContractModel):
    """서류 평가 기준 (posting.ScreeningRubric). 공고 담당이 입력 화면을 만들기 전까지 backend 설정의 더미다."""

    company_id: UUID
    recruitment_id: UUID
    criteria_version: str  # 평가 기준 버전. 결과에 함께 남기고, 바뀌면 저장된 결과를 다시 쓰지 않는다
    hire_count: int  # 선발 인원. AI 추천은 이 인원의 10배수까지다 (backend screening이 줄 세운다)
    criteria: list[Criterion]


class AnalyzeRequest(ContractModel):
    """분석 요청 본문. ai 서버 경로(application/analyze, candidate-analyst/analyze)와 AI 워커 작업(payload)이 같이 쓴다.

    키는 backend Agent 메서드의 매개변수 이름이다.
    """

    applicant: ApplicantDetail
    posting: PostingContent
    rubric: ScreeningRubric


class ApplicationAnalysis(ContractModel):
    """지원 접수 때 backend에 돌려주는 요약 (apply.ApplicationAnalysis).

    75% 통과 판단(qualification_status)과 점수 확정 상태(held)는 따로 둔다. passed는 통과가 확정됐는가다.
    """

    career_years: int | None  # 서류를 읽지 못했거나 경력을 확인하지 못하면 None, 신입은 0
    last_company: str | None
    criteria_version: str | None
    qualification_status: QualificationStatus
    qualification_rate: float | None  # 자격요건 충족률 (%). 확인 필요가 있으면 None
    qualification_score: float | None  # 자격요건 점수. 확인 필요가 있으면 None
    qualification_max: int  # 자격요건 만점 (50, 우대사항이 없으면 100, 항목이 없으면 0)
    preference_score: float | None
    preference_max: int
    document_score: float | None  # 총점 (0~100, 소수 첫째 자리). 보류면 None
    passed: bool  # qualification_status가 PASSED인가
    held: bool  # 총점을 확정하지 못했다 (서류를 읽지 못함 · 확인 필요 남음)
    shortfalls: list[str]  # 채우지 못했거나 확인이 필요한 자격요건의 짧은 표시 (예: 신입, 경력 확인 필요)


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class Actor(StrEnum):
    SELF = "SELF"  # 본인이 직접 했다
    TEAM = "TEAM"  # 팀 · 조직의 성과다
    UNCLEAR = "UNCLEAR"


FULFILLMENT = {Verdict.MET: 1.0, Verdict.PARTIAL: 0.5, Verdict.NOT_MET: 0.0}
VERDICT_LABEL = {
    Verdict.MET: "충족",
    Verdict.PARTIAL: "부분 충족",
    Verdict.NOT_MET: "미충족",
    Verdict.UNKNOWN: "확인 필요",
}


class Quote(_Record):
    """원문에서 찾은 근거 문장. sentence는 원문 글자 그대로다."""

    document: DocumentType
    sentence: str


class Fact(_Record):
    kind: str  # EXPERIENCE, PROJECT, SKILL, CERTIFICATE, ACHIEVEMENT, ACTIVITY, EDUCATION
    statement: str
    actor: Actor
    quotes: list[Quote]
    supported: bool = True  # 검토에서 근거가 주장을 받쳐 주지 않으면 False


class Period(_Record):
    company: str
    role: str
    kind: str  # EMPLOYMENT, INTERN, FREELANCE, PROJECT, EDUCATION
    start: str  # YYYY-MM
    end: str | None  # 재직 중이면 None
    months: int
    quote: Quote


class CriterionResult(_Record):
    """평가 항목 하나의 판정. 업무 관련성 · 본인 역할 · 수행 범위는 따로 점수를 매기지 않고 충족도를 정하는 데 쓴다."""

    criterion_id: str
    category: CriterionCategory
    text: str
    important: bool
    criterion_type: CriterionType
    verdict: Verdict
    reason: str
    relevance: str = ""
    role: Actor | None = None
    scope: str = ""
    satisfied_parts: list[str] = []
    unsatisfied_parts: list[str] = []
    unknown_parts: list[str] = []
    quotes: list[Quote] = []
    recheck_count: int = 0
    shortfall: str | None = None  # 자격요건을 채우지 못했거나 확인이 필요할 때 이름 옆에 붙는 짧은 표시
    career_months: int | None = None  # 경력 기간 조건이면 코드가 계산한, 요건과 관련된 경력 개월 수
    certificate_status: CertificateStatus | None = None  # 자격증 조건이면 확인 상태

    @property
    def fulfillment(self) -> float | None:
        return FULFILLMENT.get(self.verdict)


class Note(_Record):
    """카드에 보여 줄 한 줄과 출처."""

    text: str
    source: str


class ApplicationReview(_Record):
    """지원서 분석 한 번의 결과 원본."""

    version: str
    input_hash: str
    application_id: UUID
    readable: bool  # 제출 서류에서 글자를 읽었는가
    criteria_version: str = ""
    facts: list[Fact] = []
    periods: list[Period] = []
    career_years: int | None = None
    last_company: str | None = None
    criteria: list[CriterionResult] = []
    qualification_status: QualificationStatus = QualificationStatus.UNDETERMINED
    qualification_rate: float | None = None
    qualification_score: float | None = None
    qualification_max: int = 0
    preference_score: float | None = None
    preference_max: int = 0
    score_status: ScoreStatus = ScoreStatus.HELD
    document_score: float | None = None  # 총점 (0~100, 소수 첫째 자리). 보류면 None
    holds: list[Note] = []  # 총점을 보류한 이유
    checks: list[Note] = []

    @property
    def held(self) -> bool:
        return self.score_status == ScoreStatus.HELD

    @property
    def passed(self) -> bool:
        return self.qualification_status == QualificationStatus.PASSED

    @property
    def qualifications(self) -> list[CriterionResult]:
        return [result for result in self.criteria if result.category == CriterionCategory.QUALIFICATION]

    @property
    def preferences(self) -> list[CriterionResult]:
        return [result for result in self.criteria if result.category == CriterionCategory.PREFERENCE]
