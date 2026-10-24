from root_context import extra_row, make_context

from hiremate_ai.agents.guardrails import BLOCKED_REPLY
from hiremate_ai.agents.root.answer import (
    COMPARE_STATUS,
    FOCUS_WITH_REQUEST,
    MULTI_STATUS,
    AnswerEvidence,
    AnswerItem,
    CandidateNotes,
    MultiSummary,
    QuestionFocusItem,
    RootAnswer,
    RootQuestionFocus,
)
from hiremate_ai.agents.root.edit import SAME_NAME
from hiremate_ai.agents.root.find import RecheckItem, RecheckResult
from hiremate_ai.agents.root.graph import CHECKING, ROUTED, PlanEvent, build_root_graph, run_plan, stream_plan
from hiremate_ai.agents.root.route import COMPARE_NEEDS_TWO, DECISION_REPLY, NOT_UNDERSTOOD, RootRoute
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, ChatStatus, EditAction, Intent, SelectionMode
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.fake import FakeLlm, LlmCall, ToolCall

type Applicants = dict[str, ApplicantDetail]


def checked_notes() -> CandidateNotes:
    return CandidateNotes(
        items=[AnswerItem(label="확인할 점", text="세부 근거는 추가 확인이 필요해요.", status="CHECK")]
    )


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
    llm = FakeLlm(RootRoute(kind="ANSWER"), checked_notes(), MultiSummary(message="강점은 정산 배치 개선이에요."))

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
    request = "@정유민 면접 질문 만들어줘"
    assert plan.question_focus == {jung: FOCUS_WITH_REQUEST.format(focus="정산 배치 설계 판단", request=request)}


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
    llm = FakeLlm(
        RootRoute(kind="ANSWER", interview_questions=True),
        checked_notes(),
        MultiSummary(message="면접에서 확인할 점이에요."),
    )

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
        sample_applicants, sample_company, sample_posting, message="@김하늘이랑 누가 더 나아?", mentions=["김하늘"]
    )
    llm = FakeLlm(RootRoute(kind="ANSWER", compare=True))

    plan = await run_plan(llm, context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, COMPARE_NEEDS_TWO)
    assert len(llm.calls) == 1


async def test_clarified_comparison_without_targets_asks_for_two(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="둘 비교해줘")
    llm = FakeLlm(RootRoute(kind="CLARIFY", compare=True, clarify="비교할 두 지원자를 알려주세요."))

    plan = await run_plan(llm, context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, COMPARE_NEEDS_TWO)


async def test_clarified_comparison_with_checked_compares(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="둘 비교해줘", checked=["박서준", "이도윤"]
    )
    llm = FakeLlm(
        RootRoute(kind="CLARIFY", compare=True, clarify="누구를 비교할까요?"),
        checked_notes(),
        checked_notes(),
        MultiSummary(message="두 사람을 비교했어요."),
    )

    plan = await run_plan(llm, context)

    assert (plan.intent, plan.message) == (Intent.ANSWER, "두 사람을 비교했어요.")


async def test_first_turn_count_with_stray_ordinal_answers_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 실제 모델이 첫 턴의 인원 질문에 앞 대화와 순서를 표시해도 되묻지 않고 전형 전체로 답한다
    context = make_context(sample_applicants, sample_company, sample_posting, message="지금 미결정인 사람 몇 명이야?")
    llm = FakeLlm(
        RootRoute(kind="ANSWER", previous_ref="subject", ordinal=1),
        ToolCall("get_stage_summary"),
        RootAnswer(message="미결정은 8명이에요.", items=[]),
    )

    plan = await run_plan(llm, context)

    assert (plan.intent, plan.message) == (Intent.ANSWER, "미결정은 8명이에요.")


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


async def test_clear_with_previous_ref_still_clears(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="아까 선택 다 비워줘")

    plan = await run_plan(FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR, previous_ref="subject")), context)

    assert (plan.intent, plan.edit) == (Intent.EDIT, EditAction.CLEAR)


async def test_unspoken_previous_without_memory_answers_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 실제 모델은 이름이 없는 질문에 앞 대화를 표시한다. 문장이 앞 대화를 가리키지 않으면 되묻지 않고 전형 전체로 답한다
    context = make_context(sample_applicants, sample_company, sample_posting, message="미결정이 몇 명 남았어?")
    llm = FakeLlm(
        RootRoute(kind="ANSWER", previous_ref="subject"),
        ToolCall("get_stage_summary"),
        RootAnswer(message="미결정은 8명이에요.", items=[]),
    )

    plan = await run_plan(llm, context)

    assert (plan.intent, plan.message) == (Intent.ANSWER, "미결정은 8명이에요.")
    assert "대상 지원자: 지정 없음" in llm.calls[1].user


async def test_find_flagged_compare_is_not_refused(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험 있는 사람 둘 찾아줘")
    llm = FakeLlm(
        RootRoute(kind="FIND", compare=True, concepts=["금융 도메인 경험"]),
        RecheckResult(results=[RecheckItem(candidate_no=1, met=True, sentence_nos=[1])]),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.FIND


async def events_of(llm: LlmClient, context: ChatContext) -> list[PlanEvent]:
    return [event async for event in stream_plan(llm, context)]


async def test_stream_plan_events_end_with_done(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="선택 지원자 비워줘")

    events = await events_of(FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR)), context)

    assert [name for name, _ in events] == ["status", "status", "done"]
    assert [data for _, data in events[:2]] == [ChatStatus(text=CHECKING), ChatStatus(text=ROUTED["EDIT"])]
    assert events[-1][1] == await run_plan(FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR)), context)


async def test_stream_plan_blocked_has_one_status(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="30대 남자 찾아줘")

    events = await events_of(FakeLlm(), context)

    assert [name for name, _ in events] == ["status", "done"]
    assert events[-1][1] == ChatPlan.answer(Intent.BLOCKED, BLOCKED_REPLY)


async def test_stream_plan_multi_streams_items(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="두 사람 비교해줘",
        mentions=["김하늘", "박서준"],
    )

    def note(text: str, sentence: str) -> CandidateNotes:
        evidence = AnswerEvidence(sentence=sentence, source="이력서")
        return CandidateNotes(items=[AnswerItem(label="RDBMS", text=text, status="OK", evidence=[evidence])])

    llm = FakeLlm(
        RootRoute(kind="ANSWER"),
        note("Oracle 원장 설계", "Oracle 원장 테이블 설계와 쿼리 튜닝을 맡았습니다."),
        note("PostgreSQL 튜닝", "PostgreSQL 쿼리를 튜닝해 주문 조회 p99를 1.2초에서 300ms로 줄였습니다."),
        MultiSummary(message="비교했어요."),
    )

    events = await events_of(llm, context)

    assert [name for name, _ in events] == ["status", "status", "status", "item", "item", "status", "done"]
    assert [data for name, data in events if name == "status"] == [
        ChatStatus(text=text)
        for text in (CHECKING, ROUTED["ANSWER"], MULTI_STATUS.format(count=2), COMPARE_STATUS.format(count=2))
    ]
    plan = events[-1][1]
    assert isinstance(plan, ChatPlan)
    # 항목은 정리가 끝난 순서로 온다. 최종 답과 같은 항목이다
    assert sorted((data for name, data in events if name == "item"), key=str) == sorted(plan.items, key=str)
