"""Application Agent만 쓰는 타입.

- backend와 주고받는 계약: ScreeningRubric(posting.ScreeningRubric), ApplicationAnalysis(apply.ApplicationAnalysis).
  필드를 바꾸면 저장소 루트 contract/의 샘플도 고친다. 판정 · 유형 같은 공용 열거형은 contract.py에 있다.
- 요청 본문: AnalyzeRequest. ai 서버 경로와 AI 워커 작업(contract/Job.json의 payload)이 같이 쓴다.
- 분석 결과 원본: ApplicationReview. ai.application_reviews에 그대로 저장하고, backend에 돌려주는 값은 여기서 만든다.
"""

from enum import StrEnum
from typing import Literal
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
    important는 공고에서 필수(중요)로 표시한 항목이다. 필수 조건의 기본값과 면접 질문 정리에 쓴다.
    """

    criterion_id: str  # 예: Q-01, P-01
    category: CriterionCategory
    text: str
    important: bool
    criterion_type: CriterionType
    evaluation_rules: EvaluationRules
    certificates: list[str] = []  # 자격증 보유 조건이면 인정하는 자격증 이름. 코드가 이름으로 확인한다


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
    """지원 접수 때 backend에 돌려주는 요약 (apply.ApplicationAnalysis). 서류는 점수를 매기지 않는다."""

    career_years: int | None  # 서류를 읽지 못했거나 경력을 확인하지 못하면 None, 신입은 0
    last_company: str | None
    criteria_version: str | None
    shortfalls: list[str]  # 채우지 못했거나 확인이 필요한 자격요건의 짧은 표시 (예: 신입, 경력 확인 필요)
    # 평가 항목 ID별 판정. backend가 전체 지원자를 충족 개수로 줄 세우고 필수 조건을 확인하는 데 쓴다
    criterion_marks: dict[str, Verdict] = {}


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class Actor(StrEnum):
    SELF = "SELF"  # 본인이 직접 했다
    TEAM = "TEAM"  # 팀 · 조직의 성과다
    UNCLEAR = "UNCLEAR"


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
    important: bool  # 평가 기준의 중요 표시. 점수에는 쓰지 않는다
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
    metric: str = ""  # 경험형 항목 근거의 정량 지표(원문 그대로). 화면은 경험 + 지표면 상으로 보여 준다
    no_record: bool = False  # 미충족 가운데 서류에 관련 기록이 아예 없는 것(언급 없음)
    brief: str = ""  # 카드에 보일 판정 요약 한 줄. 만들지 못했으면 비어 있다
    setting_note: str = ""  # 판정 기준이 정하지 않아 판정이 갈리는 점 (지원자 확인할 점이 아니라 평가 설정 검토)


class DocumentSection(_Record):
    """자기소개서 문항 하나의 요약. 판단 없이 무엇을 썼는지만 담는다."""

    document: DocumentType
    title: str
    summary: str
    points: list[str] = []
    quotes: list[Quote] = []


class DigestRow(_Record):
    """정리 표의 한 행 (카드면 카드 하나). cells는 구역의 columns 순서다. quotes는 원문으로 가는 근거 문장이다."""

    title: str = ""
    cells: list[str] = []
    tags: list[str] = []  # 카드에 칩으로 보일 기술 (포트폴리오 프로젝트)
    quotes: list[Quote] = []


class DigestSection(_Record):
    """서류 정리의 한 구역. table은 표, cards는 제목 + 칸 카드다. tags(기술 등)와 items(자격 등 한 줄)도 담는다."""

    title: str
    layout: Literal["table", "cards"] = "table"
    columns: list[str] = []
    rows: list[DigestRow] = []
    tags: list[str] = []
    items: list[str] = []


class DocumentDigest(_Record):
    """이력서 · 포트폴리오를 담당자가 훑어보기 좋게 정리한 것. 판단 없이 서류에 적힌 것만 짧게 옮긴다."""

    document: DocumentType
    sections: list[DigestSection] = []


class Note(_Record):
    """카드에 보여 줄 한 줄과 출처. 눈여겨볼 점 묶음이면 제목 · 한 일 · 지표를 따로 담는다."""

    text: str
    source: str
    title: str = ""
    detail: str = ""
    metric: str = ""
    warning: bool = False  # 담당자가 주의해서 볼 서류 신호 (확인할 점에 붉게 표시)


class ApplicationReview(_Record):
    """지원서 분석 한 번의 결과 원본."""

    version: str
    input_hash: str
    application_id: UUID
    readable: bool  # 제출 서류에서 글자를 읽었는가
    criteria_version: str = ""
    facts: list[Fact] = []
    periods: list[Period] = []
    sections: list[DocumentSection] = []  # 자기소개서 문항별 요약
    digests: list[DocumentDigest] = []  # 이력서 · 포트폴리오 정리 (서류 화면의 정리 보기)
    career_years: int | None = None
    last_company: str | None = None
    criteria: list[CriterionResult] = []
    notable: list[Note] = []  # 같은 일끼리 묶은 눈여겨볼 점 (제목 — 한 문장). 비어 있으면 경험 문장을 그대로 쓴다
    holds: list[Note] = []  # 확인 필요로 남은 항목 (서류를 읽지 못했으면 그 사실)
    checks: list[Note] = []

    @property
    def qualifications(self) -> list[CriterionResult]:
        return [result for result in self.criteria if result.category == CriterionCategory.QUALIFICATION]

    @property
    def preferences(self) -> list[CriterionResult]:
        return [result for result in self.criteria if result.category == CriterionCategory.PREFERENCE]
