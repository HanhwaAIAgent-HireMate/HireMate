"""backend PostingAgent · PostingCriteriaAgent 연동: POST /agents/posting/{revise, draftCriterion, recommendImportant}.

요청 본문은 Java 메서드의 매개변수 이름을 키로 한 JSON이다.
"""

from fastapi import APIRouter

from hiremate_ai.agents.generation.posting.criteria import CriterionDraft, draft_criterion
from hiremate_ai.agents.generation.posting.important import ImportantAdvice, recommend_important
from hiremate_ai.agents.generation.posting.reviser import SourcedItem, revise_posting
from hiremate_ai.agents.generation.posting.types import PostingDraftContext, RevisionResult
from hiremate_ai.contract import ContractModel, CriterionCategory, PostingContent
from hiremate_ai.llm.client import LlmDep

router = APIRouter(prefix="/agents/posting", tags=["posting"])


class ReviseRequest(ContractModel):
    """PostingAgent.revise(posting, writingStyle, request)의 매개변수."""

    posting: PostingDraftContext
    writing_style: str
    request: str


@router.post("/revise")
async def revise(body: ReviseRequest, llm: LlmDep) -> RevisionResult:
    return await revise_posting(llm, body.posting, body.writing_style, body.request)


class DraftCriterionRequest(ContractModel):
    """PostingCriteriaAgent.draftCriterion(posting, category, text, ncsUnitCode)의 매개변수."""

    posting: PostingContent
    category: CriterionCategory
    text: str
    ncs_unit_code: str | None


@router.post("/draftCriterion")
async def draft(body: DraftCriterionRequest, llm: LlmDep) -> CriterionDraft:
    return await draft_criterion(llm, body.posting, body.category, body.text, body.ncs_unit_code)


class RecommendImportantRequest(ContractModel):
    """PostingCriteriaAgent.recommendImportant(posting)의 매개변수."""

    posting: PostingContent


@router.post("/recommendImportant")
async def important(body: RecommendImportantRequest, llm: LlmDep) -> ImportantAdvice:
    lists = {
        "qualifications": [SourcedItem(text=text, sources=[]) for text in body.posting.qualifications],
        "preferred": [SourcedItem(text=text, sources=[]) for text in body.posting.preferred],
    }
    return await recommend_important(llm, body.posting, lists)
