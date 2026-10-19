"""Root Agent 흐름 (LangGraph). 차단 → 대상 확인 · 분류 → 경로별 계획. 지원자를 직접 고르거나 상태를 바꾸지 않는다."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from hiremate_ai.agents.guardrails import BLOCKED_REPLY, blocked_attribute
from hiremate_ai.agents.root.edit import plan_edit
from hiremate_ai.agents.root.route import NOT_UNDERSTOOD, RootRoute, classify, precheck
from hiremate_ai.agents.root.targets import Targets, resolve
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Intent
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient

# 찾기(A)와 분석 · 생성(B)을 붙이기 전까지의 답
PENDING = "지원자 찾기와 분석은 아직 준비 중이에요. 선택 지원자 넣기, 빼기, 비우기, 되돌리기는 지금 쓸 수 있어요."


class RootState(TypedDict, total=False):
    context: ChatContext
    targets: Targets
    route: RootRoute
    plan: ChatPlan


def build_root_graph(llm: LlmClient) -> CompiledStateGraph[RootState, None, RootState, RootState]:
    """노드는 llm으로 모델을 부른다. 테스트는 FakeLlm을 넘긴다."""

    def guard(state: RootState) -> RootState:
        context = state["context"]
        if blocked_attribute(context.message):
            return {"plan": ChatPlan.answer(Intent.BLOCKED, BLOCKED_REPLY)}
        return {"targets": resolve(context)}

    async def route(state: RootState) -> RootState:
        context = state["context"]
        try:
            decided = await classify(llm, context, state["targets"])
        except LlmOutputError:
            return {"plan": ChatPlan.answer(Intent.CLARIFY, NOT_UNDERSTOOD)}
        early = precheck(decided, context)
        return {"route": decided, "plan": early} if early else {"route": decided}

    def edit(state: RootState) -> RootState:
        return {"plan": plan_edit(state["route"], state["context"], state["targets"])}

    def pending(state: RootState) -> RootState:
        return {"plan": ChatPlan.answer(Intent.CLARIFY, PENDING)}

    def after_guard(state: RootState) -> str:
        return END if "plan" in state else "route"

    def after_route(state: RootState) -> str:
        if "plan" in state:
            return END
        return "edit" if state["route"].kind == "EDIT" else "pending"

    graph: StateGraph[RootState, None, RootState, RootState] = StateGraph(RootState)
    graph.add_node("guard", guard)
    graph.add_node("route", route)
    graph.add_node("edit", edit)
    graph.add_node("pending", pending)
    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", after_guard)
    graph.add_conditional_edges("route", after_route)
    graph.add_edge("edit", END)
    graph.add_edge("pending", END)
    return graph.compile()


async def run_plan(llm: LlmClient, context: ChatContext) -> ChatPlan:
    state: dict[str, Any] = await build_root_graph(llm).ainvoke({"context": context})
    plan = state["plan"]
    if not isinstance(plan, ChatPlan):
        raise TypeError(f"Root 그래프가 계획을 내지 않았다: {state.keys()}")
    return plan
