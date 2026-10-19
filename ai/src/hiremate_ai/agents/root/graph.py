"""Root Agent 흐름 (LangGraph). 차단 → 대상 확인 · 분류 → 경로별 계획 → 턴 기록.

지원자를 직접 고르거나 상태를 바꾸지 않는다. ChatContext는 그래프 상태가 아니라 실행 context로 넘겨
지원자 문서 본문이 대화방 상태에 남지 않는다. 대화방(thread)을 주면 체크포인터가 턴 기록을 이어 보관한다.
"""

from dataclasses import dataclass
from typing import Any, TypedDict
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
from hiremate_ai.agents.root.route import NO_PREVIOUS, NOT_UNDERSTOOD, RootRoute, classify, precheck
from hiremate_ai.agents.root.targets import Targets, resolve
from hiremate_ai.agents.root.toolkit import RootToolkit, default_toolkit
from hiremate_ai.agents.root.turns import Turn, from_history, remember, turn_of
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Intent
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


@dataclass(frozen=True)
class RootThread:
    """대화방. id는 backend가 기업 · 전형 · 담당자로 만든다. metadata로 전형 단위 삭제를 한다."""

    id: str
    company_id: UUID
    stage_id: UUID


# 이번 턴의 값을 지우고 시작하는 입력. 대화방을 이어 쓸 때 앞 턴의 계획이 남지 않게 한다
_NEW_TURN: RootState = {"targets": None, "route": None, "plan": None}


def build_root_graph(
    llm: LlmClient, toolkit: RootToolkit | None = None, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[RootState, ChatContext, RootState, RootState]:
    """노드는 llm으로 모델을 부른다. 테스트는 FakeLlm을 넘긴다. 실행할 때 context에 ChatContext를 준다.

    toolkit을 주지 않으면 ChatContext 문서로 동작하는 임시 도구를 쓴다.
    """
    tools = toolkit or default_toolkit()

    def guard(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        context = runtime.context
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
        if decided.previous_ref != "none" and not targets.rows:
            # 이름 없이 앞 대화의 지원자를 가리키면 대화방 기록에서 찾는다. 대상은 여전히 코드가 정한다
            rows = from_history(context, turns, decided.previous_ref, decided.ordinal)
            if not rows:
                return {"route": decided, "plan": ChatPlan.answer(Intent.CLARIFY, NO_PREVIOUS)}
            return {"route": decided, "targets": Targets(rows=rows, ambiguous=[])}
        return {"route": decided}

    def edit(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        return {"plan": plan_edit(_route(state), runtime.context, _targets(state))}

    async def find(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        return {"plan": await plan_find(llm, _route(state), runtime.context, tools)}

    async def answer(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        context = runtime.context
        decided, targets = _route(state), _targets(state)
        if decided.interview_questions and context.stage_type is StageType.INTERVIEW:
            return {"plan": await plan_questions(llm, decided, context, targets, tools)}
        return {"plan": await plan_answer(llm, decided, context, targets, tools)}

    def record(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        turn = turn_of(runtime.context, state.get("targets"), _plan(state))
        return {"turns": remember(state.get("turns") or [], turn, settings.root_memory_turns)}

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
    remembering = saver is not None and thread is not None
    graph = build_root_graph(llm, toolkit, saver if remembering else None)
    config: RunnableConfig | None = None
    if remembering and thread is not None:
        config = {
            "configurable": {"thread_id": thread.id},
            "metadata": {"stage_id": str(thread.stage_id), "company_id": str(thread.company_id)},
        }
    state: dict[str, Any] = await graph.ainvoke(_NEW_TURN, config=config, context=context)
    plan = state.get("plan")
    if not isinstance(plan, ChatPlan):
        raise TypeError(f"Root 그래프가 계획을 내지 않았다: {state.keys()}")
    return plan


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
