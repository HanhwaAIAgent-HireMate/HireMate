"""Posting Agent. 공고 초안과 수정안(바뀐 부분만)을 만든다."""

from hiremate_ai.agents.generation.posting.reviser import revise_posting
from hiremate_ai.agents.generation.posting.types import (
    PostingDraftContext,
    PostingSuggestion,
    RecruitmentStatus,
    RevisionResult,
    StageDraft,
)

__all__ = [
    "PostingDraftContext",
    "PostingSuggestion",
    "RecruitmentStatus",
    "RevisionResult",
    "StageDraft",
    "revise_posting",
]
