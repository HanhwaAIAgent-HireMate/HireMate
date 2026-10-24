from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from root_context import make_context

from hiremate_ai.agents.root.answer import (
    FOCUS_WITH_REQUEST,
    AnswerItem,
    CandidateNotes,
    MultiSummary,
    QuestionFocusItem,
    RootAnswer,
    RootQuestionFocus,
)
from hiremate_ai.agents.root.find import RecheckItem, RecheckResult
from hiremate_ai.agents.root.graph import RootThread, run_plan
from hiremate_ai.agents.root.route import NO_PREVIOUS, RootRoute
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, EditAction, Intent, SelectionMode
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.fake import FakeLlm, ToolCall

type Applicants = dict[str, ApplicantDetail]


def thread_of(context: ChatContext, member: UUID | None = None) -> RootThread:
    return RootThread(
        id=f"{context.company.company_id}:{context.stage_id}:{member or uuid4()}",
        company_id=context.company.company_id,
        stage_id=context.stage_id,
    )


async def saved_turns(saver: InMemorySaver, thread: RootThread) -> list[Turn]:
    saved = await saver.aget_tuple({"configurable": {"thread_id": thread.id}})
    assert saved is not None
    turns: list[Turn] = saved.checkpoint["channel_values"]["turns"]
    return turns


def context_with(applicants: Applicants, company: CompanyProfile, posting: PostingContent, message: str) -> ChatContext:
    return make_context(applicants, company, posting, message=message)


async def test_second_turn_runs_full_graph(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    first = context_with(sample_applicants, sample_company, sample_posting, "비워줘")
    thread = thread_of(first)
    llm = FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR), RootRoute(kind="EDIT", edit=EditAction.RESTORE))

    cleared = await run_plan(llm, first, saver=saver, thread=thread)
    restored = await run_plan(
        llm, context_with(sample_applicants, sample_company, sample_posting, "되돌려줘"), saver=saver, thread=thread
    )

    assert (cleared.edit, restored.edit) == (EditAction.CLEAR, EditAction.RESTORE)
    turns = await saved_turns(saver, thread)
    assert [turn["message"] for turn in turns] == ["비워줘", "되돌려줘"]
    assert turns[1]["intent"] == Intent.EDIT.value


async def test_turns_keep_last_n(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "root_memory_turns", 3)
    saver = InMemorySaver()
    context = context_with(sample_applicants, sample_company, sample_posting, "비워줘")
    thread = thread_of(context)

    for _ in range(5):
        await run_plan(FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR)), context, saver=saver, thread=thread)

    assert len(await saved_turns(saver, thread)) == 3


async def test_threads_are_separate(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    context = context_with(sample_applicants, sample_company, sample_posting, "비워줘")
    mine, theirs = thread_of(context), thread_of(context)

    await run_plan(FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR)), context, saver=saver, thread=mine)
    await run_plan(FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR)), context, saver=saver, thread=theirs)
    await run_plan(FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR)), context, saver=saver, thread=theirs)

    assert len(await saved_turns(saver, mine)) == 1
    assert len(await saved_turns(saver, theirs)) == 2


async def test_turn_records_subject_and_answer(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="@김하늘 강점은?", mentions=["김하늘"]
    )
    thread = thread_of(context)
    llm = FakeLlm(
        RootRoute(kind="ANSWER"),
        RootAnswer(
            message="은행 경력이 강점이에요.",
            items=[AnswerItem(candidate="C2", label="강점", text="은행 경력", status="CHECK")],
        ),
    )

    await run_plan(llm, context, saver=saver, thread=thread)

    turn = (await saved_turns(saver, thread))[0]
    kim = str(sample_applicants["김하늘"].info.application_id)
    assert turn["targets"] == [kim]
    assert turn["answer"] == "은행 경력이 강점이에요."
    assert turn["items"] == [{"application_id": kim, "label": "강점", "text": "은행 경력"}]
    assert turn["total"] == 8


async def test_state_has_no_documents(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="@정유민 강점은?", mentions=["정유민"]
    )
    thread = thread_of(context)
    llm = FakeLlm(
        RootRoute(kind="ANSWER"),
        ToolCall("get_candidate_documents", {"candidate": "C1"}),
        RootAnswer(message="강점이에요."),
    )

    await run_plan(llm, context, saver=saver, thread=thread)

    saved = await saver.aget_tuple({"configurable": {"thread_id": thread.id}})
    assert saved is not None
    stored = repr(saved.checkpoint["channel_values"])
    assert "Kafka" not in stored
    assert "한빛카드 결제플랫폼팀" not in stored
    assert saved.metadata.get("stage_id") == str(context.stage_id)


async def test_tool_loop_is_not_saved(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    """도구 루프는 Root 그래프 안에서 돌지만 대화방에 자기 checkpoint를 남기지 않는다.

    남기면 도구 결과로 읽은 문서 본문이 저장된다 (규칙 3).
    """
    saver = InMemorySaver()
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="@정유민 강점은?", mentions=["정유민"]
    )
    thread = thread_of(context)
    llm = FakeLlm(
        RootRoute(kind="ANSWER"),
        ToolCall("get_candidate_documents", {"candidate": "C1"}),
        RootAnswer(message="강점이에요."),
    )

    await run_plan(llm, context, saver=saver, thread=thread)

    namespaces = {*saver.storage[thread.id], *(key[1] for key in saver.writes), *(key[1] for key in saver.blobs)}
    assert namespaces == {""}
    assert "Kafka" not in repr([saver.storage, saver.writes, saver.blobs])


FINANCE_FOUND = RecheckResult(
    results=[
        RecheckItem(candidate_no=1, met=True, sentence_nos=[1]),
        RecheckItem(candidate_no=2, met=True, sentence_nos=[1]),
        RecheckItem(candidate_no=6, met=True, sentence_nos=[1]),
    ]
)


async def test_ordinal_from_previous_result(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    found = context_with(sample_applicants, sample_company, sample_posting, "금융 경험 있는 사람 찾아줘")
    thread = thread_of(found)
    llm = FakeLlm(
        RootRoute(kind="FIND", concepts=["금융 도메인 경험"]),
        FINANCE_FOUND,
        RootRoute(kind="ANSWER", previous_ref="result", ordinal=2),
        RootAnswer(message="강점이에요."),
    )

    await run_plan(llm, found, saver=saver, thread=thread)
    await run_plan(
        llm,
        context_with(sample_applicants, sample_company, sample_posting, "그중 두 번째 사람 강점은?"),
        saver=saver,
        thread=thread,
    )

    assert "앞 대화" in llm.calls[2].user
    assert "정유민, 김하늘, 한예린" in llm.calls[2].user
    assert "대상 지원자: C2 김하늘" in llm.calls[3].user


async def test_subject_from_previous_turn(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    asked = make_context(
        sample_applicants, sample_company, sample_posting, message="@김하늘 강점은?", mentions=["김하늘"]
    )
    thread = thread_of(asked)
    llm = FakeLlm(
        RootRoute(kind="ANSWER"),
        RootAnswer(message="은행 경력이에요."),
        RootRoute(kind="EDIT", edit=EditAction.REMOVE, previous_ref="subject"),
    )

    await run_plan(llm, asked, saver=saver, thread=thread)
    plan = await run_plan(
        llm,
        context_with(sample_applicants, sample_company, sample_posting, "아까 그 사람 빼줘"),
        saver=saver,
        thread=thread,
    )

    assert (plan.edit, plan.targets) == (EditAction.REMOVE, [sample_applicants["김하늘"].info.application_id])


async def test_missing_previous_result_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    context = context_with(sample_applicants, sample_company, sample_posting, "그중 두 번째 사람 강점은?")

    plan = await run_plan(
        FakeLlm(RootRoute(kind="ANSWER", previous_ref="result", ordinal=2)),
        context,
        saver=saver,
        thread=thread_of(context),
    )

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_PREVIOUS)


async def test_remembered_candidate_must_be_in_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    asked = make_context(
        sample_applicants, sample_company, sample_posting, message="@김하늘 강점은?", mentions=["김하늘"]
    )
    thread = thread_of(asked)
    llm = FakeLlm(
        RootRoute(kind="ANSWER"),
        RootAnswer(message="은행 경력이에요."),
        RootRoute(kind="EDIT", edit=EditAction.REMOVE, previous_ref="subject"),
    )
    await run_plan(llm, asked, saver=saver, thread=thread)
    later = context_with(sample_applicants, sample_company, sample_posting, "아까 그 사람 빼줘")
    kim = sample_applicants["김하늘"].info.application_id
    later = later.model_copy(update={"candidates": [row for row in later.candidates if row.application_id != kim]})

    plan = await run_plan(llm, later, saver=saver, thread=thread)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_PREVIOUS)


def interview_context(
    applicants: Applicants, company: CompanyProfile, posting: PostingContent, message: str
) -> ChatContext:
    return make_context(
        applicants,
        company,
        posting,
        message=message,
        mentions=["정유민"] if "@정유민" in message else [],
        stage_type=StageType.INTERVIEW,
        previous_types=(StageType.DOCUMENT,),
    )


FOCUS = "정산 배치를 줄인 설계 판단을 기술 심화로 확인"


async def test_reason_question_reads_previous_turns(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    first = interview_context(sample_applicants, sample_company, sample_posting, "@정유민 면접 질문 만들어줘")
    thread = thread_of(first)
    llm = FakeLlm(
        RootRoute(kind="ANSWER", interview_questions=True),
        RootQuestionFocus(items=[QuestionFocusItem(candidate="C1", focus=FOCUS)]),
        RootRoute(kind="ANSWER", previous_ref="subject"),
        ToolCall("get_previous_turns"),
        RootAnswer(message="정산 배치 설계 판단을 확인하려고 만들었어요."),
    )

    await run_plan(llm, first, saver=saver, thread=thread)
    plan = await run_plan(
        llm,
        interview_context(sample_applicants, sample_company, sample_posting, "3번 질문은 왜 만든 거야?"),
        saver=saver,
        thread=thread,
    )

    assert plan.message == "정산 배치 설계 판단을 확인하려고 만들었어요."
    tool_result = llm.calls[-1].user
    assert "[tool get_previous_turns]" in tool_result
    assert FOCUS in tool_result
    assert "@정유민 면접 질문 만들어줘" in tool_result


async def test_refine_uses_previous_subject(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    first = interview_context(sample_applicants, sample_company, sample_posting, "@정유민 면접 질문 만들어줘")
    thread = thread_of(first)
    llm = FakeLlm(
        RootRoute(kind="ANSWER", interview_questions=True),
        RootQuestionFocus(items=[QuestionFocusItem(candidate="C1", focus=FOCUS)]),
        RootRoute(kind="ANSWER", interview_questions=True, previous_ref="subject"),
        RootQuestionFocus(items=[QuestionFocusItem(candidate="C1", focus="장애 대응을 더 기술적으로")]),
    )

    await run_plan(llm, first, saver=saver, thread=thread)
    plan = await run_plan(
        llm,
        interview_context(sample_applicants, sample_company, sample_posting, "좀 더 기술적으로 다시 해줘"),
        saver=saver,
        thread=thread,
    )

    jung = sample_applicants["정유민"].info.application_id
    assert plan.question_targets == [jung]
    focus = FOCUS_WITH_REQUEST.format(focus="장애 대응을 더 기술적으로", request="좀 더 기술적으로 다시 해줘")
    assert plan.question_focus == {jung: focus}


async def test_result_ref_falls_back_to_latest_turn_with_targets(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    first = interview_context(sample_applicants, sample_company, sample_posting, "@정유민 면접 질문 만들어줘")
    thread = thread_of(first)
    llm = FakeLlm(
        RootRoute(kind="ANSWER", interview_questions=True),
        RootQuestionFocus(items=[QuestionFocusItem(candidate="C1", focus=FOCUS)]),
        RootRoute(kind="ANSWER", previous_ref="result"),
        RootAnswer(message="이유예요."),
    )

    await run_plan(llm, first, saver=saver, thread=thread)
    plan = await run_plan(
        llm,
        interview_context(sample_applicants, sample_company, sample_posting, "방금 만든 질문은 왜 만든 거야?"),
        saver=saver,
        thread=thread,
    )

    assert plan.intent is Intent.ANSWER
    assert "대상 지원자: C1 정유민" in llm.calls[-1].user


async def test_saved_state_keeps_only_json_values(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="@김하늘 빼줘", mentions=["김하늘"]
    )
    thread = thread_of(context)

    plan = await run_plan(FakeLlm(RootRoute(kind="EDIT", edit=EditAction.REMOVE)), context, saver=saver, thread=thread)

    saved = await saver.aget_tuple({"configurable": {"thread_id": thread.id}})
    assert saved is not None
    values = saved.checkpoint["channel_values"]
    assert values.get("targets") is None and values.get("route") is None and values.get("plan") is None
    assert plan.edit is EditAction.REMOVE


async def test_empty_latest_result_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    found = context_with(sample_applicants, sample_company, sample_posting, "금융 경험 있는 사람 찾아줘")
    thread = thread_of(found)
    llm = FakeLlm(
        RootRoute(kind="FIND", concepts=["금융 도메인 경험"]),
        FINANCE_FOUND,
        RootRoute(kind="FIND", concepts=["양자 컴퓨팅"]),
        RootRoute(kind="ANSWER", previous_ref="result", ordinal=2),
    )

    await run_plan(llm, found, saver=saver, thread=thread)
    await run_plan(
        llm,
        context_with(sample_applicants, sample_company, sample_posting, "양자 컴퓨팅 경험자 찾아줘"),
        saver=saver,
        thread=thread,
    )
    plan = await run_plan(
        llm,
        context_with(sample_applicants, sample_company, sample_posting, "그중 두 번째 사람 강점은?"),
        saver=saver,
        thread=thread,
    )

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_PREVIOUS)


async def test_among_them_after_empty_find_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 실제 모델은 "그중 첫 번째"를 subject로도 표시한다. "그중"은 찾기 결과라 아무도 못 찾은 새 찾기 뒤에는 되묻는다
    saver = InMemorySaver()
    found = context_with(sample_applicants, sample_company, sample_posting, "금융 경험 있는 사람 찾아줘")
    thread = thread_of(found)
    llm = FakeLlm(
        RootRoute(kind="FIND", concepts=["금융 도메인 경험"]),
        FINANCE_FOUND,
        RootRoute(kind="FIND", mode=SelectionMode.REPLACE, concepts=["양자 컴퓨팅"]),
        RootRoute(kind="ANSWER", previous_ref="subject", ordinal=1),
    )

    await run_plan(llm, found, saver=saver, thread=thread)
    await run_plan(
        llm,
        context_with(sample_applicants, sample_company, sample_posting, "양자 컴퓨팅 경험자 찾아줘"),
        saver=saver,
        thread=thread,
    )
    plan = await run_plan(
        llm,
        context_with(sample_applicants, sample_company, sample_posting, "그중 첫 번째 사람 강점은?"),
        saver=saver,
        thread=thread,
    )

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_PREVIOUS)


async def test_checked_beats_previous_without_words(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    found = context_with(sample_applicants, sample_company, sample_posting, "금융 경험 있는 사람 찾아줘")
    thread = thread_of(found)
    llm = FakeLlm(
        RootRoute(kind="FIND", concepts=["금융 도메인 경험"]),
        FINANCE_FOUND,
        RootRoute(kind="ANSWER", previous_ref="result", compare=True),
        CandidateNotes(items=[]),
        CandidateNotes(items=[]),
        MultiSummary(message="비교했어요."),
    )
    compare = make_context(
        sample_applicants, sample_company, sample_posting, message="둘 비교해줘", checked=["박서준", "이도윤"]
    )

    await run_plan(llm, found, saver=saver, thread=thread)
    await run_plan(llm, compare, saver=saver, thread=thread)

    notes = [call.user for call in llm.calls if call.output is CandidateNotes]
    assert ["정리할 지원자: C3 박서준" in notes[0], "정리할 지원자: C4 이도윤" in notes[1]] == [True, True]
    assert not any("정유민" in user or "한예린" in user for user in notes)


async def test_previous_words_beat_checked(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    asked = make_context(
        sample_applicants, sample_company, sample_posting, message="@김하늘 강점은?", mentions=["김하늘"]
    )
    thread = thread_of(asked)
    llm = FakeLlm(
        RootRoute(kind="ANSWER"),
        RootAnswer(message="은행 경력이에요."),
        RootRoute(kind="EDIT", edit=EditAction.REMOVE, previous_ref="subject"),
    )
    later = make_context(
        sample_applicants, sample_company, sample_posting, message="아까 그 사람 빼줘", checked=["정유민"]
    )

    await run_plan(llm, asked, saver=saver, thread=thread)
    plan = await run_plan(llm, later, saver=saver, thread=thread)

    assert plan.targets == [sample_applicants["김하늘"].info.application_id]


async def test_empty_narrow_keeps_result(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    found = context_with(sample_applicants, sample_company, sample_posting, "금융 경험 있는 사람 찾아줘")
    thread = thread_of(found)
    llm = FakeLlm(
        RootRoute(kind="FIND", concepts=["금융 도메인 경험"]),
        FINANCE_FOUND,
        RootRoute(kind="FIND", mode=SelectionMode.NARROW, concepts=["양자 컴퓨팅"]),
        RootRoute(kind="ANSWER", previous_ref="result", ordinal=2),
        RootAnswer(message="강점이에요."),
    )

    await run_plan(llm, found, saver=saver, thread=thread)
    narrowed = await run_plan(
        llm,
        context_with(sample_applicants, sample_company, sample_posting, "그중 양자 컴퓨팅 경험 있는 사람만"),
        saver=saver,
        thread=thread,
    )
    await run_plan(
        llm,
        context_with(sample_applicants, sample_company, sample_posting, "그중 두 번째 사람 강점은?"),
        saver=saver,
        thread=thread,
    )

    assert narrowed.intent is Intent.ANSWER
    assert "대상 지원자: C2 김하늘" in llm.calls[-1].user


async def test_find_turn_records_only_found(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    asked = make_context(
        sample_applicants, sample_company, sample_posting, message="@김하늘 강점은?", mentions=["김하늘"]
    )
    thread = thread_of(asked)
    llm = FakeLlm(
        RootRoute(kind="ANSWER"),
        RootAnswer(message="은행 경력이에요."),
        RootRoute(kind="FIND", concepts=["양자 컴퓨팅"], previous_ref="subject"),
        RootRoute(kind="EDIT", edit=EditAction.REMOVE, previous_ref="subject"),
    )

    await run_plan(llm, asked, saver=saver, thread=thread)
    await run_plan(
        llm,
        context_with(sample_applicants, sample_company, sample_posting, "양자 컴퓨팅 경험자 찾아줘"),
        saver=saver,
        thread=thread,
    )
    plan = await run_plan(
        llm,
        context_with(sample_applicants, sample_company, sample_posting, "아까 그 사람 빼줘"),
        saver=saver,
        thread=thread,
    )

    assert (await saved_turns(saver, thread))[1]["targets"] == []
    assert plan.targets == [sample_applicants["김하늘"].info.application_id]


async def test_clear_with_checked_keeps_subject(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    saver = InMemorySaver()
    asked = make_context(
        sample_applicants, sample_company, sample_posting, message="@김하늘 강점은?", mentions=["김하늘"]
    )
    thread = thread_of(asked)
    llm = FakeLlm(
        RootRoute(kind="ANSWER"),
        RootAnswer(message="은행 경력이에요."),
        RootRoute(kind="EDIT", edit=EditAction.CLEAR),
        RootRoute(kind="EDIT", edit=EditAction.REMOVE, previous_ref="subject"),
    )
    cleared = make_context(sample_applicants, sample_company, sample_posting, message="선택 비워줘", checked=["정유민"])

    await run_plan(llm, asked, saver=saver, thread=thread)
    await run_plan(llm, cleared, saver=saver, thread=thread)
    plan = await run_plan(
        llm,
        context_with(sample_applicants, sample_company, sample_posting, "아까 그 사람 빼줘"),
        saver=saver,
        thread=thread,
    )

    assert plan.targets == [sample_applicants["김하늘"].info.application_id]
