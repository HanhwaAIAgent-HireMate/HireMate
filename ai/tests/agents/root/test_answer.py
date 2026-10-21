import asyncio
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel
from root_context import make_context, save_sample_profiles, sessions_of
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.root import answer
from hiremate_ai.agents.root.answer import (
    BULK,
    FOCUSED,
    MULTI_FALLBACK,
    NO_QUESTION_TARGET,
    NOT_CHECKED,
    NOT_FINISHED,
    AnswerEvidence,
    AnswerItem,
    CandidateNotes,
    MultiSummary,
    QuestionFocusItem,
    RootAnswer,
    RootQuestionFocus,
    plan_answer,
    plan_questions,
)
from hiremate_ai.agents.root.route import RootRoute
from hiremate_ai.agents.root.targets import resolve
from hiremate_ai.agents.root.toolkit import (
    ANSWER_TOOLS,
    RootToolContext,
    RootToolkit,
    default_toolkit,
    keyword_search,
    profile_toolkit,
)
from hiremate_ai.agents.root.turns import Turn, TurnItem
from hiremate_ai.agents.root.types import (
    ChatContext,
    ChatPlan,
    Intent,
    InterviewQuestion,
    InterviewView,
    QuestionSource,
)
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.chat import LlmOutputError, ToolAgent
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.fake import FakeLlm, FakeReply, LlmCall, ToolCall

type Applicants = dict[str, ApplicantDetail]

ASK = RootRoute(kind="ANSWER")
BATCH = "MySQL 정산 테이블을 파티셔닝해 월말 정산 배치 시간을 40% 줄였습니다."
RETRO = (
    "정산 배치 지연을 줄이기 위해 팀과 함께 처리 구조를 바꿨고, "
    "장애 회고를 문서로 남겨 같은 문제가 반복되지 않게 했습니다."
)


def context_for(
    applicants: Applicants,
    company: CompanyProfile,
    posting: PostingContent,
    stage_type: StageType = StageType.DOCUMENT,
    interviews: Mapping[UUID, InterviewView] | None = None,
) -> ChatContext:
    return make_context(
        applicants,
        company,
        posting,
        message="@정유민 강점이 뭐야?",
        mentions=["정유민"],
        stage_type=stage_type,
        interviews=interviews,
    )


def answered(*items: AnswerItem, message: str = "정유민 님의 강점이에요.") -> RootAnswer:
    return RootAnswer(message=message, items=list(items))


async def ask(llm: LlmClient, context: ChatContext, toolkit: RootToolkit | None = None) -> ChatPlan:
    return await plan_answer(llm, ASK, context, resolve(context), toolkit or default_toolkit())


async def test_answer_flows_through_tools(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    item = AnswerItem(
        candidate="C1",
        label="강점",
        text="정산 배치 시간을 줄였다",
        status="OK",
        evidence=[AnswerEvidence(sentence=BATCH, source="이력서")],
    )
    llm = FakeLlm(ToolCall("get_candidate_documents", {"candidate": "C1"}), answered(item))

    plan = await ask(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.message == "정유민 님의 강점이에요."
    assert plan.items[0].application_id == sample_applicants["정유민"].info.application_id
    assert (plan.items[0].label, plan.items[0].status) == ("강점", "OK")
    assert plan.sources == ["이력서"]
    assert plan.agents == []
    assert plan.targets == [] and plan.question_targets == []
    assert "C1 정유민" in llm.calls[0].user
    assert [call.agent for call in llm.calls] == ["root", "root"]


async def test_answer_reads_profile_and_keeps_its_evidence(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    await save_sample_profiles(db_session, sample_company, sample_applicants)
    context = context_for(sample_applicants, sample_company, sample_posting)
    evidence = AnswerEvidence(sentence="한빛카드 결제플랫폼팀 2022.03 ~ 현재", source="이력서")
    item = AnswerItem(candidate="C1", label="도메인", text="카드 결제 · 정산", status="OK", evidence=[evidence])
    llm = FakeLlm(ToolCall("get_candidate_profile", {"candidate": "C1"}), answered(item))

    plan = await ask(llm, context, profile_toolkit(sessions_of(db_session)))

    assert "[도메인] 금융 (카드 결제 · 정산)" in llm.calls[1].user
    assert [(item.label, item.status) for item in plan.items] == [("도메인", "OK")]
    assert plan.sources == ["이력서"]


async def test_unverified_evidence_turns_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    made_up = AnswerEvidence(sentence="10년 동안 증권사 시스템을 설계했습니다.", source="이력서")
    llm = FakeLlm(answered(AnswerItem(candidate="C1", label="강점", text="증권 경력", status="OK", evidence=[made_up])))

    plan = await ask(llm, context)

    assert plan.items[0].status == "CHECK"
    assert plan.sources == []


async def test_ok_without_evidence_about_a_candidate_turns_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        answered(
            AnswerItem(candidate="C1", label="강점", text="리더십", status="OK"),
            AnswerItem(candidate=None, label="미결정", text="8명", status="OK"),
        )
    )

    plan = await ask(llm, context)

    assert [item.status for item in plan.items] == ["CHECK", "OK"]


async def test_wrong_document_label_is_corrected(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    evidence = AnswerEvidence(sentence=RETRO, source="이력서")
    llm = FakeLlm(answered(AnswerItem(candidate="C1", label="협업", text="회고", status="OK", evidence=[evidence])))

    plan = await ask(llm, context)

    assert plan.items[0].status == "OK"
    assert plan.sources == ["자기소개서"]


async def test_unknown_candidate_item_dropped(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        answered(
            AnswerItem(candidate="C42", label="강점", text="?", status="OK"),
            AnswerItem(candidate=None, label="요약", text="공고 조건과 비교했어요", status="OK"),
        )
    )

    plan = await ask(llm, context)

    assert [item.label for item in plan.items] == ["요약"]
    assert plan.items[0].application_id is None


async def test_interview_evidence_checked_against_records(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    jung = sample_applicants["정유민"].info.application_id
    question = InterviewQuestion(
        question_id=uuid4(),
        text="정산 배치는 어떻게 줄였나요?",
        source=QuestionSource.AI,
        answer="파티셔닝 기준을 월 단위로 정했습니다.",
    )
    view = InterviewView(application_id=jung, schedule=None, questions=[question], previous=[])
    context = context_for(
        sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW, interviews={jung: view}
    )
    kept = AnswerEvidence(sentence="파티셔닝 기준을 월 단위로 정했습니다.", source="면접 기록")
    dropped = AnswerEvidence(sentence="샤딩을 도입했습니다.", source="면접 기록")
    llm = FakeLlm(
        answered(
            AnswerItem(candidate="C1", label="답변", text="파티셔닝", status="OK", evidence=[kept]),
            AnswerItem(candidate="C1", label="답변", text="샤딩", status="OK", evidence=[dropped]),
        )
    )

    plan = await ask(llm, context)

    assert [item.status for item in plan.items] == ["OK", "CHECK"]
    assert plan.sources == ["면접 기록"]


async def test_timeout_clarifies(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(answer, "ANSWER_TIMEOUT_SECONDS", 0.01)

    def slow(call: LlmCall) -> ToolCall:
        time.sleep(0.05)
        return ToolCall("get_stage_summary")

    context = context_for(sample_applicants, sample_company, sample_posting)

    plan = await ask(FakeLlm(slow, answered()), context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NOT_FINISHED)


async def test_call_limit_clarifies(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_agent_max_calls", 2)
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(ToolCall("get_stage_summary"), ToolCall("get_stage_summary"), ToolCall("get_stage_summary"))

    plan = await ask(llm, context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NOT_FINISHED)


@tool
async def analyze_application(candidate: str, runtime: ToolRuntime[RootToolContext]) -> str:
    """지원 서류를 분석한다 (테스트용 하위 Agent 도구)."""
    runtime.context.called.append("analyze_application")
    return "분석 결과"


async def test_agents_from_called_tools(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    toolkit = RootToolkit(search=keyword_search, answer_tools=(*ANSWER_TOOLS, analyze_application))
    llm = FakeLlm(ToolCall("get_stage_summary"), ToolCall("analyze_application", {"candidate": "C1"}), answered())

    plan = await ask(llm, context, toolkit)

    assert plan.agents == ["Application Agent"]


QUESTIONS = RootRoute(kind="ANSWER", interview_questions=True)
FOCUS = "정산 배치를 줄일 때의 설계 판단과 장애 대응을 기술 심화로 확인"


def interview_context(
    applicants: Applicants,
    company: CompanyProfile,
    posting: PostingContent,
    *,
    mentions: Sequence[str] = (),
    checked: Sequence[str] = (),
) -> ChatContext:
    return make_context(
        applicants,
        company,
        posting,
        message="면접 질문 만들어줘",
        stage_type=StageType.INTERVIEW,
        previous_types=(StageType.DOCUMENT,),
        mentions=mentions,
        checked=checked,
    )


def focused(*items: QuestionFocusItem) -> RootQuestionFocus:
    return RootQuestionFocus(items=list(items))


async def make_questions(llm: FakeLlm, route: RootRoute, context: ChatContext) -> ChatPlan:
    return await plan_questions(llm, route, context, resolve(context), default_toolkit())


async def test_focus_for_mentioned(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    reason = AnswerItem(
        label="확인할 점", text="파티셔닝 기준", status="OK", evidence=[AnswerEvidence(sentence=BATCH, source="이력서")]
    )
    llm = FakeLlm(
        ToolCall("get_candidate_documents", {"candidate": "C1"}),
        focused(QuestionFocusItem(candidate="C1", focus=FOCUS, reasons=[reason])),
    )

    plan = await make_questions(llm, QUESTIONS, context)

    jung = sample_applicants["정유민"].info.application_id
    assert plan.intent is Intent.ANSWER
    assert plan.question_targets == [jung]
    assert plan.question_focus == {jung: FOCUS}
    assert plan.message == FOCUSED.format(count=1)
    assert (plan.items[0].application_id, plan.items[0].status) == (jung, "OK")
    assert plan.sources == ["이력서"]
    assert plan.agents == ["Interview Agent"]
    assert plan.targets == []


async def test_untargeted_refine_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm()

    plan = await make_questions(llm, QUESTIONS, context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NO_QUESTION_TARGET)
    assert llm.calls == []


async def test_bulk_skips_tool_loop(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm()

    plan = await make_questions(llm, RootRoute(kind="ANSWER", interview_questions=True, all_candidates=True), context)

    assert len(plan.question_targets) == 8
    assert plan.question_focus == {}
    assert plan.message == BULK.format(count=8)
    assert plan.agents == ["Interview Agent"]
    assert llm.calls == []


async def test_checked_targets_and_other_candidates_ignored(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting, checked=["김하늘", "박서준"])
    llm = FakeLlm(
        focused(
            QuestionFocusItem(candidate="C2", focus="은행 계정계 장애 대응 경험을 구체적으로"),
            QuestionFocusItem(candidate="C5", focus="대상이 아닌 지원자"),
        )
    )

    plan = await make_questions(llm, QUESTIONS, context)

    kim = sample_applicants["김하늘"].info.application_id
    park = sample_applicants["박서준"].info.application_id
    assert plan.question_targets == [kim, park]
    assert plan.question_focus == {kim: "은행 계정계 장애 대응 경험을 구체적으로"}


async def test_focus_failure_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    def broken(call: LlmCall) -> RootQuestionFocus:
        raise LlmOutputError("RootQuestionFocus 형식의 답을 받지 못했다")

    context = interview_context(sample_applicants, sample_company, sample_posting, mentions=["정유민"])

    plan = await make_questions(FakeLlm(broken), QUESTIONS, context)

    assert plan == ChatPlan.answer(Intent.CLARIFY, NOT_FINISHED)


async def test_single_target_item_gets_candidate(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    evidence = AnswerEvidence(sentence=BATCH, source="이력서")
    llm = FakeLlm(answered(AnswerItem(label="강점", text="정산 배치 개선", status="OK", evidence=[evidence])))

    plan = await ask(llm, context)

    assert plan.items[0].application_id == sample_applicants["정유민"].info.application_id
    assert (plan.items[0].status, plan.sources) == ("OK", ["이력서"])


async def test_ref_in_text_assigns_candidate_and_reads_as_name(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="지원자 경력 요약해줘")
    item = AnswerItem(label="경력", text="C2 김하늘은 은행 경력이 있다", status="OK")
    llm = FakeLlm(answered(item, message="C1 정유민과 C2를 비교했어요."))

    plan = await ask(llm, context)

    assert plan.items[0].application_id == sample_applicants["김하늘"].info.application_id
    assert plan.items[0].text == "김하늘은 은행 경력이 있다"
    assert plan.message == "정유민과 김하늘를 비교했어요." or plan.message == "정유민과 김하늘을 비교했어요."


async def test_unverifiable_evidence_without_candidate_turns_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="지원자 경력 요약해줘")
    evidence = AnswerEvidence(sentence=BATCH, source="이력서")
    llm = FakeLlm(answered(AnswerItem(label="공통점", text="둘 다 정산 경험", status="OK", evidence=[evidence])))

    plan = await ask(llm, context)

    assert (plan.items[0].application_id, plan.items[0].status) == (None, "CHECK")


def test_readable_keeps_name_with_digits(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    from root_context import extra_row

    from hiremate_ai.agents.root.answer import readable

    context = make_context(
        sample_applicants, sample_company, sample_posting, message="확인", extra_rows=[extra_row("지원자1")]
    )

    assert readable("C9 지원자1의 강점", context) == "지원자1의 강점"
    assert readable("C1 정유민은, C9는", context) == "정유민은, 지원자1는"


async def test_source_label_variants_are_checked(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    def item(sentence: str, source: str) -> AnswerItem:
        return AnswerItem(
            candidate="C1",
            label=source,
            text="근거",
            status="OK",
            evidence=[AnswerEvidence(sentence=sentence, source=source)],
        )

    llm = FakeLlm(
        answered(
            item("10년 동안 증권사 시스템을 설계했습니다.", "이력서 경력란"),
            item(RETRO, "자소서"),
            item("팀을 잘 이끈다", "느낌"),
            item("고객 신뢰를 최우선으로", "회사 소개"),
            item("가장 큰 결제 회사입니다", "회사 소개"),
        )
    )

    plan = await ask(llm, context)

    assert [entry.status for entry in plan.items] == ["CHECK", "OK", "CHECK", "OK", "CHECK"]
    assert plan.sources == ["자기소개서", "회사 소개"]


async def test_checked_applicants_are_answer_targets(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="체크한 두 사람 비교해줘",
        checked=["김하늘", "박서준"],
    )
    respond = by_candidate(PAIR)
    llm = FakeLlm(respond, respond, MultiSummary(message="비교했어요."))

    await ask(llm, context)

    assert "정리할 지원자: C2 김하늘" in llm.calls[0].user
    assert "정리할 지원자: C3 박서준" in llm.calls[1].user


KIM_ORACLE = "Oracle 원장 테이블 설계와 쿼리 튜닝을 맡았습니다."
PARK_TUNING = "PostgreSQL 쿼리를 튜닝해 주문 조회 p99를 1.2초에서 300ms로 줄였습니다."


def note(text: str, sentence: str) -> CandidateNotes:
    evidence = AnswerEvidence(sentence=sentence, source="이력서")
    return CandidateNotes(items=[AnswerItem(label="RDBMS", text=text, status="OK", evidence=[evidence])])


PAIR: dict[str, CandidateNotes | Exception] = {
    "C2 김하늘": note("Oracle 원장 설계", KIM_ORACLE),
    "C3 박서준": note("PostgreSQL 튜닝", PARK_TUNING),
}


def by_candidate(notes: Mapping[str, CandidateNotes | Exception]) -> Callable[[LlmCall], FakeReply]:
    """지원자별 정리 호출에 그 지원자의 응답을 준다. 정리 호출은 동시에 나가므로 순서가 아니라 지원자로 고른다."""

    def respond(call: LlmCall) -> FakeReply:
        for header, reply in notes.items():
            if f"정리할 지원자: {header}" in call.user:
                if isinstance(reply, Exception):
                    raise reply
                return reply
        raise AssertionError(f"모르는 지원자 정리 호출: {call.user[:60]}")

    return respond


def pair_context(applicants: Applicants, company: CompanyProfile, posting: PostingContent) -> ChatContext:
    return make_context(applicants, company, posting, message="두 사람 비교해줘", mentions=["김하늘", "박서준"])


def failing(call: LlmCall) -> FakeReply:
    raise LlmOutputError("형식에 맞는 답을 받지 못했다")


async def test_multi_target_runs_notes_then_summary(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = pair_context(sample_applicants, sample_company, sample_posting)
    respond = by_candidate(PAIR)
    summary = "김하늘은 원장 설계, 박서준은 쿼리 튜닝 경험이 있어요."
    llm = FakeLlm(respond, respond, MultiSummary(message=summary))

    plan = await ask(llm, context)

    assert [call.output for call in llm.calls] == [CandidateNotes, CandidateNotes, MultiSummary]
    kim, park = (sample_applicants[name].info.application_id for name in ("김하늘", "박서준"))
    assert [(item.application_id, item.status) for item in plan.items] == [(kim, "OK"), (park, "OK")]
    assert "Oracle 원장 설계" in llm.calls[2].user and "PostgreSQL 튜닝" in llm.calls[2].user
    assert (plan.intent, plan.message, plan.sources) == (Intent.ANSWER, summary, ["이력서"])


async def test_multi_prompts_hold_one_candidate(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = by_candidate(PAIR)
    llm = FakeLlm(respond, respond, MultiSummary(message="비교했어요."))

    await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    kim_call, park_call = llm.calls[0].user, llm.calls[1].user
    assert "새솔은행" in kim_call and "다온마켓" not in kim_call
    assert "다온마켓" in park_call and "새솔은행" not in park_call


async def test_multi_unverified_evidence_turns_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = by_candidate({**PAIR, "C3 박서준": note("은행 경력", "은행에서 10년 일했습니다.")})
    llm = FakeLlm(respond, respond, MultiSummary(message="비교했어요."))

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    assert [item.status for item in plan.items] == ["OK", "CHECK"]


async def test_multi_one_failure_marks_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = by_candidate({**PAIR, "C3 박서준": LlmOutputError("형식에 맞는 답을 받지 못했다")})
    llm = FakeLlm(respond, respond, MultiSummary(message="김하늘만 확인했어요."))

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    park = sample_applicants["박서준"].info.application_id
    assert plan.message == "김하늘만 확인했어요."
    assert (plan.items[1].application_id, plan.items[1].label, plan.items[1].text, plan.items[1].status) == (
        park,
        "확인할 점",
        NOT_CHECKED,
        "CHECK",
    )


async def test_multi_all_fail_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    llm = FakeLlm(failing, failing)

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    assert plan == ChatPlan.answer(Intent.CLARIFY, NOT_FINISHED)
    assert len(llm.calls) == 2


async def test_multi_summary_failure_falls_back(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = by_candidate(PAIR)
    llm = FakeLlm(respond, respond, failing)

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    assert plan.message == MULTI_FALLBACK.format(names="김하늘, 박서준")
    assert len(plan.items) == 2


async def test_multi_prompt_has_previous_notes(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="방금 만든 질문 왜 만든 거야?",
        mentions=["정유민", "김하늘"],
    )
    jung = str(sample_applicants["정유민"].info.application_id)
    turn = Turn(
        message="면접 질문 만들어줘",
        kind="ANSWER",
        intent="ANSWER",
        targets=[jung],
        answer="만들었어요.",
        items=[TurnItem(application_id=jung, label="확인할 점", text="배치 단축 근거")],
        focus={jung: "정산 배치 설계 판단 확인"},
        total=8,
        plan={},
    )
    empty = CandidateNotes(items=[])
    llm = FakeLlm(empty, empty, MultiSummary(message="이유예요."))

    await plan_answer(llm, ASK, context, resolve(context), default_toolkit(), [turn])

    assert "정산 배치 설계 판단 확인" in llm.calls[0].user
    assert "정산 배치 설계 판단 확인" not in llm.calls[1].user


async def test_six_targets_use_tool_loop(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="이 사람들 요약해줘",
        checked=["정유민", "김하늘", "박서준", "이도윤", "최지우", "한예린"],
    )
    llm = FakeLlm(answered(message="여섯 명을 요약했어요."))

    plan = await ask(llm, context)

    assert plan.message == "여섯 명을 요약했어요."
    assert llm.calls[0].output is RootAnswer


class SlowLlm:
    """정해 둔 호출만 늦게 답하는 LLM. FakeLlm은 바로 답하므로 시간 상한을 볼 때 감싸서 쓴다."""

    def __init__(self, fake: FakeLlm, slow: Callable[[str, type[BaseModel]], bool], seconds: float = 1) -> None:
        self.fake = fake
        self.slow = slow
        self.seconds = seconds

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
        if self.slow(user, output):
            await asyncio.sleep(self.seconds)
        return await self.fake.structured(output, agent=agent, system=system, user=user)

    def tool_agent[T: BaseModel](
        self,
        output: type[T],
        *,
        agent: str,
        system: str,
        tools: Sequence[BaseTool],
        context: type[Any] | None = None,
    ) -> ToolAgent[T]:
        return self.fake.tool_agent(output, agent=agent, system=system, tools=tools, context=context)


def with_summary(notes: Mapping[str, CandidateNotes | Exception], summary: str) -> Callable[[LlmCall], FakeReply]:
    """정리 호출은 지원자로, 종합 호출은 종합 답으로 답한다. 늦은 호출이 있으면 응답 순서가 바뀌므로 내용으로 고른다."""
    notes_reply = by_candidate(notes)

    def respond(call: LlmCall) -> FakeReply:
        return MultiSummary(message=summary) if call.output is MultiSummary else notes_reply(call)

    return respond


async def test_multi_slow_candidate_marked_check(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(answer, "NOTES_SECONDS", 0.05)
    respond = with_summary(PAIR, "김하늘만 확인했어요.")
    llm = SlowLlm(FakeLlm(respond, respond, respond), lambda user, output: "정리할 지원자: C3 박서준" in user)

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    park = sample_applicants["박서준"].info.application_id
    assert plan.message == "김하늘만 확인했어요."
    assert [(item.status, item.text) for item in plan.items] == [("OK", "Oracle 원장 설계"), ("CHECK", NOT_CHECKED)]
    assert plan.items[1].application_id == park


async def test_multi_all_slow_clarifies(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(answer, "NOTES_SECONDS", 0.05)
    respond = with_summary(PAIR, "비교했어요.")
    llm = SlowLlm(FakeLlm(respond, respond), lambda user, output: output is CandidateNotes)

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    assert plan == ChatPlan.answer(Intent.CLARIFY, NOT_FINISHED)


async def test_multi_summary_timeout_falls_back(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(answer, "SUMMARY_SECONDS", 0.05)
    respond = with_summary(PAIR, "비교했어요.")
    llm = SlowLlm(FakeLlm(respond, respond, respond), lambda user, output: output is MultiSummary)

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    assert plan.message == MULTI_FALLBACK.format(names="김하늘, 박서준")
    assert [item.status for item in plan.items] == ["OK", "OK"]


async def test_summary_naming_other_applicant_falls_back(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = by_candidate(PAIR)
    summary = MultiSummary(message="정유민은 정산 배치 경험이 있고, 박서준은 쿼리 튜닝 경험이 있어요.")
    llm = FakeLlm(respond, respond, summary)

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    assert plan.message == MULTI_FALLBACK.format(names="김하늘, 박서준")


async def test_cancelled_request_cancels_notes(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = with_summary(PAIR, "비교했어요.")
    fake = FakeLlm(respond, respond, respond)
    llm = SlowLlm(fake, lambda user, output: output is CandidateNotes, seconds=0.2)
    request = asyncio.create_task(ask(llm, pair_context(sample_applicants, sample_company, sample_posting)))

    await asyncio.sleep(0.05)
    request.cancel()
    await asyncio.sleep(0.4)

    assert request.cancelled()
    assert fake.calls == []
