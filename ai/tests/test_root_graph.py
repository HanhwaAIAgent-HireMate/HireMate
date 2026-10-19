from root_context import make_context

from hiremate_ai.agents.guardrails import BLOCKED_REPLY
from hiremate_ai.agents.root.graph import PENDING, run_plan
from hiremate_ai.agents.root.route import DECISION_REPLY, NOT_UNDERSTOOD, RootRoute
from hiremate_ai.agents.root.types import ChatPlan, EditAction, Intent
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.fake import FakeLlm, LlmCall

type Applicants = dict[str, ApplicantDetail]


async def test_blocked_skips_model(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="30대 남자 찾아줘")
    llm = FakeLlm()

    plan = await run_plan(llm, context)

    assert plan == ChatPlan.answer(Intent.BLOCKED, BLOCKED_REPLY)
    assert llm.calls == []


async def test_classify_error_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    def broken(call: LlmCall) -> RootRoute:
        raise LlmOutputError("RootRoute 형식의 답을 받지 못했다")

    context = make_context(sample_applicants, sample_company, sample_posting, message="음")

    plan = await run_plan(FakeLlm(broken), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NOT_UNDERSTOOD)


async def test_edit_flows_to_plan(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="@김하늘 빼줘", mentions=["김하늘"]
    )

    plan = await run_plan(FakeLlm(RootRoute(kind="EDIT", edit=EditAction.REMOVE)), context)

    assert (plan.intent, plan.edit) == (Intent.EDIT, EditAction.REMOVE)
    assert plan.targets == [sample_applicants["김하늘"].info.application_id]


async def test_precheck_answers_without_path(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="이 사람 합격시켜줘")

    plan = await run_plan(FakeLlm(RootRoute(kind="DECISION")), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, DECISION_REPLY)


async def test_find_and_answer_are_pending(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험자 찾아줘")
    llm = FakeLlm(RootRoute(kind="FIND", concepts=["금융 도메인 경험"]), RootRoute(kind="ANSWER"))

    found = await run_plan(llm, context)
    answered = await run_plan(llm, context)

    assert found == answered == ChatPlan.answer(Intent.CLARIFY, PENDING)
