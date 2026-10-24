"""Root Agent 흐름 (LangGraph). 차단 → 대상 확인 · 분류 → 경로별 계획 → 턴 기록.

지원자를 직접 고르거나 상태를 바꾸지 않는다. ChatContext는 그래프 상태가 아니라 실행 context로 넘겨
지원자 문서 본문이 대화방 상태에 남지 않는다. 대화방(thread)을 주면 체크포인터가 턴 기록을 이어 보관한다.
처리 중에는 노드가 단계 문구와 검증된 항목을 custom 스트림으로 낸다 (stream_plan).
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
from hiremate_ai.agents.root.answer import plan_answer, plan_questions
from hiremate_ai.agents.root.edit import plan_edit
from hiremate_ai.agents.root.find import plan_find
from hiremate_ai.agents.root.progress import writer_progress
from hiremate_ai.agents.root.route import (
    COMPARE_NEEDS_TWO,
    NO_PREVIOUS,
    NOT_UNDERSTOOD,
    RootRoute,
    asks_comparison,
    classify,
    precheck,
    refers_previous,
    says_previous,
)
from hiremate_ai.agents.root.targets import Targets, checked, resolve
from hiremate_ai.agents.root.toolkit import RootToolkit, default_toolkit
from hiremate_ai.agents.root.turns import Turn, next_result, recall, remember, remembered, turn_of
from hiremate_ai.agents.root.types import ChatContext, ChatItem, ChatPlan, ChatStatus, EditAction, Intent
from hiremate_ai.config import settings
from hiremate_ai.contract import StageType
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient


class RootState(TypedDict, total=False):
    # 이번 턴의 값. 턴마다 None으로 다시 시작한다
    targets: Targets | None
    route: RootRoute | None
    plan: ChatPlan | None
    # 대화방에 쌓이는 최근 턴 기록
    turns: list[Turn]
    # 지금 결과 목록(찾기 · 면접 질문 대상, 만든 적이 없으면 None)과 직전에 다룬 지원자. 지원자 id 글자다
    result: list[str] | None
    subject: list[str]


@dataclass(frozen=True)
class RootThread:
    """대화방. id는 backend가 기업 · 전형 · 담당자로 만든다. metadata로 전형 단위 삭제를 한다."""

    id: str
    company_id: UUID
    stage_id: UUID


# 이번 턴의 값을 지우고 시작하는 입력. 대화방을 이어 쓸 때 앞 턴의 계획이 남지 않게 한다
_NEW_TURN: RootState = {"targets": None, "route": None, "plan": None}

# 처리 중 화면에 보이는 단계 문구. 분류가 끝나고 경로로 갈 때만 ROUTED를 낸다
CHECKING = "요청을 확인하고 있어요"
ROUTED = {"ANSWER": "분석 요청으로 처리해요", "FIND": "찾기 요청으로 처리해요", "EDIT": "선택 지원자를 바꾸고 있어요"}

# (이벤트 이름, data). 마지막은 done 하나다
type PlanEvent = tuple[Literal["status", "item", "done"], ChatStatus | ChatItem | ChatPlan]


def build_root_graph(
    llm: LlmClient, toolkit: RootToolkit | None = None, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[RootState, ChatContext, RootState, RootState]:
    """노드는 llm으로 모델을 부른다. 테스트는 FakeLlm을 넘긴다. 실행할 때 context에 ChatContext를 준다.

    toolkit을 주지 않으면 ChatContext 문서로 동작하는 임시 도구를 쓴다.
    """
    tools = toolkit or default_toolkit()

    def guard(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        context = runtime.context
        writer_progress(runtime.stream_writer).status(CHECKING)
        if blocked_attribute(context.message):
            return {"plan": ChatPlan.answer(Intent.BLOCKED, BLOCKED_REPLY)}
        return {"targets": resolve(context)}

    async def route(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        context = runtime.context
        targets, turns = _targets(state), state.get("turns") or []
        try:
            decided = await classify(llm, context, targets, turns)
        except LlmOutputError:
            return {"plan": ChatPlan.answer(Intent.CLARIFY, NOT_UNDERSTOOD)}
        early = precheck(decided, context)
        if early:
            return {"route": decided, "plan": early}
        needs_targets = decided.kind == "ANSWER" or decided.edit in (EditAction.ADD, EditAction.REMOVE)
        if needs_targets and not targets.rows and not targets.ambiguous:
            # 대상은 코드가 정한다: @멘션 · 이름 → 체크한 지원자 → 앞 대화.
            # 앞 대화는 순서나 앞 대화를 가리키는 말이 있으면 체크한 지원자보다 먼저다.
            # 앞 대화에 가리킬 지원자가 없으면 문장이 앞 대화를 가리킬 때만 되묻고, 아니면 대상 없이 간다
            implied = False
            if refers_previous(decided, context):
                ids = remembered(state.get("result"), state.get("subject") or [], decided.previous_ref)
                rows = recall(context, ids, decided.ordinal)
                said = says_previous(decided, context.message)
                if not rows and said:
                    return {"route": decided, "plan": ChatPlan.answer(Intent.CLARIFY, NO_PREVIOUS)}
                implied = bool(rows) and not said
            else:
                rows = checked(context)
            targets = Targets(rows=rows, ambiguous=[], implied=implied)
        if decided.kind == "ANSWER" and asks_comparison(decided, context.message) and len(targets.rows) < 2:
            plan = ChatPlan.answer(Intent.CLARIFY, COMPARE_NEEDS_TWO)
            return {"route": decided, "targets": targets, "plan": plan}
        writer_progress(runtime.stream_writer).status(ROUTED.get(decided.kind, ROUTED["ANSWER"]))
        return {"route": decided, "targets": targets}

    def edit(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        return {"plan": plan_edit(_route(state), runtime.context, _targets(state))}

    async def find(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        progress = writer_progress(runtime.stream_writer)
        return {"plan": await plan_find(llm, _route(state), runtime.context, tools, progress=progress)}

    async def answer(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        context = runtime.context
        decided, targets, turns = _route(state), _targets(state), state.get("turns") or []
        progress = writer_progress(runtime.stream_writer)
        if decided.interview_questions and context.stage_type is StageType.INTERVIEW:
            return {"plan": await plan_questions(llm, decided, context, targets, tools, turns, progress=progress)}
        return {"plan": await plan_answer(llm, decided, context, targets, tools, turns, progress=progress)}

    def record(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        """턴을 남기고 이번 턴의 값을 비운다. 대화방에는 JSON 값(턴 기록)만 남아 라이브러리를 올려도 다시 읽힌다."""
        decided, plan = state.get("route"), _plan(state)
        kind = decided.kind if decided else ""
        turn = turn_of(runtime.context, state.get("targets"), plan, kind)
        return {
            "turns": remember(state.get("turns") or [], turn, settings.root_memory_turns),
            "result": next_result(state.get("result"), kind, decided.mode if decided else None, plan),
            "subject": turn["targets"] or state.get("subject") or [],
            **_NEW_TURN,
        }

    def after_guard(state: RootState) -> str:
        return "record" if state.get("plan") is not None else "route"

    def after_route(state: RootState) -> str:
        if state.get("plan") is not None:
            return "record"
        return {"EDIT": "edit", "FIND": "find"}.get(_route(state).kind, "answer")

    graph: StateGraph[RootState, ChatContext, RootState, RootState] = StateGraph(RootState, context_schema=ChatContext)
    graph.add_node("guard", guard)
    graph.add_node("route", route)
    graph.add_node("edit", edit)
    graph.add_node("find", find)
    graph.add_node("answer", answer)
    graph.add_node("record", record)
    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", after_guard)
    graph.add_conditional_edges("route", after_route)
    for node in ("edit", "find", "answer"):
        graph.add_edge(node, "record")
    graph.add_edge("record", END)
    return graph.compile(checkpointer=checkpointer)


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


def _targets(state: RootState) -> Targets:
    targets = state.get("targets")
    if targets is None:
        raise TypeError("대상 확인 전에 경로를 탔다")
    return targets


def _route(state: RootState) -> RootRoute:
    decided = state.get("route")
    if decided is None:
        raise TypeError("분류 전에 경로를 탔다")
    return decided


def _plan(state: RootState) -> ChatPlan:
    plan = state.get("plan")
    if plan is None:
        raise TypeError("계획 없이 턴을 남기려 했다")
    return plan
