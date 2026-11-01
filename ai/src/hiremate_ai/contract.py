"""backend와 주고받는 공통 계약 타입. backend의 Java 레코드를 그대로 옮긴다.

여러 Agent가 같이 쓰는 타입만 둔다. 한 Agent만 쓰는 요청 · 응답 타입은 담당자가 자기 Agent 패키지 안
(라우터 파일, 패키지 안 여러 모듈이 같이 쓰면 types.py)에 만든다.
필드를 바꾸면 저장소 루트 contract/의 JSON 샘플도 고친다. backend와 ai 테스트가 같은 샘플로 왕복 검사를 한다.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ContractModel(BaseModel):
    """필드는 snake_case, JSON 이름은 camelCase다. 모르는 필드는 무시한다."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        frozen=True,
    )


class InterviewerRole(StrEnum):
    HR = "HR"
    PRACTICAL = "PRACTICAL"


class InterviewerMemo(ContractModel):
    """담당자의 면접 메모. 지원자의 발언이나 검증된 사실과 구분한다."""

    stage_id: UUID
    stage_name: str
    text: str


class QuestionSource(StrEnum):
    """면접 질문을 만든 쪽 (interview.QuestionSource)."""

    AI = "AI"
    MANUAL = "MANUAL"


class InterviewSchedule(ContractModel):
    """면접 일정 (InterviewView.Schedule)."""

    scheduled_at: datetime | None
    interviewers: str


class InterviewQuestion(ContractModel):
    """면접 질문 하나와 기록한 답변 (InterviewView.Question). 답변이 없으면 빈 문자열이다."""

    question_id: UUID
    text: str
    source: QuestionSource
    answer: str
    reason: str | None = None
    # 🎤 질문 담당 (HR 인사 · PRACTICAL 실무). 담당 칸이 생기기 전에 저장된 질문은 None
    interviewer_role: InterviewerRole | None = None
    # 🎤 꼬리질문이면 원래 질문의 id, 처음 만든 질문은 None. 목록은 원래 질문 바로 뒤에 꼬리질문을 둔다 (최대 2단계)
    parent_question_id: UUID | None = None
    version: int = 0


class PreviousInterview(ContractModel):
    """이전 면접 전형의 질문과 답변 (InterviewView.PreviousInterview)."""

    stage_id: UUID
    stage_name: str
    schedule: InterviewSchedule | None
    questions: list[InterviewQuestion]


class InterviewView(ContractModel):
    """면접 전형 지원자 카드의 면접 기록 (interview.InterviewView). Root Agent와 면접 Agent가 같이 쓴다."""

    application_id: UUID
    schedule: InterviewSchedule | None
    questions: list[InterviewQuestion]
    previous: list[PreviousInterview]
    single_interview: bool = False


class DocumentType(StrEnum):
    """지원서 제출 항목 (posting.DocumentType)."""

    RESUME = "RESUME"
    COVER_LETTER = "COVER_LETTER"
    PORTFOLIO = "PORTFOLIO"
    CERTIFICATE = "CERTIFICATE"

    @property
    def label(self) -> str:
        """화면과 근거 출처에 쓰는 이름."""
        return _DOCUMENT_LABELS[self]


_DOCUMENT_LABELS = {
    DocumentType.RESUME: "이력서",
    DocumentType.COVER_LETTER: "자기소개서",
    DocumentType.PORTFOLIO: "포트폴리오",
    DocumentType.CERTIFICATE: "자격증",
}


class StageType(StrEnum):
    """전형 종류 (recruit.StageType)."""

    DOCUMENT = "DOCUMENT"
    ASSESSMENT = "ASSESSMENT"
    INTERVIEW = "INTERVIEW"


class AnalysisStatus(StrEnum):
    """지원 자료 분석 상태 (apply.AnalysisStatus)."""

    PENDING = "PENDING"
    DONE = "DONE"
    FAILED = "FAILED"


class CriterionCategory(StrEnum):
    """평가 항목의 영역. 영역마다 만점은 50점이다."""

    QUALIFICATION = "QUALIFICATION"  # 자격요건
    PREFERENCE = "PREFERENCE"  # 우대사항


class CriterionType(StrEnum):
    """평가 항목의 유형. 평가 기준을 준비할 때 정해 저장하고 지원자마다 바뀌지 않는다."""

    CONDITION = "CONDITION"  # 조건형 (경력 3년 이상, SQLD 보유): 0 · 1
    SINGLE = "SINGLE"  # 단일 능력 · 경험형: 0 · 1
    COMPOSITE = "COMPOSITE"  # 복합 경험형 (연동 구현 및 오류 처리): 0 · 0.5 · 1


class Verdict(StrEnum):
    """항목 하나의 판정. 모든 유형에서 근거가 모자라거나 상충하면 UNKNOWN이다."""

    MET = "MET"  # 1
    PARTIAL = "PARTIAL"  # 0.5. 복합 경험형에서 일부 수행이 확인될 때만
    NOT_MET = "NOT_MET"  # 0
    UNKNOWN = "UNKNOWN"  # 판단 불가. 0이나 0.5로 바꾸지 않는다


class CertificateStatus(StrEnum):
    """자격증 확인 상태. 증빙 제출을 발급기관 확인으로 표시하지 않는다."""

    SELF_REPORTED = "SELF_REPORTED"  # 본인 기재 · 미검증
    EVIDENCE_SUBMITTED = "EVIDENCE_SUBMITTED"  # 증빙 제출
    ISSUER_VERIFIED = "ISSUER_VERIFIED"  # 발급기관 확인


class QualificationStatus(StrEnum):
    """자격요건 75% 통과 판단. 점수 계산과 따로 둔다. 부분 충족은 0.5개로 센다."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    UNDETERMINED = "UNDETERMINED"  # 확인 필요 항목에 따라 결과가 갈린다 (분석 전도 여기)


class ScoreStatus(StrEnum):
    """총점 확정 상태. 서류를 읽지 못했거나 확인 필요가 남으면 보류다."""

    CONFIRMED = "CONFIRMED"
    HELD = "HELD"


class ApplicantInfo(ContractModel):
    """전형 화면의 지원자 한 명 (apply.ApplicantInfo). 분석 전이면 경력 · 점수가 None이다.

    passed는 자격요건 75% 통과가 확정됐는지, held는 총점을 보류했는지다. 보류면 document_score가 None이다.
    document_score는 서류 평가 총점(자격요건 50 + 우대사항 50, 소수 첫째 자리)이다.
    *_low는 확인 필요를 0점으로 넣어 계산한 점수다. 보류 지원자의 점수 표시와 정렬에 쓴다.
    """

    application_id: UUID
    recruitment_id: UUID
    application_no: int
    name: str
    email: str
    career_years: int | None
    last_company: str | None
    document_score: float | None
    document_score_low: float | None = None
    passed: bool
    held: bool = False
    shortfalls: list[str] = []  # 채우지 못한 자격요건의 짧은 표시 (예: 신입, 경력 확인 필요)
    qualification_status: QualificationStatus = QualificationStatus.UNDETERMINED
    qualification_score: float | None = None
    qualification_score_low: float | None = None
    qualification_max: int = 0
    preference_score: float | None = None
    preference_max: int = 0
    analysis_status: AnalysisStatus
    submitted_at: datetime


class ApplicantDocument(ContractModel):
    """제출 문서와 추출한 본문 (apply.ApplicantDocument)."""

    type: DocumentType
    file_id: UUID
    file_name: str
    size: int
    text: str


class ApplicantDetail(ContractModel):
    """지원서 전체 (apply.ApplicantDetail)."""

    info: ApplicantInfo
    phone: str
    certificates: str | None
    documents: list[ApplicantDocument]


class PostingRole(ContractModel):
    name: str = Field(min_length=1, max_length=100)
    career: str = Field(max_length=50)
    duties: list[str] = Field(max_length=10)
    qualifications: list[str] = Field(max_length=10)
    preferred: list[str] = Field(max_length=10)


class PostingContent(ContractModel):
    """공고 본문 (posting.PostingContent).

    headcount부터는 모집 조건이다. 채용 인원은 정하지 않았으면 None이고, 나머지는 비어 있으면 빈 문자열이다.
    모집 조건이 없던 때 만든 본문도 읽을 수 있게 기본값을 둔다.
    """

    title: str
    job_category: str
    employment_type: str
    career: str
    location: str
    intro: str
    duties: list[str]
    qualifications: list[str]
    preferred: list[str]
    benefits: list[str]
    headcount: int | None = None
    position: str = ""
    education: str = ""
    work_hours: str = ""
    salary: str = ""
    roles: list[PostingRole] = Field(default_factory=list, max_length=10)


class Talent(ContractModel):
    """인재상 항목 (company.Talent)."""

    title: str
    description: str


class CompanyProfile(ContractModel):
    """회사 소개 설정 (company.CompanyProfile). AI 분석의 인재상 기준으로 쓴다."""

    company_id: UUID
    name: str
    intro: str
    culture: str
    talents: list[Talent]
    benefits: list[str]


class Condition(ContractModel):
    """공고 조건 충족 여부 (CandidateAnalysis.Condition)."""

    label: str
    met: bool
    requirement: str


class Finding(ContractModel):
    """눈여겨볼 점이나 확인이 필요한 점과 그 출처 (CandidateAnalysis.Finding)."""

    text: str
    source: str


class Evidence(ContractModel):
    """문서 Viewer에 표시할 근거 문장 (CandidateAnalysis.Evidence)."""

    document: DocumentType
    sentence: str


class CriterionLine(ContractModel):
    """평가 항목 하나의 판정 (CandidateAnalysis.CriterionLine).

    fulfillment는 1 · 0.5 · 0이고 확인 필요면 None이다. allotted는 배점(영역 만점 ÷ 영역 항목 수),
    earned는 획득 점수이고 확인 필요면 None이다. career_years는 경력 기간 조건에서 코드가 계산한 관련 경력이다.
    """

    criterion_id: str
    category: CriterionCategory
    text: str
    important: bool  # 평가 기준의 중요 표시. 점수에는 쓰지 않는다
    criterion_type: CriterionType
    verdict: Verdict
    fulfillment: float | None
    allotted: float
    earned: float | None
    reason: str
    satisfied_parts: list[str]
    unsatisfied_parts: list[str]
    unknown_parts: list[str]
    evidence: list[Evidence]
    recheck_count: int
    career_years: int | None
    certificate_status: CertificateStatus | None


class SummarySection(ContractModel):
    """제출 문서의 문항별 요약 (CandidateAnalysis.SummarySection). 지금은 자기소개서 문항마다 하나다."""

    document: DocumentType
    title: str
    summary: str
    points: list[str]
    evidence: list[Evidence]


class CandidateAnalysis(ContractModel):
    """지원자 카드의 AI 분석 요약 (ai.application.CandidateAnalysis). 근거가 없으면 확인 필요로 둔다.

    holds는 총점을 보류한 이유다. 보류가 아니면 비어 있다.
    document_score는 총점(자격요건 + 우대사항, 0~100)이고 보류면 None이다. 영역 점수는 확인 필요가 있으면 None이다.
    *_low는 확인 필요를 0점으로 넣어 계산한 점수이고(보류 점수), 평가하지 못했거나 영역이 없으면 None이다.
    criteria는 항목별 판정이다. 분석 전이거나 서류를 읽지 못했으면 비어 있다.
    summaries는 자기소개서 문항별 요약이다. 판단 없이 무엇을 썼는지만 담는다.
    """

    conditions: list[Condition]
    notable: list[Finding]
    checks: list[Finding]
    holds: list[Finding]
    criteria_version: str | None
    score_status: ScoreStatus
    document_score: float | None
    document_score_low: float | None = None
    qualification_status: QualificationStatus
    qualification_rate: float | None
    qualification_score: float | None
    qualification_score_low: float | None = None
    qualification_max: int
    preference_score: float | None
    preference_score_low: float | None = None
    preference_max: int
    criteria: list[CriterionLine]
    summaries: list[SummarySection]
    highlights: list[Evidence]
    agent: str
    stub: bool


class FeatureLabelsRequest(ContractModel):
    """표 보기의 열 이름을 만들 평가 기준 · 인재상 문장들 (CandidateAnalyst.labels의 매개변수)."""

    texts: list[str]


class FeatureLabels(ContractModel):
    """texts와 같은 순서의 짧은 키워드. 예: '인성을 중요시한다' → '인성' (ai.application.FeatureLabels)."""

    labels: list[str]


class CompanyFactorsRequest(ContractModel):
    """회사 소개 · 조직 문화 글 (CandidateAnalyst.factors의 매개변수)."""

    text: str


class CompanyFactors(ContractModel):
    """회사 소개 · 조직 문화 글에서 뽑은, 회사가 사람을 볼 때 중요하게 여기는 요소 (ai.application.CompanyFactors).

    title은 짧은 낱말(예: '인성'), description은 그 요소가 나온 원문 문장이다.
    """

    items: list[Talent]


class TalentLevel(StrEnum):
    """인재상 하나에 맞는 정도. 서류에 근거가 없으면 UNKNOWN이다 (LOW로 바꾸지 않는다)."""

    HIGH = "HIGH"  # 상: 본인이 직접 한 구체 경험이 있다
    MID = "MID"  # 중: 관련 경험은 있지만 팀 성과이거나 본인 역할 · 결과가 분명하지 않다
    LOW = "LOW"  # 하: 관련 언급은 있지만 구체 경험이 없다
    UNKNOWN = "UNKNOWN"  # 확인 필요


class TalentFitRequest(ContractModel):
    """지원자 한 명의 인재상 판정 요청 (CandidateAnalyst.talents의 매개변수). 지원 접수 때 저장한 분석을 읽는다."""

    company_id: UUID
    recruitment_id: UUID
    application_id: UUID
    talents: list[Talent]


class TalentFitItem(ContractModel):
    """인재상 하나의 판정 (TalentFit.Item). evidence는 무엇을 했는지 짧게, quote는 원문 문장이다."""

    title: str
    level: TalentLevel
    evidence: str
    reason: str
    quote: str | None


class TalentFit(ContractModel):
    """지원자 한 명의 인재상 판정. items는 요청한 인재상과 같은 순서다 (ai.application.TalentFit)."""

    items: list[TalentFitItem]
    agent: str
    stub: bool


class Job(ContractModel):
    """AI 워커가 처리할 분석 작업 (job.Job). backend가 Redis 작업 스트림에 넣는다.

    type은 ai 서버 경로와 같은 '{agent}/{method}'이고 payload는 그 경로의 요청 본문과 같다.
    target은 작업 대상이다 (application/analyze면 지원서 ID). 같은 대상의 작업을 묶는 데 쓴다.
    """

    job_id: UUID
    type: str
    target: str
    payload: dict[str, Any]


class JobStatus(StrEnum):
    """작업 결과 (job.JobStatus)."""

    DONE = "DONE"
    FAILED = "FAILED"


class JobResult(ContractModel):
    """작업 결과 (job.JobResult). AI 워커가 Redis 결과 스트림에 넣고 backend가 꺼내 기록한다.

    DONE이면 result가 그 경로의 응답 본문이다. FAILED면 result가 None이고 error에 이유를 남긴다.
    error는 로그에만 남고 화면에는 보이지 않는다.
    """

    job_id: UUID
    type: str
    target: str
    status: JobStatus
    result: dict[str, Any] | None
    error: str | None
