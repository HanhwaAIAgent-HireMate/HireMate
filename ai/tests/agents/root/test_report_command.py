from typing import Any

import pytest
from root_context import make_context

from hiremate_ai.agents.guardrails import BLOCKED_REPLY
from hiremate_ai.agents.root.handlers import handle_report
from hiremate_ai.agents.root.plan import AnswerPlan, ReportPlan, RootPlan, check_plan, make_plan
from hiremate_ai.agents.root.report import ANSWER_HINT, COMPARE_COUNT, NO_PREVIOUS_STAGE, REPORT_HINT, asks_report
from hiremate_ai.agents.root.scope import Scope
from hiremate_ai.agents.root.types import ChatContext, Intent, ReportRequestKind
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.fake import FakeLlm, ToolCall

type Applicants = dict[str, ApplicantDetail]


@pytest.fixture
def context(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> ChatContext:
    return make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="두 사람 협업 관점으로 간략히 리포트 만들어줘",
        stage_type=StageType.INTERVIEW,
        previous_types=[StageType.DOCUMENT],
    )


def report(**arguments: Any) -> ReportPlan:
    return ReportPlan.model_validate({"view": "compare", "scope": {}, **arguments})


async def test_plan_reads_report_form(context: ChatContext) -> None:
    arguments = {"view": "compare", "scope": {"names": ["정유민", "김하늘"]}, "stage": None, "perspective": "협업"}

    plan = await make_plan(FakeLlm(ToolCall("report", {**arguments, "brief": True})), context, [], None, [])

    assert plan.kind == "report"
    assert isinstance(plan.form, ReportPlan) and plan.form.perspective == "협업" and plan.form.brief


def test_compare_report_carries_targets_focus_and_brief(context: ChatContext) -> None:
    rows = context.candidates[:2]

    handled = handle_report(context, report(perspective=" 협업 ", brief=True), rows)

    assert handled.plan.intent is Intent.REPORT
    request = handled.plan.report
    assert request is not None and request.kind is ReportRequestKind.COMPARE
    assert request.targets == [row.application_id for row in rows]
    assert (request.focus, request.brief, request.report_id) == ("협업", True, None)
    assert handled.plan.message == f"{rows[0].name}, {rows[1].name} 비교 리포트를 만들고 있어요."


def test_compare_report_needs_two_to_five_people(context: ChatContext) -> None:
    for rows in (context.candidates[:1], context.candidates[:6]):
        handled = handle_report(context, report(), rows)
        assert (handled.plan.intent, handled.plan.message) == (Intent.CLARIFY, COMPARE_COUNT)


def test_compare_report_keeps_to_the_mentioned_people(context: ChatContext) -> None:
    mentioned = context.model_copy(
        update={"mentions": [context.candidates[0].application_id, context.candidates[1].application_id]}
    )

    handled = handle_report(mentioned, report(), context.candidates[:3])

    assert handled.plan.report is not None
    assert handled.plan.report.targets == mentioned.mentions


def test_discriminatory_perspective_is_blocked(context: ChatContext) -> None:
    handled = handle_report(context, report(perspective="여성 지원자"), context.candidates[:2])

    assert (handled.plan.intent, handled.plan.message) == (Intent.BLOCKED, BLOCKED_REPLY)


@pytest.mark.parametrize("name", ["이전 전형", "이전", "지난 전형", "직전 단계", "서류전형"])
def test_stage_report_opens_the_stage_before_the_current(context: ChatContext, name: str) -> None:
    previous = context.stages[context.stage_index - 1]

    handled = handle_report(context, report(view="stage", stage=name), [])

    request = handled.plan.report
    assert request is not None and request.kind is ReportRequestKind.STAGE
    assert request.stage_id == previous.id
    assert handled.plan.message == f"{previous.name} 결과 리포트를 열어요."


def test_current_stage_report_leaves_the_stage_to_backend(context: ChatContext) -> None:
    handled = handle_report(context, report(view="stage"), [])

    assert handled.plan.report is not None and handled.plan.report.stage_id is None


def test_first_stage_has_no_previous_stage_report(context: ChatContext) -> None:
    first = context.model_copy(update={"stage_id": context.stages[0].id})

    handled = handle_report(first, report(view="stage", stage="이전 전형"), [])

    assert (handled.plan.intent, handled.plan.message) == (Intent.CLARIFY, NO_PREVIOUS_STAGE)


def test_unknown_stage_is_asked_back(context: ChatContext) -> None:
    handled = handle_report(context, report(view="stage", stage="코딩테스트"), [])

    assert handled.plan.intent is Intent.CLARIFY
    assert "이 채용의 전형" in handled.plan.message


def test_compare_report_without_scope_is_rewritten(context: ChatContext) -> None:
    assert check_plan(RootPlan(kind="report", form=report()), context, None, []) is not None


def test_text_answer_to_a_report_request_is_rewritten(context: ChatContext) -> None:
    plan = RootPlan(kind="answer", form=AnswerPlan(scope=Scope(sources=["mentions"])))
    asked = context.model_copy(update={"message": "두 사람 점수를 그래프로 보여줘"})

    assert check_plan(plan, asked, None, []) == REPORT_HINT
    assert check_plan(plan, context.model_copy(update={"message": "두 사람 비교해줘"}), None, []) is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("한서윤, 정지호 협업 관점으로 비교 리포트 만들어줘", True),
        ("서류전형 리포트 보여줘", True),
        ("두 사람 점수를 그래프로 보여줘", True),
        ("세 명 차트로 정리해줘", True),
        ("두 사람 비교해줘", False),
        ("리포트는 언제 나와?", False),
        ("그래프에서 누가 제일 높아?", False),
    ],
)
def test_asks_report(message: str, expected: bool) -> None:
    assert asks_report(message) is expected


def test_compare_without_any_report_cue_is_an_answer(context: ChatContext) -> None:
    plan = RootPlan(kind="report", form=report(scope=Scope(names=["정유민", "김하늘"])))

    plain = context.model_copy(update={"message": "정유민이랑 김하늘 비교해줘"})
    nuance = context.model_copy(update={"message": "두 사람 한눈에 보게 정리해줘"})

    assert check_plan(plan, plain, None, []) == ANSWER_HINT
    assert check_plan(plan, nuance, None, []) is None
