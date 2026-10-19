"""backend RootAgent.plan 연동: POST /agents/root/plan. 요청 본문은 {"context": ChatContext}, 응답은 ChatPlan이다."""

from fastapi import APIRouter

from hiremate_ai.agents.root.graph import run_plan
from hiremate_ai.agents.root.types import ChatContext, ChatPlan
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmDep

router = APIRouter(prefix="/agents/root", tags=["root"])


class PlanRequest(ContractModel):
    context: ChatContext


@router.post("/plan")
async def plan(request: PlanRequest, llm: LlmDep) -> ChatPlan:
    return await run_plan(llm, request.context)
