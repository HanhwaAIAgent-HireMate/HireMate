"""Posting Agent만 쓰는 계약 타입. backend `posting` · `recruit` · `ai.application`의 Java 레코드를 그대로 옮긴다.

필드를 바꾸면 저장소 루트 contract/의 PostingDraftContext.json · PostingSuggestion.json도 고친다.
"""

from enum import StrEnum
from uuid import UUID

from hiremate_ai.contract import ContractModel, DocumentType, PostingContent, StageType


class RecruitmentStatus(StrEnum):
    """채용 진행 상태 (recruit.RecruitmentStatus). 작성 중 · 공고 게시 중 · 전형 진행 중 · 종료."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class StageDraft(ContractModel):
    """공고에서 정한 전형 하나 (recruit.StageDraft). 이름은 기업이 부르는 그대로 쓴다."""

    name: str
    type: StageType


class PostingDraftContext(ContractModel):
    """AI 수정 요청에 넘기는 현재 공고 (posting.PostingDraftContext).

    required_extras는 이력서 · 자기소개서 밖에 필수로 받는 서류다.
    """

    recruitment_id: UUID
    status: RecruitmentStatus
    content: PostingContent
    stages: list[StageDraft]
    required_extras: list[DocumentType]


class PostingSuggestion(ContractModel):
    """Posting Agent가 만든 수정안 (posting.PostingSuggestion). HR이 적용하기 전까지 공고를 바꾸지 않는다 (FR-03).

    stages · required_extras는 바꾸지 않았으면 null이다. changed_fields는 화면이 바뀐 칸을 표시할 때 쓰는 칸 이름이다
    (본문 칸은 PostingContent의 JSON 이름, 전형 절차는 stages, 필수 제출 서류는 requiredDocuments).
    """

    content: PostingContent
    stages: list[StageDraft] | None
    required_extras: list[DocumentType] | None
    changed_fields: list[str]


class RevisionResult(ContractModel):
    """PostingAgent.Result. reply는 Chat에 보여 줄 답이고, 되묻거나 처리할 수 없는 요청이면 suggestion이 null이다."""

    reply: str
    suggestion: PostingSuggestion | None
