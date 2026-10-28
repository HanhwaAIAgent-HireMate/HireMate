from typing import Any
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from root_context import extra_row, form_call, make_context

from hiremate_ai.agents.guardrails import BLOCKED_REPLY
from hiremate_ai.agents.root.find import RecheckItem, RecheckResult
from hiremate_ai.agents.root.graph import (
    BUDGET_EXHAUSTED,
    CHECKING,
    NOT_FINISHED,
    NOT_IN_STAGE,
    VALIDATION_FAILED,
    RootThread,
    build_root_graph,
    run_plan,
    stream_plan,
)
from hiremate_ai.agents.root.handlers import DECISION_REPLY
from hiremate_ai.agents.root.review import ClaimJudgement, ClaimVerdict
from hiremate_ai.agents.root.types import ChatContext, ChatItem, ChatPlan, ChatStatus, EditAction, Intent
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.chat import LAST_CALL, LlmOutputError
from hiremate_ai.llm.fake import FakeLlm, LlmCall, ToolCall

type Applicants = dict[str, ApplicantDetail]


def context_of(applicants: Applicants, company: CompanyProfile, posting: PostingContent, **kwargs: Any) -> ChatContext:
    return make_context(applicants, company, posting, **{"message": "요청", **kwargs})


def thread_of(context: ChatContext) -> RootThread:
    return RootThread(
        id=f"{context.company.company_id}:{context.stage_id}:{uuid4()}",
        company_id=context.company.company_id,
        stage_id=context.stage_id,
    )


def supported(*ids: str) -> ClaimJudgement:
    return ClaimJudgement(verdicts=[ClaimVerdict(id=value, verdict="SUPPORTED") for value in ids])


def analysis_answer(candidate: str | None = "C1", *refs: str) -> ToolCall:
    item = {
        "candidate": candidate,
        "label": "근거",
        "text": "확인할 점이 있어요.",
        "status": "CHECK",
        "refs": list(refs),
    }
    return form_call("answer", message="정리했어요.", items=[item])


async def test_blocked_skips_model(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, message="30대 남자 찾아줘")
    llm = FakeLlm()

    assert await run_plan(llm, context) == ChatPlan.answer(Intent.BLOCKED, BLOCKED_REPLY)
    assert llm.calls == []


async def test_mention_outside_stage_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=[uuid4()])
    llm = FakeLlm()

    plan = await run_plan(llm, context)

    assert plan.message == NOT_IN_STAGE and llm.calls == []


async def test_model_failure_returns_clarification(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    def broken(call: LlmCall) -> ToolCall:
        raise LlmOutputError("모델 출력을 확인하지 못했다")

    context = context_of(sample_applicants, sample_company, sample_posting, message="음")

    assert await run_plan(FakeLlm(broken), context) == ChatPlan.answer(Intent.CLARIFY, NOT_FINISHED)


async def test_repeated_invalid_plan_ends_with_validation_message(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    bad = form_call("answer", scope={"picks": ["C99"]})

    plan = await run_plan(FakeLlm(bad, bad), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, VALIDATION_FAILED)


async def test_budget_exceeded_message(
    monkeypatch: pytest.MonkeyPatch,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    monkeypatch.setattr(settings, "llm_agent_max_calls", 3)
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    read = ToolCall("stage_overview")
    llm = FakeLlm(form_call("answer", scope={"sources": ["mentions"]}), read, read, read)

    plan = await run_plan(llm, context)

    assert plan.message == BUDGET_EXHAUSTED and plan.items == []


async def test_analysis_leaves_one_call_for_review(
    monkeypatch: pytest.MonkeyPatch,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    monkeypatch.setattr(settings, "llm_agent_max_calls", 3)
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    item = {"candidate": "C1", "label": "결정", "text": "아직 미결정이에요.", "status": "OK", "refs": ["E1"]}
    llm = FakeLlm(
        form_call("answer", scope={"sources": ["mentions"]}),
        form_call("answer", message="정리했어요.", items=[item]),
        supported("I1", "M"),
    )

    plan = await run_plan(llm, context)

    assert LAST_CALL in llm.calls[1].user
    assert [call.output.__name__ for call in llm.calls] == ["RootPlan", "AnalysisReply", "ClaimJudgement"]
    assert plan.items[0].status == "OK"


async def test_decision_only_guides_the_user_to_the_screen(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, message="합격 처리해줘")

    plan = await run_plan(FakeLlm(form_call("decision")), context)

    assert plan.message == DECISION_REPLY and plan.targets == [] and plan.edit is None


async def test_homonym_is_asked_back_without_another_model_call(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, extra_rows=[extra_row("정유민")])
    llm = FakeLlm(form_call("edit", action="ADD", scope={"names": ["정유민"]}))

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY and "2명이에요" in plan.message and len(llm.calls) == 1


async def test_edit_path_runs_without_more_calls(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    llm = FakeLlm(form_call("edit", action="ADD", scope={"sources": ["mentions"]}))

    plan = await run_plan(llm, context)

    assert (plan.intent, plan.edit, plan.targets) == (Intent.EDIT, EditAction.ADD, context.mentions)


async def test_find_path_records_result(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, message="금융 경험 찾아줘")
    saver, thread = InMemorySaver(), thread_of(context)
    query = {"mode": "replace", "concepts": ["금융 도메인 경험"], "min_score": None}
    recheck = RecheckResult(results=[RecheckItem(candidate_no=1, met=True, sentence_nos=[1])])
    llm = FakeLlm(form_call("find", query=query, scope={}, remove=False), recheck)

    plan = await run_plan(llm, context, saver=saver, thread=thread)

    saved = await saver.aget_tuple({"configurable": {"thread_id": thread.id}})
    assert saved is not None
    assert plan.intent is Intent.FIND and len(plan.targets) == 1
    assert saved.checkpoint["channel_values"]["result"] == [str(plan.targets[0])]


async def test_answer_path_runs_review(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    llm = FakeLlm(
        form_call("answer", scope={"sources": ["mentions"]}), analysis_answer("C1", "E1"), supported("I1", "M")
    )

    plan = await run_plan(llm, context)

    assert [call.output.__name__ for call in llm.calls] == ["RootPlan", "AnalysisReply", "ClaimJudgement"]
    assert plan.intent is Intent.ANSWER and plan.items[0].application_id == context.mentions[0]
    assert plan.sources == ["전형 결과"]


async def test_questions_with_checks_go_through_analysis(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(
        sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW, mentions=["정유민"]
    )
    focus = [{"candidate": "C1", "text": "결제 경험의 본인 역할", "refs": ["E1"]}]
    llm = FakeLlm(
        form_call("questions", scope={"sources": ["mentions"]}, checks="documents", replace=True),
        form_call("questions", message="정리했어요.", focus=focus),
        supported("I1", "M"),
    )

    plan = await run_plan(llm, context)

    assert plan.question_targets == context.mentions and plan.question_replace is True
    assert "결제 경험의 본인 역할" in plan.question_focus[context.mentions[0]]


async def test_nothing_left_after_review_asks_back(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    unrelated = ClaimJudgement(
        verdicts=[ClaimVerdict(id="I1", verdict="UNRELATED"), ClaimVerdict(id="M", verdict="SUPPORTED")]
    )
    llm = FakeLlm(form_call("answer", scope={"sources": ["mentions"]}), analysis_answer("C1", "E1"), unrelated)

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY and plan.items == []


async def test_stream_finishes_after_verified_items(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    llm = FakeLlm(
        form_call("answer", scope={"sources": ["mentions"]}), analysis_answer("C1", "E1"), supported("I1", "M")
    )

    events = [event async for event in stream_plan(llm, context)]

    names = [name for name, _ in events]
    assert events[0] == ("status", ChatStatus(text=CHECKING))
    assert names[-1] == "done" and names[-2] == "item"
    assert isinstance(events[-2][1], ChatItem)


async def test_graph_records_streamed_steps_and_seconds(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(
        form_call("answer", scope={"sources": ["mentions"]}), analysis_answer("C1", "E1"), supported("I1", "M")
    )

    await run_plan(llm, context, saver=saver, thread=thread)

    saved = await saver.aget_tuple({"configurable": {"thread_id": thread.id}})
    assert saved is not None
    turn = saved.checkpoint["channel_values"]["turns"][-1]
    assert turn["steps"][0] == CHECKING and "요청에 맞는 답변을 준비하고 있어요" in turn["steps"]
    assert isinstance(turn["seconds"], int)


async def test_checkpoint_has_no_run_channel(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    saver, thread = InMemorySaver(), thread_of(context)
    llm = FakeLlm(
        form_call("answer", scope={"sources": ["mentions"]}), analysis_answer("C1", "E1"), supported("I1", "M")
    )

    await run_plan(llm, context, saver=saver, thread=thread)

    saved = await saver.aget_tuple({"configurable": {"thread_id": thread.id}})
    assert saved is not None
    assert "run" not in saved.checkpoint["channel_values"]
    assert sample_applicants["정유민"].documents[0].text not in str(saved.checkpoint)


def test_graph_draws_every_branch() -> None:
    edges = {(edge.source, edge.target) for edge in build_root_graph(FakeLlm()).get_graph().edges}

    assert {
        ("guard", "plan"),
        ("guard", "record"),
        ("plan", "find"),
        ("plan", "edit"),
        ("plan", "questions"),
        ("plan", "analyze"),
        ("plan", "reply"),
        ("plan", "record"),
        ("analyze", "review"),
        ("analyze", "record"),
        ("review", "record"),
    } <= edges
