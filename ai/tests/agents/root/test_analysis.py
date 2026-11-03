from typing import Any
from uuid import UUID

from root_context import Recorder, make_context

from hiremate_ai.agents.guardrails import BLOCKED_REPLY
from hiremate_ai.agents.root.analysis import (
    BAD_FIND,
    FOREIGN_REFS,
    NO_ITEMS,
    SEARCH_BUDGET,
    UNKNOWN_REFS,
    AnalysisRun,
    AnswerOutput,
    FindOutput,
    analysis_run,
    run_analysis,
)
from hiremate_ai.agents.root.find import RecheckItem, RecheckResult
from hiremate_ai.agents.root.toolkit import ProfileLine, ProfileView, RootToolContext, RootToolkit, keyword_search
from hiremate_ai.agents.root.types import ChatContext
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, InterviewerMemo, PostingContent, StageType
from hiremate_ai.llm.chat import model_call_budget
from hiremate_ai.llm.fake import FakeLlm, ToolCall

type Applicants = dict[str, ApplicantDetail]


def context_of(applicants: Applicants, company: CompanyProfile, posting: PostingContent, **kwargs: Any) -> ChatContext:
    return make_context(applicants, company, posting, **{"message": "이 사람 협업 경험은 어때?", **kwargs})


def toolkit_with_profiles(*, profiled: set[UUID] | None = None) -> RootToolkit:
    async def profile(scope: RootToolContext, application_id: UUID) -> ProfileView | None:
        if profiled is not None and application_id not in profiled:
            return None
        line = ProfileLine("EXPERIENCE", "결제 API 개발", "결제 API를 개발했다.", "이력서", "EVIDENCED", "application")
        return ProfileView(front="분석 상태: 분석 완료", lines=[line])

    return RootToolkit(search=keyword_search, profile=profile)


def answer(*refs: str, candidate: str | None = "C1") -> ToolCall:
    item = {
        "candidate": candidate,
        "label": "협업",
        "text": "결제 API를 개발했어요",
        "status": "OK",
        "refs": list(refs),
    }
    return ToolCall("answer", {"message": "정리했어요.", "items": [item]})


def run_of(context: ChatContext, *names: str) -> AnalysisRun:
    rows = [row for name in names for row in context.candidates if row.name == name]
    return analysis_run(context, rows)


async def test_few_targets_get_profiles_preloaded(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    llm = FakeLlm(answer("E2"))
    run = run_of(context, "정유민")

    reply = await run_analysis(llm, toolkit_with_profiles(), run, task="answer", checks="none", progress=Recorder())

    assert isinstance(reply.form, AnswerOutput) and reply.form.items[0].refs == ["E2"]
    assert "E2 [근거 확인] 결제 API 개발" in llm.calls[0].user and len(llm.calls) == 1
    assert "[대상] C1 정유민" in llm.calls[0].user


async def test_no_targets_get_stage_overview(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, message="미결정 몇 명 남았어?")
    llm = FakeLlm(answer("E1", candidate=None))

    await run_analysis(llm, toolkit_with_profiles(), run_of(context), task="answer", checks="none", progress=Recorder())

    assert "미결정 8명" in llm.calls[0].user and "결제 API 개발" not in llm.calls[0].user


async def test_many_targets_get_one_line_summaries(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    names = list(sample_applicants)[:6]
    llm = FakeLlm(ToolCall("clarify", {"message": "누구를 비교할까요?"}))

    await run_analysis(
        llm, toolkit_with_profiles(), run_of(context, *names), task="answer", checks="none", progress=Recorder()
    )

    assert "결제 API 개발" not in llm.calls[0].user
    assert all(name in llm.calls[0].user for name in names)


async def test_memos_preloaded_only_for_memos(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW)
    row = context.candidates[0]
    memo = InterviewerMemo(stage_id=context.stage_id, stage_name="1차 면접", text="리더 역할 다시 확인")
    context = context.model_copy(update={"interviewer_memos": {row.application_id: [memo]}})
    with_memos = FakeLlm(
        ToolCall("questions", {"message": "정리했어요.", "focus": []}), ToolCall("clarify", {"message": "?"})
    )
    without = FakeLlm(ToolCall("clarify", {"message": "?"}))

    await run_analysis(
        with_memos,
        toolkit_with_profiles(),
        run_of(context, row.name),
        task="questions",
        checks="memos",
        progress=Recorder(),
    )
    await run_analysis(
        without, toolkit_with_profiles(), run_of(context, row.name), task="answer", checks="none", progress=Recorder()
    )

    assert "리더 역할 다시 확인" in with_memos.calls[0].user
    assert "리더 역할 다시 확인" not in without.calls[0].user


async def test_read_application_detail_without_saved_review(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    llm = FakeLlm(ToolCall("read_candidates", {"candidates": ["C1"], "detail": "application"}), answer("E2"))
    progress = Recorder()

    await run_analysis(
        llm, toolkit_with_profiles(), run_of(context, "정유민"), task="answer", checks="none", progress=progress
    )

    assert "저장된 서류 분석이 없어요" in llm.calls[1].user
    # 도구 단계는 Root 단계 아래 한 칸 들여 지원자 이름과 함께 낸다
    assert progress.statuses[1] == "정유민의 서류 분석을 읽고 있어요"
    assert progress.depths[:2] == [0, 1]


async def test_search_then_find_returns_search_number(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, message="이 사람이랑 비슷한 사람 더 있어?")
    query = {"mode": "replace", "concepts": ["결제"], "min_score": None}
    recheck = RecheckResult(results=[RecheckItem(candidate_no=1, met=True, sentence_nos=[1])])
    llm = FakeLlm(ToolCall("search_candidates", {"query": query}), recheck, ToolCall("find", {"result": "S1"}))
    run = run_of(context, "정유민")

    reply = await run_analysis(llm, toolkit_with_profiles(), run, task="answer", checks="none", progress=Recorder())

    assert isinstance(reply.form, FindOutput) and reply.form.result == "S1"
    assert "S1" in run.searches and run.queries["S1"].concepts == ["결제"]


async def test_search_recheck_keeps_the_answer_and_review_calls(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    query = {"mode": "replace", "concepts": ["결제"], "min_score": None}
    llm = FakeLlm(ToolCall("search_candidates", {"query": query}), answer("E2"))

    with model_call_budget(3):
        reply = await run_analysis(
            llm, toolkit_with_profiles(), run_of(context, "정유민"), task="answer", checks="none", progress=Recorder()
        )

    assert SEARCH_BUDGET in llm.calls[1].user
    assert isinstance(reply.form, AnswerOutput)


async def test_unknown_ref_is_rewritten_once(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    llm = FakeLlm(answer("E99"), answer("E2"))

    await run_analysis(
        llm, toolkit_with_profiles(), run_of(context, "정유민"), task="answer", checks="none", progress=Recorder()
    )

    assert UNKNOWN_REFS in llm.calls[1].user


async def test_foreign_ref_is_rewritten(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민", "김하늘"])
    llm = FakeLlm(answer("E4", candidate="C1"), answer("E2", candidate="C1"))

    await run_analysis(
        llm,
        toolkit_with_profiles(),
        run_of(context, "정유민", "김하늘"),
        task="answer",
        checks="none",
        progress=Recorder(),
    )

    assert FOREIGN_REFS in llm.calls[1].user


async def test_common_item_can_cite_candidate_lines(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, message="미결정 몇 명이야?")
    run = run_of(context)
    llm = FakeLlm(answer("E1", "E6", candidate=None))

    reply = await run_analysis(llm, toolkit_with_profiles(), run, task="answer", checks="none", progress=Recorder())

    line = run.ledger.get("E6")
    assert line is not None and line.application_id == context.candidates[0].application_id
    assert isinstance(reply.form, AnswerOutput) and len(llm.calls) == 1


async def test_unknown_search_number_is_rewritten(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    llm = FakeLlm(ToolCall("find", {"result": "S3"}), answer("E2"))

    await run_analysis(
        llm, toolkit_with_profiles(), run_of(context, "정유민"), task="answer", checks="none", progress=Recorder()
    )

    assert BAD_FIND in llm.calls[1].user


async def test_search_blocks_discriminatory(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    query = {"mode": "replace", "concepts": ["기혼 여성"], "min_score": None}
    llm = FakeLlm(
        ToolCall("search_candidates", {"query": query}), ToolCall("clarify", {"message": "다른 조건을 알려 주세요."})
    )

    await run_analysis(llm, toolkit_with_profiles(), run_of(context), task="answer", checks="none", progress=Recorder())

    assert BLOCKED_REPLY in llm.calls[1].user


async def test_message_only_answer_is_rewritten_once(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, message="미결정 몇 명 남았어?")
    llm = FakeLlm(ToolCall("answer", {"message": "미결정 8명이에요.", "items": []}), answer("E1", candidate=None))

    reply = await run_analysis(
        llm, toolkit_with_profiles(), run_of(context), task="answer", checks="none", progress=Recorder()
    )

    assert NO_ITEMS in llm.calls[1].user
    assert isinstance(reply.form, AnswerOutput) and reply.form.items
