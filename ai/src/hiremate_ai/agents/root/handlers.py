"""정해진 흐름의 처리기: 찾기, 선택 편집, 확인할 점 없는 면접 질문, 리포트 요청, 고정 답. 계획이 정한 인자만 쓴다.

데이터 사실(결과를 확정한 전형, 면접 전형이 아님, 메모 없음)은 모델에게 다시 묻지 않고 바로 안내한다.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from hiremate_ai.agents.guardrails import BLOCKED_REPLY, blocked_attribute, blocked_reply
from hiremate_ai.agents.root.answer import BULK_LIMIT, INTERVIEW_AGENT, QUESTIONS_REQUESTED, readable
from hiremate_ai.agents.root.edit import plan_edit, selectable
from hiremate_ai.agents.root.find import LOCKED, SEARCH_STATUS, SearchQuery, plan_find, search_criteria
from hiremate_ai.agents.root.plan import (
    BlockedPlan,
    ClarifyPlan,
    ConversationPlan,
    DecisionPlan,
    EditPlan,
    FindPlan,
    QuestionsPlan,
    ReportPlan,
    RootPlan,
)
from hiremate_ai.agents.root.progress import Progress, nested
from hiremate_ai.agents.root.report import (
    COMPARE_COUNT,
    COMPARING,
    MAX_COMPARED,
    MIN_COMPARED,
    OPENING_STAGE,
    report_stage,
)
from hiremate_ai.agents.root.scope import NO_SELECTED
from hiremate_ai.agents.root.toolkit import NO_MEMOS, RootToolkit
from hiremate_ai.agents.root.types import (
    CandidateRow,
    ChatContext,
    ChatPlan,
    ChatReport,
    EditAction,
    Intent,
    ReportRequestKind,
    SelectionMode,
)
from hiremate_ai.contract import StageType
from hiremate_ai.llm.client import LlmClient

DECISION_REPLY = "합격과 불합격 결정, 결과 확정, 공고 게시와 안내 발송은 담당자가 화면에서 직접 실행해 주세요."
NOT_INTERVIEW = "면접 질문은 면접 전형에서 만들 수 있어요."
# 면접관 모드의 Chat: 배정된 지원자만 보고, 선택 지원자는 채용 담당자가 바꾼다
# (backend ChatService.INTERVIEWER_LOCKED와 같은 문구)
INTERVIEWER_LOCKED = "면접관 모드에서는 선택 지원자를 바꿀 수 없어요. 지원자 분석과 질문 만들기는 할 수 있어요."
TOO_MANY = f"면접 질문은 한 번에 {BULK_LIMIT}명까지 만들 수 있어요."
NOTHING_TO_ADD = "선택 지원자에 넣을 수 있는 미선택 지원자가 없어요."
NOTHING_TO_REMOVE = "선택 지원자 가운데 조건에 맞는 사람이 없어요. 선택 지원자는 그대로예요."


@dataclass(frozen=True)
class Handled:
    plan: ChatPlan
    kind: str  # 턴 기록의 종류: FIND, EDIT, ANSWER
    mode: SelectionMode | None = None


def precheck(context: ChatContext, plan: RootPlan, rows: Sequence[CandidateRow]) -> ChatPlan | None:
    """처리 전에 화면과 전형 상태만으로 정해지는 안내. 실행할 수 있으면 None."""
    form = plan.form
    if context.interviewer and isinstance(form, EditPlan | FindPlan):
        return ChatPlan.answer(Intent.CLARIFY, INTERVIEWER_LOCKED)
    if isinstance(form, EditPlan) and not context.selectable:
        return ChatPlan.answer(Intent.CLARIFY, LOCKED)
    if isinstance(form, FindPlan) and form.remove and not context.selectable:
        return ChatPlan.answer(Intent.CLARIFY, LOCKED)
    if isinstance(form, QuestionsPlan):
        if context.stage_type is not StageType.INTERVIEW:
            return ChatPlan.answer(Intent.CLARIFY, NOT_INTERVIEW)
        if len(rows) > BULK_LIMIT:
            return ChatPlan.answer(Intent.CLARIFY, TOO_MANY)
        if form.checks == "memos" and not any(context.interviewer_memos.get(row.application_id) for row in rows):
            return ChatPlan.answer(Intent.CLARIFY, NO_MEMOS)
    return None


async def handle_find(
    llm: LlmClient,
    context: ChatContext,
    toolkit: RootToolkit,
    form: FindPlan,
    rows: Sequence[CandidateRow] | None,
    *,
    progress: Progress,
) -> Handled:
    """rows는 요청이 말한 검색 범위다. None이면 전형 전체다."""
    if term := blocked_attribute(" ".join(search_criteria(form.query, context)), blind=context.posting.blind):
        return Handled(ChatPlan.answer(Intent.BLOCKED, blocked_reply(term)), "ANSWER")
    progress.status(SEARCH_STATUS)
    if form.remove:
        return await _remove_matching(llm, context, toolkit, form.query, rows, nested(progress))
    pool = [row.application_id for row in rows] if rows is not None else None
    found = await plan_find(llm, form.query, context, toolkit, pool=pool, progress=nested(progress))
    kind = "FIND" if found.intent in (Intent.FIND, Intent.ANSWER) else "ANSWER"
    return Handled(found, kind, form.query.mode)


async def _remove_matching(
    llm: LlmClient,
    context: ChatContext,
    toolkit: RootToolkit,
    query: SearchQuery,
    rows: Sequence[CandidateRow] | None,
    progress: Progress,
) -> Handled:
    pool = list(rows) if rows else [row for row in context.candidates if row.selected]
    if not pool:
        return Handled(ChatPlan.answer(Intent.CLARIFY, NO_SELECTED), "ANSWER")
    narrowed = query.model_copy(update={"mode": SelectionMode.NARROW})
    found = await plan_find(
        llm, narrowed, context, toolkit, pool=[row.application_id for row in pool], progress=progress
    )
    if found.intent in (Intent.CLARIFY, Intent.BLOCKED):
        return Handled(found, "ANSWER")
    matched = set(found.targets)
    removing = [row for row in pool if row.application_id in matched]
    if not removing:
        return Handled(ChatPlan.answer(Intent.ANSWER, NOTHING_TO_REMOVE), "ANSWER")
    plan = plan_edit(EditAction.REMOVE, context, removing)
    return Handled(
        plan.model_copy(update={"items": found.items, "sources": found.sources, "agents": found.agents}), "EDIT"
    )


def handle_edit(context: ChatContext, form: EditPlan, rows: Sequence[CandidateRow], all_scope: bool) -> Handled:
    """전형 전체를 넣으라는 요청은 넣을 수 있는 미선택자만 남긴다. 넣을 수 없는 사람을 하나하나 나열하지 않는다."""
    targets = list(rows)
    if form.action is EditAction.ADD and all_scope:
        targets = [row for row in targets if not row.selected and selectable(context, row)]
        if not targets:
            return Handled(ChatPlan.answer(Intent.CLARIFY, NOTHING_TO_ADD), "ANSWER")
    plan = plan_edit(form.action, context, targets)
    return Handled(plan, "EDIT" if plan.intent is Intent.EDIT else "ANSWER")


def handle_questions(context: ChatContext, form: QuestionsPlan, rows: Sequence[CandidateRow]) -> Handled:
    """확인할 점 없이 만드는 면접 질문. backend가 요청 문장을 그대로 질문 생성 Agent에 넘긴다."""
    plan = ChatPlan.answer(Intent.ANSWER, QUESTIONS_REQUESTED.format(count=len(rows)), agents=[INTERVIEW_AGENT])
    update = {
        "question_targets": [row.application_id for row in rows],
        "question_replace": form.replace,
        # 메모 질문은 면접 기록에서 확인할 점을 묻는 것이라 NCS를 참고하지 않는다 (review.questions_plan과 같다)
        "question_ncs": "SKIP" if form.checks == "memos" else form.ncs,
    }
    return Handled(plan.model_copy(update=update), "ANSWER")


def handle_report(context: ChatContext, form: ReportPlan, rows: Sequence[CandidateRow]) -> Handled:
    """리포트 요청. 비교는 현재 전형 지원자 2~5명이고, 멘션이 두 명 이상이면 멘션한 사람만 비교한다.

    전형 결과 리포트는 전형만 정한다. 결과 확정 · 안내 발송 여부와 저장된 리포트는 backend가 확인한다.
    """
    if term := blocked_attribute(form.perspective, blind=context.posting.blind):
        return Handled(ChatPlan.answer(Intent.BLOCKED, blocked_reply(term)), "ANSWER")
    if form.view == "stage":
        stage_id = report_stage(form.stage, context) if form.stage else context.stage_id
        if isinstance(stage_id, str):
            return Handled(ChatPlan.answer(Intent.CLARIFY, stage_id), "ANSWER")
        stage = next(stage for stage in context.stages if stage.id == stage_id)
        request = ChatReport(
            kind=ReportRequestKind.STAGE,
            stage_id=None if stage_id == context.stage_id else stage_id,
            targets=[],
            focus="",
            brief=form.brief,
        )
        plan = ChatPlan.answer(Intent.REPORT, OPENING_STAGE.format(stage=stage.name))
        return Handled(plan.model_copy(update={"report": request}), "ANSWER")
    mentioned = [row for row in context.candidates if row.application_id in set(context.mentions)]
    targets = mentioned if len(mentioned) >= MIN_COMPARED else list(rows)
    if not MIN_COMPARED <= len(targets) <= MAX_COMPARED:
        return Handled(ChatPlan.answer(Intent.CLARIFY, COMPARE_COUNT), "ANSWER")
    request = ChatReport(
        kind=ReportRequestKind.COMPARE,
        stage_id=None,
        targets=[row.application_id for row in targets],
        focus=form.perspective.strip(),
        brief=form.brief,
    )
    names = ", ".join(row.name for row in targets)
    plan = ChatPlan.answer(Intent.REPORT, COMPARING.format(names=names))
    return Handled(plan.model_copy(update={"report": request}), "ANSWER")


def handle_reply(context: ChatContext, plan: RootPlan) -> Handled:
    """자료 없이 내는 답: 일반 대화, 되묻기, 차단, 결정 안내."""
    form = plan.form
    if isinstance(form, ConversationPlan):
        return Handled(ChatPlan.answer(Intent.ANSWER, readable(form.message, context)), "ANSWER")
    if isinstance(form, ClarifyPlan):
        return Handled(ChatPlan.answer(Intent.CLARIFY, readable(form.message, context)), "ANSWER")
    if isinstance(form, BlockedPlan):
        return Handled(ChatPlan.answer(Intent.BLOCKED, BLOCKED_REPLY), "ANSWER")
    if isinstance(form, DecisionPlan):
        return Handled(ChatPlan.answer(Intent.ANSWER, DECISION_REPLY), "ANSWER")
    raise TypeError(f"고정 답으로 처리하지 않는 종류다: {plan.kind}")
