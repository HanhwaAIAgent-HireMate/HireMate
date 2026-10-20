from root_context import extra_row, make_context

from hiremate_ai.agents.guardrails import BLOCKED_REPLY
from hiremate_ai.agents.root.answer import QuestionFocusItem, RootAnswer, RootQuestionFocus
from hiremate_ai.agents.root.edit import SAME_NAME
from hiremate_ai.agents.root.find import RecheckItem, RecheckResult
from hiremate_ai.agents.root.graph import build_root_graph, run_plan
from hiremate_ai.agents.root.route import COMPARE_NEEDS_TWO, DECISION_REPLY, NOT_UNDERSTOOD, RootRoute
from hiremate_ai.agents.root.types import ChatPlan, EditAction, Intent, SelectionMode
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
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


async def test_answer_flows_to_plan(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="@정유민 강점이 뭐야?", mentions=["정유민"]
    )
    llm = FakeLlm(RootRoute(kind="ANSWER"), RootAnswer(message="강점은 정산 배치 개선이에요."))

    plan = await run_plan(llm, context)

    assert (plan.intent, plan.message) == (Intent.ANSWER, "강점은 정산 배치 개선이에요.")
    assert plan.question_targets == []


async def test_interview_questions_flow_in_interview_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@정유민 면접 질문 만들어줘",
        mentions=["정유민"],
        stage_type=StageType.INTERVIEW,
    )
    focus = RootQuestionFocus(items=[QuestionFocusItem(candidate="C1", focus="정산 배치 설계 판단")])
    llm = FakeLlm(RootRoute(kind="ANSWER", interview_questions=True), focus)

    plan = await run_plan(llm, context)

    jung = sample_applicants["정유민"].info.application_id
    assert plan.question_targets == [jung]
    assert plan.question_focus == {jung: "정산 배치 설계 판단"}


async def test_interview_questions_outside_interview_stage_answer(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@정유민 면접에서 뭘 확인해야 해?",
        mentions=["정유민"],
    )
    llm = FakeLlm(RootRoute(kind="ANSWER", interview_questions=True), RootAnswer(message="면접에서 확인할 점이에요."))

    plan = await run_plan(llm, context)

    assert (plan.intent, plan.question_targets) == (Intent.ANSWER, [])
    assert plan.message == "면접에서 확인할 점이에요."


async def test_find_flows_to_plan(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험자 찾아줘")
    # 기본 검색 순서에서 김하늘은 두 번째 후보다
    recheck = RecheckResult(results=[RecheckItem(candidate_no=2, met=True, sentence_nos=[1])])
    llm = FakeLlm(RootRoute(kind="FIND", mode=SelectionMode.REPLACE, concepts=["금융 도메인 경험"]), recheck)

    plan = await run_plan(llm, context)

    assert (plan.intent, plan.mode) == (Intent.FIND, SelectionMode.REPLACE)
    assert plan.targets == [sample_applicants["김하늘"].info.application_id]


async def test_state_does_not_keep_chat_context(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="선택 지원자 비워줘")
    graph = build_root_graph(FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR)))

    state = await graph.ainvoke({}, context=context)

    assert "context" not in state
    assert state["turns"][-1]["plan"]["edit"] == EditAction.CLEAR.value


async def test_compare_with_one_target_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="@김하늘 비교해줘", mentions=["김하늘"]
    )
    llm = FakeLlm(RootRoute(kind="ANSWER", compare=True))

    plan = await run_plan(llm, context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, COMPARE_NEEDS_TWO)
    assert len(llm.calls) == 1


async def test_edit_uses_checked_without_target(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="이 둘 빼줘", checked=["정유민", "김하늘"]
    )

    plan = await run_plan(FakeLlm(RootRoute(kind="EDIT", edit=EditAction.REMOVE)), context)

    assert plan.targets == [sample_applicants[name].info.application_id for name in ("정유민", "김하늘")]


async def test_ambiguous_name_not_replaced_by_checked(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="김하늘 강점은?",
        checked=["정유민"],
        extra_rows=[extra_row("김하늘")],
    )
    llm = FakeLlm(RootRoute(kind="ANSWER"))

    plan = await run_plan(llm, context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, SAME_NAME.format(names="김하늘"))
    assert len(llm.calls) == 1
