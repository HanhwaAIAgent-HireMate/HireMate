from root_context import make_context

from hiremate_ai.agents.root.route import (
    DECISION_REPLY,
    DEFAULT_CLARIFY,
    NO_ASSESSMENT,
    NO_INTERVIEW,
    RootRoute,
    classify,
    precheck,
)
from hiremate_ai.agents.root.targets import resolve
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, EditAction, Intent
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.fake import FakeLlm

type Applicants = dict[str, ApplicantDetail]


def context_for(
    applicants: Applicants,
    company: CompanyProfile,
    posting: PostingContent,
    stage_type: StageType = StageType.DOCUMENT,
    previous_types: tuple[StageType, ...] = (),
) -> ChatContext:
    return make_context(
        applicants, company, posting, message="질문", stage_type=stage_type, previous_types=previous_types
    )


async def test_prompt_has_question_and_targets_but_no_documents(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@정유민 빼줘",
        mentions=["정유민"],
        checked=["김하늘", "박서준"],
    )
    route = RootRoute(kind="EDIT", edit=EditAction.REMOVE)
    llm = FakeLlm(route)

    result = await classify(llm, context, resolve(context))

    assert result == route
    call = llm.calls[0]
    assert call.agent == "root"
    assert "@정유민 빼줘" in call.user
    assert "정유민" in call.user.replace("@정유민 빼줘", "")
    assert "2명" in call.user
    first_line = sample_applicants["정유민"].documents[0].text.splitlines()[0]
    assert first_line not in call.user


def test_decision_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    assert precheck(RootRoute(kind="DECISION"), context) == ChatPlan.answer(Intent.CLARIFY, DECISION_REPLY)


def test_clarify_uses_model_question(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    plan = precheck(RootRoute(kind="CLARIFY", clarify="어느 지원자를 말씀하세요?"), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, "어느 지원자를 말씀하세요?")


def test_clarify_falls_back_to_default(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    assert precheck(RootRoute(kind="CLARIFY"), context) == ChatPlan.answer(Intent.CLARIFY, DEFAULT_CLARIFY)


def test_needs_assessment_in_document_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    plan = precheck(RootRoute(kind="FIND", needs=[StageType.ASSESSMENT]), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_ASSESSMENT)


def test_needs_assessment_in_interview_stage_without_assessment(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting, StageType.INTERVIEW, (StageType.DOCUMENT,))

    plan = precheck(RootRoute(kind="ANSWER", needs=[StageType.ASSESSMENT]), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_ASSESSMENT)


def test_needs_assessment_after_assessment_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(
        sample_applicants, sample_company, sample_posting, StageType.INTERVIEW, (StageType.ASSESSMENT,)
    )

    assert precheck(RootRoute(kind="FIND", needs=[StageType.ASSESSMENT]), context) is None


def test_needs_assessment_in_assessment_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting, StageType.ASSESSMENT)

    assert precheck(RootRoute(kind="FIND", needs=[StageType.ASSESSMENT]), context) is None


def test_needs_interview_before_interview(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting, StageType.ASSESSMENT)

    plan = precheck(RootRoute(kind="ANSWER", needs=[StageType.INTERVIEW]), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_INTERVIEW)


def test_needs_interview_in_interview_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting, StageType.INTERVIEW)

    assert precheck(RootRoute(kind="ANSWER", needs=[StageType.INTERVIEW]), context) is None


def test_find_and_edit_pass_precheck(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    assert precheck(RootRoute(kind="FIND", concepts=["금융 도메인 경험"]), context) is None
    assert precheck(RootRoute(kind="EDIT", edit=EditAction.CLEAR), context) is None
