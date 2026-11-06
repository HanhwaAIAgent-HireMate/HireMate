"""backend와 주고받는 공통 계약 타입. backend의 Java 레코드를 그대로 옮긴다.

여러 Agent가 같이 쓰는 타입만 둔다. 한 Agent만 쓰는 요청 · 응답 타입은 담당자가 자기 Agent 패키지 안
(라우터 파일, 패키지 안 여러 모듈이 같이 쓰면 types.py)에 만든다.
필드를 바꾸면 저장소 루트 contract/의 JSON 샘플도 고친다. backend와 ai 테스트가 같은 샘플로 왕복 검사를 한다.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
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


NcsUse = Literal["SKIP", "REQUESTED", "HELPFUL"]
"""면접 질문을 만들 때 NCS를 참고할지 (Root 계획이 정한다). REQUESTED는 HR이 NCS를 참고하라고 한 요청이라,
참고하지 못하면 backend가 알린다. 없으면 SKIP이고 지금처럼 만든다."""


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


class ApplicantInfo(ContractModel):
    """전형 화면의 지원자 한 명 (apply.ApplicantInfo). 분석 전이면 경력이 None이다. 서류는 점수를 매기지 않는다."""

    application_id: UUID
    recruitment_id: UUID
    application_no: int
    name: str
    email: str
    career_years: int | None
    last_company: str | None
    shortfalls: list[str] = []  # 채우지 못한 자격요건의 짧은 표시 (예: 신입, 경력 확인 필요)
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
    blind: bool = False
    """블라인드 채용. 켜면 학력 · 출신 학교를 공고와 AI 판단에 쓰지 않는다 (차별 조건 검사에 blind로 넘긴다)."""


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
    address: str = ""
    """회사 주소. 채용 페이지에 보여 주는 값이고 AI는 쓰지 않는다."""


class Condition(ContractModel):
    """공고 조건 충족 여부 (CandidateAnalysis.Condition)."""

    label: str
    met: bool
    requirement: str


class Finding(ContractModel):
    """눈여겨볼 점이나 확인이 필요한 점과 그 출처 (CandidateAnalysis.Finding).

    같은 일끼리 묶은 눈여겨볼 점은 title(제목) · detail(한 일) · metric(정량 지표)을 따로 담는다.
    text는 셋을 이은 한 줄이다.
    """

    text: str
    source: str
    title: str = ""
    detail: str = ""
    metric: str = ""
    # 담당자가 주의해서 볼 서류 신호 (잦은 이직, 기준 없는 수치, 서류 속 평가 지시문 등). 확인할 점에 붉게 표시한다
    warning: bool = False


class Evidence(ContractModel):
    """문서 Viewer에 표시할 근거 문장 (CandidateAnalysis.Evidence)."""

    document: DocumentType
    sentence: str


class CriterionLine(ContractModel):
    """평가 항목 하나의 판정 (CandidateAnalysis.CriterionLine). 점수는 매기지 않는다.

    career_years는 경력 기간 조건에서 코드가 계산한 관련 경력이다.
    """

    criterion_id: str
    category: CriterionCategory
    text: str
    important: bool  # 평가 기준의 중요(필수) 표시
    criterion_type: CriterionType
    verdict: Verdict
    reason: str
    satisfied_parts: list[str]
    unsatisfied_parts: list[str]
    unknown_parts: list[str]
    evidence: list[Evidence]
    recheck_count: int
    career_years: int | None
    certificate_status: CertificateStatus | None
    # 근거의 정량 지표(숫자로 된 성과 · 규모, 원문 그대로). 경험형 항목은 경험과 지표가 함께 있어야 상이다
    metric: str = ""
    # 미충족 가운데 서류에 관련 기록이 아예 없는 것. 표기는 하와 같고, 카드에 '서류에 해당 내용 없음'으로 보인다
    no_record: bool = False
    brief: str = ""  # 카드에 보일 판정 요약 한 줄. 예전 분석이나 코드가 바꾼 판정은 비어 있다
    # 판정 기준이 정하지 않아 판정이 갈리는 점 (예: '대용량'의 규모 기준 없음).
    # 지원자에게 물을 점이 아니라 평가 설정 검토다
    setting_note: str = ""


class SummarySection(ContractModel):
    """제출 문서의 문항별 요약 (CandidateAnalysis.SummarySection). 지금은 자기소개서 문항마다 하나다."""

    document: DocumentType
    title: str
    summary: str
    points: list[str]
    evidence: list[Evidence]


class CandidateAnalysis(ContractModel):
    """지원자 카드의 AI 분석 요약 (ai.application.CandidateAnalysis). 근거가 없으면 확인 필요로 둔다.

    holds는 확인 필요로 남은 항목이다 (서류를 읽지 못했으면 그 사실). 점수는 매기지 않는다.
    criteria는 항목별 판정이다. 분석 전이거나 서류를 읽지 못했으면 비어 있다.
    summaries는 자기소개서 문항별 요약이다. 판단 없이 무엇을 썼는지만 담는다.
    """

    conditions: list[Condition]
    notable: list[Finding]
    checks: list[Finding]
    holds: list[Finding]
    criteria_version: str | None
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
    """인재상 하나의 행동이 서류에서 확인되는 정도. 인재상 설명의 행동 확인 · 일부 확인 기준으로 판정한다."""

    HIGH = "HIGH"  # 행동 확인: 본인이 직접 한 경험이 행동 확인 기준을 모두 채운다
    MID = "MID"  # 일부 확인: 본인이 직접 한 경험이 일부 확인 기준에 해당한다
    LOW = "LOW"  # 미확인: 기준의 행동이 서류에 없다 (다짐 · 팀 성과만 있거나 본인 역할이 분명하지 않다)
    UNKNOWN = "UNKNOWN"  # 확인 필요: 분석이 없거나 근거 번호가 맞지 않아 판정하지 못했다


class TalentFitRequest(ContractModel):
    """지원자 한 명의 인재상 판정 요청 (CandidateAnalyst.talents의 매개변수). 지원 접수 때 저장한 분석을 읽는다."""

    company_id: UUID
    recruitment_id: UUID
    application_id: UUID
    talents: list[Talent]


class TalentFitItem(ContractModel):
    """인재상 하나의 판정 (TalentFit.Item).

    evidence는 무엇을 했는지 짧게, quote는 원문 문장, metric은 상일 때 근거의 정량 지표다.
    """

    title: str
    level: TalentLevel
    evidence: str
    reason: str
    quote: str | None
    metric: str = ""


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


class DocumentSource(ContractModel):
    """블라인드 처리한 파서 원문 조각."""

    id: str = Field(min_length=1, pattern=r"\S")
    page: int | None = Field(ge=1)
    text: str


NormalizedDocumentType = Literal[DocumentType.RESUME, DocumentType.COVER_LETTER, DocumentType.PORTFOLIO]
ParagraphRole = Literal["body", "caption", "page_header", "page_footer", "form_instruction", "unassigned"]
VISUAL_NOTICE = "관련 시각 자료가 있을 수 있습니다. 원본 PDF를 확인해 주세요."
CODE_NOTICE = "코드 예시가 포함되어 있습니다. 원본 PDF를 확인해 주세요."


class DocumentBlockBase(ContractModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, pattern=r"\S")
    source_ids: list[Annotated[str, Field(min_length=1, pattern=r"\S")]]


class DocumentSection(DocumentBlockBase):
    type: Literal["section"] = "section"
    title: str | None
    blocks: list["DocumentBlock"]

    @model_validator(mode="after")
    def validate_title_sources(self) -> "DocumentSection":
        if self.title is None and self.source_ids:
            raise ValueError("Untitled sections cannot have title sources")
        return self


class DocumentParagraph(DocumentBlockBase):
    type: Literal["paragraph"] = "paragraph"
    role: ParagraphRole
    text: str


class DocumentListItem(ContractModel):
    model_config = ConfigDict(extra="forbid")
    marker: str | None
    text: str
    children: list["DocumentListItem"]


class DocumentList(DocumentBlockBase):
    type: Literal["list"] = "list"
    items: list[DocumentListItem]


class DocumentTable(DocumentBlockBase):
    type: Literal["table"] = "table"
    caption: str | None
    headers: list[str | None]
    rows: list[list[str | None]]


class DocumentReference(DocumentBlockBase):
    type: Literal["reference"] = "reference"
    kind: Literal["possible_visual", "code_example"]
    text: str | None
    notice: str

    @model_validator(mode="after")
    def validate_notice(self) -> "DocumentReference":
        expected = VISUAL_NOTICE if self.kind == "possible_visual" else CODE_NOTICE
        if self.notice != expected:
            raise ValueError("Reference notice must be assigned by code")
        return self


DocumentBlock = Annotated[
    DocumentSection | DocumentParagraph | DocumentList | DocumentTable | DocumentReference,
    Field(discriminator="type"),
]
DocumentSection.model_rebuild()


class NormalizedDocument(ContractModel):
    """코드가 메타데이터와 블록 ID를 부여한 정제 문서."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    document_id: UUID
    revision: int = Field(gt=0)
    document_type: NormalizedDocumentType
    blocks: list[DocumentBlock]

    def all_blocks(self) -> list[DocumentBlock]:
        def flatten(blocks: list[DocumentBlock]) -> list[DocumentBlock]:
            return [
                child
                for block in blocks
                for child in ([block] + (flatten(block.blocks) if isinstance(block, DocumentSection) else []))
            ]

        return flatten(self.blocks)

    @model_validator(mode="after")
    def validate_block_ids(self) -> "NormalizedDocument":
        ids = [block.id for block in self.all_blocks()]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate block IDs")
        return self

    def validate_sources(self, sources: list[DocumentSource]) -> None:
        ids = {source.id for source in sources}
        if len(ids) != len(sources):
            raise ValueError("Duplicate source IDs")
        if any(source_id not in ids for block in self.all_blocks() for source_id in block.source_ids):
            raise ValueError("Unknown source ID")


class DocumentNormalizationRequest(ContractModel):
    """기업과 문서 버전 범위가 고정된 정제 요청."""

    model_config = ConfigDict(extra="forbid")
    company_id: UUID
    recruitment_id: UUID
    application_id: UUID
    document_id: UUID
    revision: int = Field(gt=0)
    document_type: NormalizedDocumentType
    sources: list[DocumentSource]

    @model_validator(mode="after")
    def validate_source_ids(self) -> "DocumentNormalizationRequest":
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError("Duplicate source IDs")
        return self


class DocumentIndexRequest(ContractModel):
    """backend가 검증하고 저장한 문서와 그 문서를 만든 권한 범위."""

    model_config = ConfigDict(extra="forbid")
    request: DocumentNormalizationRequest
    document: NormalizedDocument

    @model_validator(mode="after")
    def validate_document(self) -> "DocumentIndexRequest":
        if (
            self.request.document_id != self.document.document_id
            or self.request.revision != self.document.revision
            or self.request.document_type != self.document.document_type
        ):
            raise ValueError("Normalized document identity does not match its request")
        self.document.validate_sources(self.request.sources)
        return self
