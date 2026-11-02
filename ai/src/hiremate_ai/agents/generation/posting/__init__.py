"""Posting Agent. 글 공고 초안·수정안과 포스터 디자인·대화 처리를 제공한다."""

from hiremate_ai.agents.generation.posting.poster import propose_poster
from hiremate_ai.agents.generation.posting.poster_chat import design_poster
from hiremate_ai.agents.generation.posting.reviser import revise_posting
from hiremate_ai.agents.generation.posting.types import (
    PostingDraftContext,
    PostingFocus,
    PostingSuggestion,
    RecruitmentStatus,
    RevisionResult,
    StageDraft,
)

__all__ = [
    "PostingDraftContext",
    "PostingFocus",
    "PostingSuggestion",
    "RecruitmentStatus",
    "RevisionResult",
    "StageDraft",
    "revise_posting",
    "propose_poster",
    "design_poster",
]
