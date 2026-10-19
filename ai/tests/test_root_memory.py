from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from root_context import make_context

from hiremate_ai.agents.root.answer import AnswerItem, RootAnswer
from hiremate_ai.agents.root.find import RecheckItem, RecheckResult
from hiremate_ai.agents.root.graph import RootThread, run_plan
from hiremate_ai.agents.root.route import NO_PREVIOUS, RootRoute
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, EditAction, Intent
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent
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
