"""Posting Agent. 공고 초안과 수정안(바뀐 부분만)을 만들고, 자격 요건 · 우대 사항 중 '중요' 항목을 추천한다."""

from hiremate_ai.agents.generation.posting.important import ImportantAdvice, ImportantItem, recommend_important
from hiremate_ai.agents.generation.posting.reviser import revise_posting
from hiremate_ai.agents.generation.posting.types import (
    PostingDraftContext,
    PostingSuggestion,
    RecruitmentStatus,
    RevisionResult,
    StageDraft,
)

__all__ = [
    "ImportantAdvice",
    "ImportantItem",
    "PostingDraftContext",
    "PostingSuggestion",
    "RecruitmentStatus",
    "RevisionResult",
    "StageDraft",
    "recommend_important",
    "revise_posting",
]
