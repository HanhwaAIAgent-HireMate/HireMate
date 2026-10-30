"""backend PostingAgent 연동: POST /agents/posting/revise.

요청 본문은 Java 메서드의 매개변수 이름을 키로 한 JSON이다.
"""

from fastapi import APIRouter

from hiremate_ai.agents.generation.posting.reviser import revise_posting
from hiremate_ai.agents.generation.posting.types import PostingDraftContext, PostingFocus, RevisionResult
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmDep

router = APIRouter(prefix="/agents/posting", tags=["posting"])


class ReviseRequest(ContractModel):
    """PostingAgent.revise(posting, writingStyle, request, focus)의 매개변수. 줄을 고르지 않으면 focus가 null이다."""

    posting: PostingDraftContext
    writing_style: str
    request: str
    focus: PostingFocus | None = None


@router.post("/revise")
async def revise(body: ReviseRequest, llm: LlmDep) -> RevisionResult:
    return await revise_posting(llm, body.posting, body.writing_style, body.request, body.focus)
