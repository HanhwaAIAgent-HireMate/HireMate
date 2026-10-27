"""backend RootAgent 연동: POST /agents/root/{plan, applied, history, forget, forgetStage}.

요청 본문은 Java 메서드의 매개변수 이름을 키로 한 JSON이다. 대화방은 체크포인터에 둔다 (기획 15절).
plan만 SSE로 응답한다. 진행(status, item)을 낸 뒤 마지막 done 이벤트에 ChatPlan을 담는다.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent

from hiremate_ai.agents.root.graph import RootThread, apply_plan, stream_plan
from hiremate_ai.agents.root.memory import SaverDep, forget_stage, forget_thread
from hiremate_ai.agents.root.toolkit import ToolkitDep
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import ChatApplied, ChatContext, ChatHistoryTurn, ChatPlan
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmDep

router = APIRouter(prefix="/agents/root", tags=["root"])


class PlanRequest(ContractModel):
    context: ChatContext


class ThreadRequest(ContractModel):
    thread_id: str


class AppliedRequest(ContractModel):
    applied: ChatApplied


class Applied(ContractModel):
    applied: bool


class StageRequest(ContractModel):
    stage_id: UUID


class Deleted(ContractModel):
    deleted: int


@router.post("/plan", response_class=EventSourceResponse)
async def plan(
    request: PlanRequest, llm: LlmDep, saver: SaverDep, toolkit: ToolkitDep
) -> AsyncIterator[ServerSentEvent]:
    context = request.context
    if not context.thread_id:
        # 끝난 전형: 대화방을 만들지 않는다 (대화는 전형 종료까지만 보관)
        events = stream_plan(llm, context, toolkit)
    else:
        thread = RootThread(id=context.thread_id, company_id=context.company.company_id, stage_id=context.stage_id)
        events = stream_plan(llm, context, toolkit, saver=saver, thread=thread)
    async for name, data in events:
        # 계약 JSON(camelCase)을 그대로 보낸다
        yield ServerSentEvent(event=name, raw_data=data.model_dump_json(by_alias=True))


@router.post("/applied")
async def applied(request: AppliedRequest, llm: LlmDep, saver: SaverDep) -> Applied:
    return Applied(applied=await apply_plan(llm, saver, request.applied))


@router.post("/history")
async def history(request: ThreadRequest, saver: SaverDep) -> list[ChatHistoryTurn]:
    turns = await _turns(saver, request.thread_id)
    return [
        ChatHistoryTurn(
            message=turn["message"],
            plan=ChatPlan.model_validate(turn["plan"]),
            total=turn["total"],
            mentions=[UUID(application_id) for application_id in turn.get("mentions", [])],
            steps=turn.get("steps", []),
            seconds=turn.get("seconds"),
        )
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
