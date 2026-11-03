"""공고 Agent 연동: 본문 수정 /agents/posting/revise, 포스터 대화 /agents/posting/design.

요청 본문은 Java 메서드의 매개변수 이름을 키로 한 JSON이다.
"""

from fastapi import APIRouter
from pydantic import Field

from hiremate_ai.agents.generation.posting import design_poster
from hiremate_ai.agents.generation.posting.poster import PosterContext, PosterProposal
from hiremate_ai.agents.generation.posting.reviser import revise_posting
from hiremate_ai.agents.generation.posting.types import PostingDraftContext, PostingFocus, RevisionResult
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmDep
from hiremate_ai.ncs_search.reference import NcsDep

router = APIRouter(prefix="/agents/posting", tags=["posting"])


class ReviseRequest(ContractModel):
    """PostingAgent.revise(posting, writingStyle, request, focus)의 매개변수. 줄을 고르지 않으면 focus가 null이다."""

    posting: PostingDraftContext
    writing_style: str
    request: str
    focus: PostingFocus | None = None


@router.post("/revise")
async def revise(body: ReviseRequest, llm: LlmDep, ncs: NcsDep) -> RevisionResult:
    return await revise_posting(llm, body.posting, body.writing_style, body.request, body.focus, ncs=ncs)


class DesignRequest(ContractModel):
    context: PosterContext
    request: str = Field(min_length=1, max_length=1000)


@router.post("/design")
async def design(body: DesignRequest, llm: LlmDep) -> PosterProposal:
    return await design_poster(llm, body.context, body.request)
