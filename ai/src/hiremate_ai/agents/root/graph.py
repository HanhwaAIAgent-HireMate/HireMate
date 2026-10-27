"""Root 그래프. 요청 차단, ReAct 도구 루프, 검증된 결과 기록을 연결한다.

문서와 도구 실행 상태는 실행 context에만 두고 대화방에는 최근 질문과 검증한 결과만 보관한다.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, TypedDict, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from hiremate_ai.agents.guardrails import BLOCKED_REPLY, blocked_attribute
from hiremate_ai.agents.root.agent import run_agent
from hiremate_ai.agents.root.progress import writer_progress
from hiremate_ai.agents.root.toolkit import RootToolkit, default_toolkit
from hiremate_ai.agents.root.turns import Turn, next_result, remember, turn_of, update_turn
from hiremate_ai.agents.root.types import (
    ChatApplied,
    ChatContext,
    ChatItem,
    ChatPlan,
    ChatStatus,
    EditAction,
    Intent,
    SelectionMode,
)
from hiremate_ai.config import settings
from hiremate_ai.llm.client import LlmClient


class RootState(TypedDict, total=False):
    plan: ChatPlan | None
    kind: str
    mode: SelectionMode | None
    turns: list[Turn]
    result: list[str] | None
    subject: list[str]


@dataclass(frozen=True)
class RootThread:
    """backend가 인증한 기업, 전형과 담당자로 만든 대화방."""

    id: str
    company_id: UUID
    stage_id: UUID


_NEW_TURN: RootState = {"plan": None, "kind": "", "mode": None}
CHECKING = "요청을 확인하고 있어요"
type PlanEvent = tuple[Literal["status", "item", "done"], ChatStatus | ChatItem | ChatPlan]


def build_root_graph(
    llm: LlmClient,
    toolkit: RootToolkit | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    *,
    context_schema: type[ChatContext] = ChatContext,
) -> CompiledStateGraph[RootState, ChatContext, RootState, RootState]:
    """하나의 도구 루프가 맥락을 해석한다. 그래프는 의미별 실행 경로를 정하지 않는다."""
    tools = toolkit or default_toolkit()

    def guard(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        writer_progress(runtime.stream_writer).status(CHECKING)
        if blocked_attribute(runtime.context.message):
            return {"plan": ChatPlan.answer(Intent.BLOCKED, BLOCKED_REPLY)}
        return {}

    async def agent(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        progress = writer_progress(runtime.stream_writer)
        finished = await run_agent(
            llm,
            runtime.context,
            tools,
            state.get("turns") or [],
            state.get("result"),
            state.get("subject") or [],
            progress=progress,
        )
        for item in finished.plan.items:
            progress.item(item)
        return {"plan": finished.plan, "kind": finished.kind, "mode": finished.mode}

    def record(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        plan = state.get("plan")
        if plan is None:
            raise TypeError("검증된 최종 명령 없이 턴을 남기려 했다")
        kind = state.get("kind") or ""
        turn = turn_of(runtime.context, None, plan, kind)
        mode = state.get("mode")
        turn["mode"] = mode.value if mode is not None else None
        turn["result_before"] = state.get("result")
        turn["subject_before"] = state.get("subject") or []
        return {
            "turns": remember(state.get("turns") or [], turn, settings.root_memory_turns),
            "result": next_result(state.get("result"), kind, state.get("mode"), plan),
            "subject": turn["targets"] or state.get("subject") or [],
            **_NEW_TURN,
        }

    def after_guard(state: RootState) -> Literal["record", "agent"]:
        return "record" if state.get("plan") is not None else "agent"

    graph: StateGraph[RootState, ChatContext, RootState, RootState] = StateGraph(
        RootState, context_schema=context_schema
    )
    graph.add_node("guard", guard)
    graph.add_node("agent", agent)
    graph.add_node("record", record)
    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", after_guard)
    graph.add_edge("agent", "record")
    graph.add_edge("record", END)
    return graph.compile(checkpointer=checkpointer)


async def apply_plan(llm: LlmClient, saver: BaseCheckpointSaver[Any], applied: ChatApplied) -> bool:
    """업무 서버의 최종 응답으로 기존 턴을 보정한다. 모델이나 업무 도구를 실행하지 않는다."""
    graph = build_root_graph(llm, checkpointer=saver)
    snapshot = await graph.aget_state({"configurable": {"thread_id": applied.thread_id}})
    if not snapshot.values or snapshot.next:
        return False
    turns: list[Turn] = snapshot.values.get("turns") or []
    previous = applied.previous.model_dump(mode="json")
    matches = [
        index
        for index, turn in enumerate(turns)
        if turn["message"] == applied.message and "proposed_plan" not in turn and turn["plan"] == previous
    ]
    if not matches:
        return any(
            turn["message"] == applied.message
            and turn.get("proposed_plan") == previous
            and turn["plan"] == applied.plan.model_dump(mode="json")
            for turn in turns
        )
    if len(matches) != 1:
        return False
    index = matches[0]
    turn = turns[index]
    allowed = _plan_candidates(applied.previous)
    if (
        applied.previous.intent is Intent.EDIT
        and applied.previous.edit in (EditAction.CLEAR, EditAction.RESTORE)
        and applied.plan.intent is Intent.EDIT
        and applied.plan.edit is applied.previous.edit
    ):
        # 이 명령은 계획에 대상을 넣지 않고 업무 서버가 실제 변경한 대상을 돌려준다.
        allowed.update(applied.plan.targets)
    if not _plan_candidates(applied.plan) <= allowed:
        return False
    updated = list(turns)
    updated[index] = update_turn(turn, applied.plan)
    updated[index]["proposed_plan"] = previous
    start = index if "result_before" in turn and "subject_before" in turn else 0
    result = turns[start].get("result_before")
    subject = turns[start].get("subject_before") or []
    for position in range(start, len(updated)):
        saved_turn = updated[position]
        saved_turn = {**saved_turn, "result_before": result, "subject_before": subject}
        updated[position] = saved_turn
        plan = ChatPlan.model_validate(saved_turn["plan"])
        saved_mode = saved_turn.get("mode", plan.mode)
        mode = SelectionMode(saved_mode) if saved_mode is not None else None
        result = next_result(result, saved_turn["kind"], mode, plan)
        subject = saved_turn["targets"] or subject
    metadata: dict[str, Any] = dict(snapshot.metadata or {})
    await graph.aupdate_state(
        {
            **snapshot.config,
            "metadata": {key: metadata[key] for key in ("stage_id", "company_id") if key in metadata},
        },
        {"turns": updated, "result": result, "subject": subject},
        as_node="record",
    )
    return True


def _plan_candidates(plan: ChatPlan) -> set[UUID]:
    return (
        set(plan.targets)
        | set(plan.question_targets)
        | set(plan.question_focus)
        | set(plan.question_memos)
        | {item.application_id for item in plan.items if item.application_id is not None}
    )


async def run_plan(
    llm: LlmClient,
    context: ChatContext,
    toolkit: RootToolkit | None = None,
    *,
    saver: BaseCheckpointSaver[Any] | None = None,
    thread: RootThread | None = None,
) -> ChatPlan:
    """계획을 낸다. saver와 thread를 주면 그 대화방에 턴을 남기고 앞 턴 기록을 이어 쓴다."""
    async for name, data in stream_plan(llm, context, toolkit, saver=saver, thread=thread):
        if name == "done" and isinstance(data, ChatPlan):
            return data
    raise TypeError("Root 그래프가 계획을 내지 않았다")


async def stream_plan(
    llm: LlmClient,
    context: ChatContext,
    toolkit: RootToolkit | None = None,
    *,
    saver: BaseCheckpointSaver[Any] | None = None,
    thread: RootThread | None = None,
) -> AsyncIterator[PlanEvent]:
    """진행 알림(status, item)을 내고, 턴을 남긴 뒤 마지막에 계획(done)을 낸다."""
    remembering = saver is not None and thread is not None
    graph = build_root_graph(llm, toolkit, saver if remembering else None)
    config: RunnableConfig | None = None
    if remembering and thread is not None:
        config = {
            "configurable": {"thread_id": thread.id},
            "metadata": {"stage_id": str(thread.stage_id), "company_id": str(thread.company_id)},
        }
    state: dict[str, Any] = {}
    # 여러 모드로 받으면 (모드, 값)이 온다. custom은 노드가 낸 진행 알림, values는 단계마다의 상태다
    async for streamed in graph.astream(_NEW_TURN, config=config, context=context, stream_mode=["custom", "values"]):
        mode, chunk = cast(tuple[str, Any], streamed)
        if mode == "custom":
            yield chunk
        else:
            state = chunk
    turns: list[Turn] = state.get("turns") or []
    if not turns:
        raise TypeError(f"Root 그래프가 턴을 남기지 않았다: {state.keys()}")
    yield ("done", ChatPlan.model_validate(turns[-1]["plan"]))
