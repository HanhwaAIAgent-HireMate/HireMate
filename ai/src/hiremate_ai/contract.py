"""backend와 주고받는 공통 계약 타입. backend의 Java 레코드를 그대로 옮긴다.

여러 Agent가 같이 쓰는 타입만 둔다. 한 Agent만 쓰는 요청 · 응답 타입은 담당자가 자기 Agent 패키지 안
(라우터 파일, 패키지 안 여러 모듈이 같이 쓰면 types.py)에 만든다.
필드를 바꾸면 저장소 루트 contract/의 JSON 샘플도 고친다. backend와 ai 테스트가 같은 샘플로 왕복 검사를 한다.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict
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


class ApplicantInfo(ContractModel):
    """전형 화면의 지원자 한 명 (apply.ApplicantInfo). 분석 전이면 경력 · 점수가 None이다."""

    application_id: UUID
    recruitment_id: UUID
    application_no: int
    name: str
    email: str
    career_years: int | None
    last_company: str | None
    document_score: int | None
    passed: bool
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


class PostingContent(ContractModel):
    """공고 본문 (posting.PostingContent)."""

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


class CandidateAnalysis(ContractModel):
    """지원자 카드의 AI 분석 요약 (ai.application.CandidateAnalysis). 근거가 없으면 확인 필요로 둔다."""

    conditions: list[Condition]
    notable: list[Finding]
    checks: list[Finding]
    highlights: list[Evidence]
    agent: str
    stub: bool
