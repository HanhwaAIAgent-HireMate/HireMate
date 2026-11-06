"""Root 그래프. 요청 차단 → 계획 → (찾기 | 편집 | 면접 질문 | 분석 → 근거 검토 | 고정 답) → 기록.

계획 한 번으로 종류와 대상을 정하고(라우팅), 다음 단계를 미리 알 수 있는 요청은 정해진 흐름으로,
자료를 읽어 봐야 다음 단계를 알 수 있는 요청만 분석 루프로 처리한다. 요청 하나의 모델 호출 예산과 근거 번호표는
저장하지 않는 상태 채널(run)로 노드 사이에 넘기고, 대화방에는 최근 질문과 검증한 결과만 남긴다.
"""

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Any, Literal, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from hiremate_ai.agents.guardrails import blocked_attribute, blocked_reply
from hiremate_ai.agents.root.analysis import (
    AnswerOutput,
    ClarifyOutput,
    FindOutput,
    QuestionsOutput,
    analysis_run,
    run_analysis,
)
from hiremate_ai.agents.root.answer import readable
from hiremate_ai.agents.root.handlers import (
    Handled,
    handle_edit,
    handle_find,
    handle_questions,
    handle_reply,
    handle_report,
    precheck,
)
from hiremate_ai.agents.root.plan import EditPlan, FindPlan, QuestionsPlan, ReportPlan, make_plan
from hiremate_ai.agents.root.progress import StepRecorder, step, writer_progress
from hiremate_ai.agents.root.review import (
    NO_EVIDENCE,
    answer_plan,
    cap_items,
    focus_drafts,
    questions_plan,
    review_items,
)
from hiremate_ai.agents.root.scope import expand_scope
from hiremate_ai.agents.root.state import RootInput, RootOutput, RootRun, RootState
from hiremate_ai.agents.root.toolkit import RootToolkit, default_toolkit
from hiremate_ai.agents.root.turns import Turn, next_result, remember, turn_of, update_turn
from hiremate_ai.agents.root.types import (
    CandidateRow,
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
from hiremate_ai.llm.chat import LlmFailureReason, LlmOutputError, new_model_call_budget, using_model_call_budget
from hiremate_ai.llm.client import LlmClient

__all__ = ["RootState", "RootThread", "apply_plan", "build_root_graph", "run_plan", "stream_plan"]

logger = logging.getLogger(__name__)

CHECKING = "요청을 확인하고 있어요"
REVIEWING = "답변의 근거를 검토하고 있어요"
# 근거 검토 결과. REVIEWING 아래 한 칸 들여 보인다
REVIEWED = "항목 {total}개 중 근거 확인 {ok}개"
REVIEWED_CHECK = ", 확인 필요 {count}개"
REVIEWED_DROPPED = ", 근거가 맞지 않아 뺀 항목 {count}개"
FOCUS_REVIEWED = "면접에서 확인할 점 {count}개를 정했어요"
NO_FOCUS_LEFT = "남은 확인할 점이 없어 요청 문장으로 질문을 만들어요"
NOTHING_EVIDENCED = "근거를 확인한 항목이 없어요"
NOT_FINISHED = "답변을 올바른 형식으로 완성하지 못했어요. 잠시 후 다시 요청해 주세요."
VALIDATION_FAILED = "답변의 근거와 실행 조건을 확인하지 못했어요. 질문을 다시 말씀해 주세요."
BUDGET_EXHAUSTED = "한 번에 확인할 수 있는 처리 한도에 도달했어요. 요청을 나눠 다시 말씀해 주세요."
NOT_IN_STAGE = "현재 전형에서 멘션한 지원자를 찾을 수 없어요. 지원자 목록에서 대상을 골라 다시 말씀해 주세요."
FAILURE_MESSAGES = {
    LlmFailureReason.FORMAT: NOT_FINISHED,
    LlmFailureReason.VALIDATION: VALIDATION_FAILED,
    LlmFailureReason.BUDGET: BUDGET_EXHAUSTED,
}

type PlanEvent = tuple[Literal["status", "item", "done"], ChatStatus | ChatItem | ChatPlan]

_NEW_TURN: RootInput = {"plan": None, "kind": "", "mode": None, "steps": []}


@dataclass(frozen=True)
class RootThread:
    """backend가 인증한 기업, 전형과 담당자로 만든 대화방."""

    id: str
    company_id: UUID
    stage_id: UUID


def build_root_graph(
    llm: LlmClient,
    toolkit: RootToolkit | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    *,
    context_schema: type[ChatContext] = ChatContext,
) -> CompiledStateGraph[RootState, ChatContext, RootInput, RootOutput]:
    tools = toolkit or default_toolkit()

    def guard(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        writer_progress(runtime.stream_writer).status(CHECKING)
        context = runtime.context
        run = RootRun(budget=new_model_call_budget(settings.llm_agent_max_calls))
        started: RootState = {"steps": [step(CHECKING)], "started": time.monotonic(), "run": run}
        # 블라인드 채용이면 학력 · 출신 학교로 찾거나 거르는 요청도 막는다
        if term := blocked_attribute(context.message, blind=context.posting.blind):
            return {**started, "plan": ChatPlan.answer(Intent.BLOCKED, blocked_reply(term))}
        if set(context.mentions) - {row.application_id for row in context.candidates}:
            return {**started, "plan": ChatPlan.answer(Intent.CLARIFY, NOT_IN_STAGE)}
        return started

    async def plan(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        context, run = runtime.context, _run(state)
        progress = _progress(state, runtime)
        result, subject = state.get("result"), state.get("subject") or []
        try:
            with using_model_call_budget(run.budget):
                root_plan = await make_plan(llm, context, state.get("turns") or [], result, subject)
        except LlmOutputError as error:
            return _failed(error, progress)
        scope = root_plan.scope
        rows: list[CandidateRow] = []
        if scope is not None and not scope.empty:
            expanded = expand_scope(scope, context, result, subject)
            if isinstance(expanded, str):
                return {"plan": ChatPlan.answer(Intent.CLARIFY, expanded), "kind": "ANSWER", "steps": progress.steps}
            rows = expanded
        checked = precheck(context, root_plan, rows)
        if checked is not None:
            return {"plan": checked, "kind": "ANSWER", "steps": progress.steps}
        return {"run": replace(run, plan=root_plan, rows=rows), "steps": progress.steps}

    def after_plan(state: RootState) -> Literal["find", "edit", "questions", "report", "analyze", "reply", "record"]:
        if state.get("plan") is not None:
            return "record"
        root_plan = _run(state).plan
        if root_plan is None:
            raise TypeError("계획 없이 처리 노드로 갈 수 없다")
        match root_plan.kind:
            case "find":
                return "find"
            case "edit":
                return "edit"
            case "report":
                return "report"
            case "questions":
                form = root_plan.form
                return "questions" if isinstance(form, QuestionsPlan) and form.checks == "none" else "analyze"
            case "answer":
                return "analyze"
            case _:
                return "reply"

    async def find(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        run, progress = _run(state), _progress(state, runtime)
        form = _form(run, FindPlan)
        rows = run.rows if not form.scope.empty else None
        try:
            with using_model_call_budget(run.budget):
                handled = await handle_find(llm, runtime.context, tools, form, rows, progress=progress)
        except LlmOutputError as error:
            return _failed(error, progress)
        return _handled(handled, progress)

    def edit(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        run = _run(state)
        form = _form(run, EditPlan)
        # 전형 전체나 다른 탭에서 모아 넣을 때는 이미 선택했거나 넣을 수 없는 사람을 조용히 뺀다
        bulk = "all" in form.scope.sources or bool(form.scope.tabs)
        handled = handle_edit(runtime.context, form, run.rows, all_scope=bulk)
        return _handled(handled, _progress(state, runtime))

    def questions(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        run = _run(state)
        return _handled(
            handle_questions(runtime.context, _form(run, QuestionsPlan), run.rows), _progress(state, runtime)
        )

    def report(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        run = _run(state)
        handled = handle_report(runtime.context, _form(run, ReportPlan), run.rows)
        return _handled(handled, _progress(state, runtime))

    def reply(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        root_plan = _run(state).plan
        if root_plan is None:
            raise TypeError("계획 없이 답할 수 없다")
        return _handled(handle_reply(runtime.context, root_plan), _progress(state, runtime))

    async def analyze(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        context, run, progress = runtime.context, _run(state), _progress(state, runtime)
        root_plan = run.plan
        if root_plan is None:
            raise TypeError("계획 없이 분석할 수 없다")
        form = root_plan.form
        checks = form.checks if isinstance(form, QuestionsPlan) else "none"
        analysis = analysis_run(
            context, run.rows, state.get("turns") or [], state.get("result"), state.get("subject") or []
        )
        try:
            with using_model_call_budget(run.budget):
                answered = await run_analysis(
                    llm,
                    tools,
                    analysis,
                    task="questions" if isinstance(form, QuestionsPlan) else "answer",
                    checks=checks,
                    progress=progress,
                )
        except LlmOutputError as error:
            return _failed(error, progress)
        output = answered.form
        if isinstance(output, FindOutput):
            found = analysis.searches[output.result]
            mode = analysis.queries[output.result].mode
            kind = "FIND" if found.intent in (Intent.FIND, Intent.ANSWER) else "ANSWER"
            return {"plan": found, "kind": kind, "mode": mode, "steps": progress.steps}
        if isinstance(output, ClarifyOutput):
            clarify = ChatPlan.answer(Intent.CLARIFY, readable(output.message, context))
            return {"plan": clarify, "kind": "ANSWER", "steps": progress.steps}
        return {"run": replace(run, analysis=analysis, reply=answered), "steps": progress.steps}

    def after_analyze(state: RootState) -> Literal["review", "record"]:
        return "record" if state.get("plan") is not None else "review"

    async def review(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        context, run, progress = runtime.context, _run(state), _progress(state, runtime)
        if run.reply is None or run.analysis is None or run.plan is None:
            raise TypeError("분석 답 없이 근거를 검토할 수 없다")
        output, ledger = run.reply.form, run.analysis.ledger
        progress.status(REVIEWING)
        with using_model_call_budget(run.budget):
            if isinstance(output, AnswerOutput):
                message, checked = await review_items(llm, context, ledger, output.message, output.items)
                reviewed = answer_plan(context, message, checked)
            elif isinstance(output, QuestionsOutput) and isinstance(run.plan.form, QuestionsPlan):
                # 확인할 점은 사실 주장이 아니라 물어볼 점이라 판정 모델 없이 근거 상태만 맞춘다.
                # 남은 확인할 점이 없으면 요청 문장으로 질문을 만들게 한다
                checked = cap_items(context, ledger, focus_drafts(output.focus))
                reviewed = questions_plan(context, run.rows, run.plan.form, checked) or (
                    handle_questions(context, run.plan.form, run.rows).plan
                )
            else:
                raise TypeError(f"근거를 검토하지 않는 답이다: {run.reply.kind}")
        final = reviewed or ChatPlan.answer(Intent.CLARIFY, NO_EVIDENCE)
        drafts = len(output.items) if isinstance(output, AnswerOutput) else len(output.focus)
        progress.status(_reviewed(final, isinstance(output, QuestionsOutput), len(checked), drafts - len(checked)), 1)
        return {"plan": final, "kind": "ANSWER", "steps": progress.steps}

    def record(state: RootState, runtime: Runtime[ChatContext]) -> RootState:
        final = state.get("plan")
        if final is None:
            raise TypeError("검증된 계획 없이 턴을 남기려 했다")
        writer = writer_progress(runtime.stream_writer)
        for item in final.items:
            writer.item(item)
        kind = state.get("kind") or ""
        turn = turn_of(runtime.context, None, final, kind)
        mode = state.get("mode")
        turn["mode"] = mode.value if mode is not None else None
        turn["result_before"] = state.get("result")
        turn["subject_before"] = state.get("subject") or []
        turn["steps"] = state.get("steps") or []
        started = state.get("started")
        if started is not None:
            turn["seconds"] = round(time.monotonic() - started)
        return {
            "turns": remember(state.get("turns") or [], turn, settings.root_memory_turns),
            "result": next_result(state.get("result"), kind, mode, final),
            "subject": turn["targets"] or state.get("subject") or [],
            **_NEW_TURN,
            "run": None,
        }

    def after_guard(state: RootState) -> Literal["record", "plan"]:
        return "record" if state.get("plan") is not None else "plan"

    graph: StateGraph[RootState, ChatContext, RootInput, RootOutput] = StateGraph(
        RootState, context_schema=context_schema, input_schema=RootInput, output_schema=RootOutput
    )
    graph.add_node("guard", guard)
    graph.add_node("plan", plan)
    graph.add_node("find", find)
    graph.add_node("edit", edit)
    graph.add_node("questions", questions)
    graph.add_node("report", report)
    graph.add_node("reply", reply)
    graph.add_node("analyze", analyze)
    graph.add_node("review", review)
    graph.add_node("record", record)
    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", after_guard)
    graph.add_conditional_edges("plan", after_plan)
    graph.add_conditional_edges("analyze", after_analyze)
    for node in ("find", "edit", "questions", "report", "reply", "review"):
        graph.add_edge(node, "record")
    graph.add_edge("record", END)
    return graph.compile(checkpointer=checkpointer)


def _reviewed(final: ChatPlan, questions: bool, kept: int, dropped: int) -> str:
    """근거 검토 결과 단계. 항목 문장은 내보내지 않고 상태별 개수만 쓴다."""
    if questions:
        return FOCUS_REVIEWED.format(count=kept) if kept else NO_FOCUS_LEFT
    if not final.items or final.intent is Intent.CLARIFY:
        return NOTHING_EVIDENCED
    check = sum(1 for item in final.items if item.status == "CHECK")
    text = REVIEWED.format(total=len(final.items), ok=sum(1 for item in final.items if item.status == "OK"))
    if check:
        text += REVIEWED_CHECK.format(count=check)
    if dropped > 0:
        text += REVIEWED_DROPPED.format(count=dropped)
    return text


def _run(state: RootState) -> RootRun:
    run = state.get("run")
    if run is None:
        raise TypeError("요청 상태(run) 없이 처리할 수 없다")
    return run


def _form[T](run: RootRun, kind: type[T]) -> T:
    form = run.plan.form if run.plan is not None else None
    if not isinstance(form, kind):
        raise TypeError(f"{kind.__name__} 계획이 아니다")
    return form


def _progress(state: RootState, runtime: Runtime[ChatContext]) -> StepRecorder:
    return StepRecorder(writer_progress(runtime.stream_writer), state.get("steps"))


def _handled(handled: Handled, progress: StepRecorder) -> RootState:
    return {"plan": handled.plan, "kind": handled.kind, "mode": handled.mode, "steps": progress.steps}


def _failed(error: LlmOutputError, progress: StepRecorder) -> RootState:
    """원인을 구분해 기록하고 원인에 맞는 안내를 낸다. 검증되지 않은 모델 출력은 보이지 않는다."""
    logger.warning("Root 답변을 완료하지 못했다 (reason=%s)", error.reason.value)
    return {
        "plan": ChatPlan.answer(Intent.CLARIFY, FAILURE_MESSAGES[error.reason]),
        "kind": "",
        "steps": progress.steps,
    }


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
        and applied.previous.edit is EditAction.CLEAR
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
        saved_plan = ChatPlan.model_validate(saved_turn["plan"])
        saved_mode = saved_turn.get("mode", saved_plan.mode)
        mode = SelectionMode(saved_mode) if saved_mode is not None else None
        result = next_result(result, saved_turn["kind"], mode, saved_plan)
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
