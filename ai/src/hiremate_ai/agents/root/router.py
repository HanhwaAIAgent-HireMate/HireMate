"""backend RootAgent 연동: POST /agents/root/{plan, applied, history, forget, title}.

요청 본문은 Java 메서드의 매개변수 이름을 키로 한 JSON이다. 대화방은 체크포인터에 둔다 (기획 15절).
plan만 SSE로 응답한다. 진행(status, item)을 낸 뒤 마지막 done 이벤트에 ChatPlan을 담는다.
backend PosterAgent.design은 POST /agents/posting/design으로 공고 디자인 화면의 Root(poster.py)를 부른다.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import Field

from hiremate_ai.agents.generation.posting.poster import PosterContext, PosterProposal
from hiremate_ai.agents.root.graph import RootThread, apply_plan, stream_plan
from hiremate_ai.agents.root.memory import SaverDep, forget_thread
from hiremate_ai.agents.root.poster import plan_poster
from hiremate_ai.agents.root.title import make_title
from hiremate_ai.agents.root.toolkit import ToolkitDep
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import ChatApplied, ChatAsker, ChatContext, ChatHistoryTurn, ChatPlan
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmDep

router = APIRouter(prefix="/agents/root", tags=["root"])
# backend는 공고 Agent 경로로 부르지만 처리는 Root가 한다. 공고 Agent가 Root를 import하지 않게 여기에 둔다.
poster_router = APIRouter(prefix="/agents/posting", tags=["posting"])


class PlanRequest(ContractModel):
    context: ChatContext


class ThreadRequest(ContractModel):
    thread_id: str


class AppliedRequest(ContractModel):
    applied: ChatApplied


class Applied(ContractModel):
    applied: bool


class Deleted(ContractModel):
    deleted: int


class TitleRequest(ContractModel):
    message: str
    reply: str


class Title(ContractModel):
    title: str | None


@router.post("/plan", response_class=EventSourceResponse)
async def plan(
    request: PlanRequest, llm: LlmDep, saver: SaverDep, toolkit: ToolkitDep
) -> AsyncIterator[ServerSentEvent]:
    context = request.context
    if not context.thread_id:
        # 대화방 id가 없으면(Studio, 평가) 대화를 남기지 않고 답한다
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
            asker=_asker(turn.get("asker")),
        )
        for turn in turns
    ]


@router.post("/forget")
async def forget(request: ThreadRequest, saver: SaverDep) -> Deleted:
    exists = await saver.aget_tuple({"configurable": {"thread_id": request.thread_id}}) is not None
    await forget_thread(saver, request.thread_id)
    return Deleted(deleted=int(exists))


@router.post("/title")
async def title(request: TitleRequest, llm: LlmDep) -> Title:
    """탭의 첫 대화로 탭 이름을 짓는다. 만들지 못하면 title이 null이다."""
    return Title(title=await make_title(llm, request.message, request.reply))


class DesignRequest(ContractModel):
    context: PosterContext
    request: str = Field(min_length=1, max_length=1000)


@poster_router.post("/design")
async def design(body: DesignRequest, llm: LlmDep) -> PosterProposal:
    return await plan_poster(llm, body.context, body.request)


async def _turns(saver: Any, thread_id: str) -> list[Turn]:
    saved = await saver.aget_tuple({"configurable": {"thread_id": thread_id}})
    if saved is None:
        return []
    turns: list[Turn] = saved.checkpoint["channel_values"].get("turns", [])
    return turns


def _asker(saved: dict[str, str] | None) -> ChatAsker | None:
    return ChatAsker(member_id=UUID(saved["member_id"]), name=saved["name"]) if saved else None
