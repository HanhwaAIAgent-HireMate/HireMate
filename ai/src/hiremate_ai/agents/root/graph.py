"""Root Agent 흐름 (LangGraph). 차단 → 대상 확인 · 분류 → 경로별 계획. 지원자를 직접 고르거나 상태를 바꾸지 않는다.

ChatContext는 그래프 상태가 아니라 실행 context로 넘긴다. 지원자 문서 본문이 상태(나중에 대화 기록)에 남지 않는다.
"""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from hiremate_ai.agents.guardrails import BLOCKED_REPLY, blocked_attribute
from hiremate_ai.agents.root.answer import plan_answer, plan_questions
from hiremate_ai.agents.root.edit import plan_edit
from hiremate_ai.agents.root.find import plan_find
from hiremate_ai.agents.root.route import NOT_UNDERSTOOD, RootRoute, classify, precheck
from hiremate_ai.agents.root.targets import Targets, resolve
from hiremate_ai.agents.root.toolkit import RootToolkit, default_toolkit
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Intent
from hiremate_ai.contract import StageType
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient


class RootState(TypedDict, total=False):
    targets: Targets
    route: RootRoute
    plan: ChatPlan


def build_root_graph(
    llm: LlmClient, toolkit: RootToolkit | None = None
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
        try:
            decided = await classify(llm, context, state["targets"])
        except LlmOutputError:
            return {"plan": ChatPlan.answer(Intent.CLARIFY, NOT_UNDERSTOOD)}
        early = precheck(decided, context)
        return {"route": decided, "plan": early} if early else {"route": decided}

    def edit(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        return {"plan": plan_edit(state["route"], runtime.context, state["targets"])}

    async def find(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        return {"plan": await plan_find(llm, state["route"], runtime.context, tools)}

    async def answer(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        context = runtime.context
        route, targets = state["route"], state["targets"]
        if route.interview_questions and context.stage_type is StageType.INTERVIEW:
            return {"plan": await plan_questions(llm, route, context, targets, tools)}
        return {"plan": await plan_answer(llm, route, context, targets, tools)}

    def after_guard(state: RootState) -> str:
        return END if "plan" in state else "route"

    def after_route(state: RootState) -> str:
        if "plan" in state:
            return END
        return {"EDIT": "edit", "FIND": "find"}.get(state["route"].kind, "answer")

    graph: StateGraph[RootState, ChatContext, RootState, RootState] = StateGraph(RootState, context_schema=ChatContext)
    graph.add_node("guard", guard)
    graph.add_node("route", route)
    graph.add_node("edit", edit)
    graph.add_node("find", find)
    graph.add_node("answer", answer)
    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", after_guard)
    graph.add_conditional_edges("route", after_route)
    graph.add_edge("edit", END)
    graph.add_edge("find", END)
    graph.add_edge("answer", END)
    return graph.compile()


async def run_plan(llm: LlmClient, context: ChatContext, toolkit: RootToolkit | None = None) -> ChatPlan:
    state: dict[str, Any] = await build_root_graph(llm, toolkit).ainvoke({}, context=context)
    plan = state["plan"]
    if not isinstance(plan, ChatPlan):
        raise TypeError(f"Root 그래프가 계획을 내지 않았다: {state.keys()}")
    return plan
