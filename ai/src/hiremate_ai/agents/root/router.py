"""backend RootAgent 연동: POST /agents/root/{plan, history, forget, forgetStage}.

요청 본문은 Java 메서드의 매개변수 이름을 키로 한 JSON이다. 대화방은 체크포인터에 둔다 (기획 15절).
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter

from hiremate_ai.agents.root.graph import RootThread, run_plan
from hiremate_ai.agents.root.memory import SaverDep, forget_stage, forget_thread
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import ChatContext, ChatHistoryTurn, ChatPlan
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmDep

router = APIRouter(prefix="/agents/root", tags=["root"])


class PlanRequest(ContractModel):
    context: ChatContext


class ThreadRequest(ContractModel):
    thread_id: str


class StageRequest(ContractModel):
    stage_id: UUID


class Deleted(ContractModel):
    deleted: int


@router.post("/plan")
async def plan(request: PlanRequest, llm: LlmDep, saver: SaverDep) -> ChatPlan:
    context = request.context
    if not context.thread_id:
        # 끝난 전형: 대화방을 만들지 않는다 (대화는 전형 종료까지만 보관)
        return await run_plan(llm, context)
    thread = RootThread(id=context.thread_id, company_id=context.company.company_id, stage_id=context.stage_id)
    return await run_plan(llm, context, saver=saver, thread=thread)


@router.post("/history")
async def history(request: ThreadRequest, saver: SaverDep) -> list[ChatHistoryTurn]:
    turns = await _turns(saver, request.thread_id)
    return [
        ChatHistoryTurn(message=turn["message"], plan=ChatPlan.model_validate(turn["plan"]), total=turn["total"])
        for turn in turns
    ]


@router.post("/forget")
async def forget(request: ThreadRequest, saver: SaverDep) -> Deleted:
    exists = await saver.aget_tuple({"configurable": {"thread_id": request.thread_id}}) is not None
    await forget_thread(saver, request.thread_id)
    return Deleted(deleted=int(exists))


@router.post("/forgetStage")
async def forget_stage_threads(request: StageRequest, saver: SaverDep) -> Deleted:
    return Deleted(deleted=await forget_stage(saver, str(request.stage_id)))


async def _turns(saver: Any, thread_id: str) -> list[Turn]:
    saved = await saver.aget_tuple({"configurable": {"thread_id": thread_id}})
    if saved is None:
        return []
    turns: list[Turn] = saved.checkpoint["channel_values"].get("turns", [])
    return turns
