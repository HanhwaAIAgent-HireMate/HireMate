import asyncio
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain_core.tools import BaseTool
from pydantic import BaseModel
from root_context import Recorder, make_context, save_sample_profiles, sessions_of
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.root.answer import (
    BULK,
    COMPARE_STATUS,
    FOCUS_FALLBACK,
    FOCUS_STATUS,
    FOCUS_WITH_REQUEST,
    FOCUSED,
    LATER_GAP_PROBLEM,
    MULTI_FALLBACK,
    MULTI_STATUS,
    NO_QUESTION_TARGET,
    NOT_CHECKED,
    NOT_FINISHED,
    ONE_STATUS,
    STAGE_STATUS,
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
    AgentEvidence,
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
from hiremate_ai.db.profile import ItemAgent, ItemCategory
from hiremate_ai.db.profile_store import NewItem, save_profile
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
    """대상 없는 질문. 도구 루프로 답하므로 근거 확인(verify_items)을 항목 그대로 본다.

    대상이 있으면 지원자별 정리로 간다 (one_context).
    """
    return make_context(
        applicants,
        company,
        posting,
        message="강점이 뭐야?",
        stage_type=stage_type,
        interviews=interviews,
    )


def one_context(applicants: Applicants, company: CompanyProfile, posting: PostingContent) -> ChatContext:
    return make_context(applicants, company, posting, message="@정유민 강점이 뭐야?", mentions=["정유민"])


def answered(*items: AnswerItem, message: str = "정유민 님의 강점이에요.") -> RootAnswer:
    return RootAnswer(
        message=message,
        items=list(items)
        or [AnswerItem(candidate="C1", label="확인할 점", text="본인 역할은 추가 확인이 필요해요.", status="CHECK")],
    )


def unrepaired(reply: RootAnswer) -> FakeLlm:
    """검증 실패를 알려도 같은 답을 내는 모델. 안전한 결과로 마무리하는 동작을 검사한다."""
    return FakeLlm(reply, reply)


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
    assert "대상 지원자: 지정 없음" in llm.calls[0].user
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
    assert plan.agents == ["Application Agent"]


async def test_unverified_evidence_turns_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    made_up = AnswerEvidence(sentence="10년 동안 증권사 시스템을 설계했습니다.", source="이력서")
    llm = unrepaired(
        answered(AnswerItem(candidate="C1", label="강점", text="증권 경력", status="OK", evidence=[made_up]))
    )

    plan = await ask(llm, context)

    assert plan.items[0].status == "CHECK"
    assert plan.sources == []


async def test_ok_without_evidence_about_a_candidate_turns_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = unrepaired(
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
    llm = unrepaired(
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
    llm = unrepaired(
        answered(
            AnswerItem(candidate="C1", label="답변", text="파티셔닝", status="OK", evidence=[kept]),
            AnswerItem(candidate="C1", label="답변", text="샤딩", status="OK", evidence=[dropped]),
        )
    )

    plan = await ask(llm, context)

    assert [item.status for item in plan.items] == ["OK", "CHECK"]
    assert plan.sources == ["면접 기록"]


PARTITION_ANSWER = "파티셔닝 기준을 월 단위로 정했습니다."
TEST_ANSWER = "테스트는 다른 팀원이 주로 맡아서 자세히는 모릅니다."
INCIDENT_ANSWER = "장애가 나면 팀과 함께 대응했습니다."


def interview_answers(application_id: UUID, *answers: str) -> InterviewView:
    questions = [
        InterviewQuestion(question_id=uuid4(), text="경험을 말해 주세요.", source=QuestionSource.AI, answer=answer)
        for answer in answers
    ]
    return InterviewView(application_id=application_id, schedule=None, questions=questions, previous=[])


def interview_item(sentence: str, verification: str) -> AgentEvidence:
    return AgentEvidence(sentence=sentence, source="1차 면접 답변", agent="interview", verification=verification)


async def test_evidence_the_agent_left_unconfirmed_or_conflicting_turns_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    jung = sample_applicants["정유민"].info.application_id
    view = interview_answers(jung, PARTITION_ANSWER, TEST_ANSWER, INCIDENT_ANSWER)
    context = context_for(
        sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW, interviews={jung: view}
    )
    toolkit = with_evidence(
        {
            jung: [
                interview_item(PARTITION_ANSWER, "CONFIRMED"),
                interview_item(TEST_ANSWER, "CONFLICT"),
                interview_item(INCIDENT_ANSWER, "UNCONFIRMED"),
            ]
        }
    )
    llm = unrepaired(
        answered(
            *(
                AnswerItem(
                    candidate="C1",
                    label="답변",
                    text=text,
                    status="OK",
                    evidence=[AnswerEvidence(sentence=sentence, source="면접 기록")],
                )
                for text, sentence in [
                    ("파티셔닝", PARTITION_ANSWER),
                    ("테스트", TEST_ANSWER),
                    ("장애 대응", INCIDENT_ANSWER),
                ]
            )
        )
    )

    plan = await ask(llm, context, toolkit)

    assert [item.status for item in plan.items] == ["OK", "CHECK", "CHECK"]
    assert (plan.sources, plan.agents) == (["면접 기록"], ["Interview Agent"])


async def test_doubt_from_another_source_keeps_document_evidence(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    jung = sample_applicants["정유민"].info.application_id
    context = context_for(sample_applicants, sample_company, sample_posting)
    toolkit = with_evidence({jung: [interview_item(BATCH, "CONFLICT")]})
    evidence = AnswerEvidence(sentence=BATCH, source="이력서")
    llm = FakeLlm(answered(AnswerItem(candidate="C1", label="강점", text="배치", status="OK", evidence=[evidence])))

    plan = await ask(llm, context, toolkit)

    assert plan.items[0].status == "OK"


async def test_slow_tool_loop_still_answers(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:

    def slow(call: LlmCall) -> ToolCall:
        time.sleep(0.05)
        return ToolCall("get_stage_summary")

    context = context_for(sample_applicants, sample_company, sample_posting)

    plan = await ask(FakeLlm(slow, answered()), context)

    assert (plan.intent, plan.message) == (Intent.ANSWER, "정유민 님의 강점이에요.")


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


ASSESSMENT_NOTE = "장애 원인을 로그로 좁혀 가는 과정을 팀원에게 차근차근 설명했어요."


def assessment_note(application_id: UUID) -> dict[UUID, list[AgentEvidence]]:
    return {application_id: [AgentEvidence(sentence=ASSESSMENT_NOTE, source="평가 메모", agent="assessment")]}


def with_evidence(recorded: Mapping[UUID, list[AgentEvidence]]) -> RootToolkit:
    """분석 Agent가 프로필에 남긴 근거를 정해 두는 묶음. 받은 지원자 것만 돌려준다."""

    async def evidence(scope: RootToolContext, application_ids: Sequence[UUID]) -> dict[UUID, list[AgentEvidence]]:
        return {
            application_id: recorded[application_id] for application_id in application_ids if application_id in recorded
        }

    return RootToolkit(search=keyword_search, answer_tools=ANSWER_TOOLS, evidence=evidence)


async def test_assessment_evidence_checked_against_profile(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    toolkit = with_evidence(assessment_note(sample_applicants["정유민"].info.application_id))
    llm = unrepaired(
        answered(
            AnswerItem(
                candidate="C1",
                label="소통",
                text="원인 설명",
                status="OK",
                evidence=[AnswerEvidence(sentence=ASSESSMENT_NOTE, source="평가 메모")],
            ),
            AnswerItem(
                candidate="C1",
                label="과제",
                text="테스트 코드",
                status="OK",
                evidence=[AnswerEvidence(sentence="모든 기능에 테스트 코드를 작성했어요.", source="과제 제출물")],
            ),
        )
    )

    plan = await ask(llm, context, toolkit)

    assert [item.status for item in plan.items] == ["OK", "CHECK"]
    assert plan.sources == ["평가 메모"]
    assert plan.agents == ["Assessment Agent"]


async def test_assessment_evidence_without_profile_turns_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    evidence = AnswerEvidence(sentence=ASSESSMENT_NOTE, source="평가 메모")
    llm = unrepaired(answered(AnswerItem(candidate="C1", label="소통", text="설명", status="OK", evidence=[evidence])))

    plan = await ask(llm, context)

    assert plan.items[0].status == "CHECK"
    assert (plan.sources, plan.agents) == ([], [])


async def test_score_source_is_kept_without_agent(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    evidence = AnswerEvidence(sentence="평가 점수: 82점", source="평가 결과")
    llm = FakeLlm(answered(AnswerItem(candidate="C1", label="평가", text="82점", status="OK", evidence=[evidence])))

    plan = await ask(llm, context)

    assert plan.items[0].status == "OK"
    assert (plan.sources, plan.agents) == (["평가 결과"], [])


async def test_answer_keeps_assessment_evidence_saved_in_profile(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    jung = sample_applicants["정유민"].info
    await save_profile(
        db_session,
        company_id=sample_company.company_id,
        recruitment_id=jung.recruitment_id,
        application_id=jung.application_id,
        agent=ItemAgent.ASSESSMENT,
        items=[
            NewItem(
                category=ItemCategory.STRENGTH,
                content="원인 분석을 설명한다",
                evidence=ASSESSMENT_NOTE,
                source="평가 메모",
            )
        ],
        stage_id=uuid4(),
    )
    context = context_for(sample_applicants, sample_company, sample_posting)
    evidence = AnswerEvidence(sentence=ASSESSMENT_NOTE, source="평가 메모")
    item = AnswerItem(candidate="C1", label="소통", text="원인 설명", status="OK", evidence=[evidence])
    llm = FakeLlm(ToolCall("get_candidate_profile", {"candidate": "C1"}), answered(item))

    plan = await ask(llm, context, profile_toolkit(sessions_of(db_session)))

    assert ASSESSMENT_NOTE in llm.calls[1].user
    assert [(item.label, item.status) for item in plan.items] == [("소통", "OK")]
    assert (plan.sources, plan.agents) == (["평가 메모"], ["Assessment Agent"])


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
    assert plan.question_focus == {jung: FOCUS_WITH_REQUEST.format(focus=FOCUS, request="면접 질문 만들어줘")}
    assert plan.message == FOCUSED.format(count=1)
    assert (plan.items[0].application_id, plan.items[0].status) == (jung, "OK")
    assert plan.sources == ["이력서"]
    assert plan.agents == ["Interview Agent"]
    assert plan.targets == []


async def test_focus_names_assessment_agent_of_reason(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    reason = AnswerItem(
        label="확인할 점",
        text="원인 분석 방식",
        status="OK",
        evidence=[AnswerEvidence(sentence=ASSESSMENT_NOTE, source="평가 메모")],
    )
    llm = FakeLlm(
        ToolCall("get_candidate_profile", {"candidate": "C1"}),
        focused(QuestionFocusItem(candidate="C1", focus=FOCUS, reasons=[reason])),
    )
    toolkit = with_evidence(assessment_note(sample_applicants["정유민"].info.application_id))

    plan = await plan_questions(llm, QUESTIONS, context, resolve(context), toolkit)

    assert plan.items[0].status == "OK"
    assert plan.agents == ["Assessment Agent", "Interview Agent"]


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


async def test_focus_keeps_hr_request_words(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # Interview Agent는 "확인 안 된 점 위주로" 같은 담당자 말로 질문 범위를 좁힌다. 실제 모델은 그 말을 바꿔 쓴다
    message = "1차 면접에서 확인 안 된 점 위주로 질문 만들어줘"
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message=message,
        mentions=["정유민"],
        stage_type=StageType.INTERVIEW,
        previous_types=(StageType.DOCUMENT,),
    )
    llm = FakeLlm(focused(QuestionFocusItem(candidate="C1", focus="검증되지 않은 정산 경험을 확인")))

    plan = await make_questions(llm, QUESTIONS, context)

    jung = sample_applicants["정유민"].info.application_id
    assert plan.question_focus == {jung: f"검증되지 않은 정산 경험을 확인 (담당자 요청: {message})"}


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
    focus = FOCUS_WITH_REQUEST.format(focus="은행 계정계 장애 대응 경험을 구체적으로", request="면접 질문 만들어줘")
    assert plan.question_focus == {kim: focus}


async def test_focus_failure_keeps_explicit_question_request_without_invented_reasons(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    def broken(call: LlmCall) -> RootQuestionFocus:
        raise LlmOutputError("RootQuestionFocus 형식의 답을 받지 못했다")

    context = interview_context(sample_applicants, sample_company, sample_posting, mentions=["정유민"])

    plan = await make_questions(FakeLlm(broken), QUESTIONS, context)

    assert plan.intent == Intent.ANSWER
    assert plan.question_targets == [sample_applicants["정유민"].info.application_id]
    assert plan.question_focus == {}
    assert plan.items == []
    assert plan.sources == []
    assert plan.agents == ["Interview Agent"]
    assert plan.message == FOCUS_FALLBACK


async def test_single_target_answers_through_notes(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 한 명도 지원자별 정리로 답한다. 도구 루프로 답하면 실제 모델이 근거 항목 없이 답 글만 쓰기 일쑤다
    context = one_context(sample_applicants, sample_company, sample_posting)
    evidence = AnswerEvidence(sentence=BATCH, source="이력서")
    llm = FakeLlm(
        CandidateNotes(items=[AnswerItem(label="강점", text="정산 배치 개선", status="OK", evidence=[evidence])]),
        MultiSummary(message="정유민은 정산 배치를 줄였어요."),
    )

    plan = await ask(llm, context)

    assert (plan.intent, plan.message) == (Intent.ANSWER, "정유민은 정산 배치를 줄였어요.")
    assert plan.items[0].application_id == sample_applicants["정유민"].info.application_id
    assert (plan.items[0].status, plan.sources) == ("OK", ["이력서"])
    assert "정리할 지원자: C1 정유민" in llm.calls[0].user
    assert "회사:" in llm.calls[0].user


async def test_ref_in_text_assigns_candidate_and_reads_as_name(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="지원자 경력 요약해줘")
    item = AnswerItem(
        label="경력",
        text="C2 김하늘은 은행 경력이 있다",
        status="OK",
        evidence=[AnswerEvidence(sentence=KIM_ORACLE, source="이력서")],
    )
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
    llm = unrepaired(answered(AnswerItem(label="공통점", text="둘 다 정산 경험", status="OK", evidence=[evidence])))

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

    llm = unrepaired(
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


async def test_company_evidence_as_tool_shows_it(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 실제 모델은 회사 도구가 보여 준 "제목: 설명" 줄을 그대로 옮기고, 출처를 "인재상"으로도 적는다
    context = context_for(sample_applicants, sample_company, sample_posting)

    def item(sentence: str, source: str) -> AnswerItem:
        return AnswerItem(
            candidate="C1",
            label="인재상",
            text="근거",
            status="OK",
            evidence=[AnswerEvidence(sentence=sentence, source=source)],
        )

    llm = FakeLlm(
        answered(
            item("고객 신뢰를 최우선으로: 고객의 돈과 정보를 다룬다는 책임감", "회사 소개"),
            item("함께 성장: 지식을 나누고 동료의 성장을 돕는 태도", "인재상"),
            item("작게 나눠 빠르게 배포하고, 장애는 숨기지 않고 함께 회고합니다.", "조직 문화"),
        )
    )

    plan = await ask(llm, context)

    assert [entry.status for entry in plan.items] == ["OK", "OK", "OK"]
    assert plan.sources == ["회사 소개"]


async def test_sources_listed_once(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    evidence = [
        AnswerEvidence(sentence=BATCH, source="이력서"),
        AnswerEvidence(sentence="카드 결제 승인 · 정산 API를 Java와 Spring Boot로 개발했습니다.", source="이력서"),
    ]
    llm = FakeLlm(answered(AnswerItem(candidate="C1", label="경력", text="정산", status="OK", evidence=evidence)))

    plan = await ask(llm, context)

    assert plan.sources == ["이력서"]


def test_readable_cleans_model_leftovers(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    from hiremate_ai.agents.root.answer import readable

    context = make_context(sample_applicants, sample_company, sample_posting, message="확인")

    # 실제 모델 답에 "responseC1"처럼 영문 낱말에 붙은 번호와 생각 태그가 남았다
    assert readable("responseC1의 강점은 결제예요.", context) == "정유민의 강점은 결제예요."
    assert readable("<think>번호로 부른다</think>C2 김하늘은 은행 경력이에요.", context) == "김하늘은 은행 경력이에요."
    assert readable("</think>\n\n정리했어요.", context) == "정리했어요."
    # 대문자 약어(EC2)는 지원자 번호가 아니다
    assert readable("EC2 운영 경험이 있어요.", context) == "EC2 운영 경험이 있어요."


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


TALENT_QUESTION = "@정유민 우리 회사 인재상과 잘 맞는 것 같아?"


def talent_notes() -> CandidateNotes:
    evidence = [AnswerEvidence(sentence=RETRO, source="자기소개서")]
    item = AnswerItem(label="함께 성장", text="장애 회고를 문서로 남겨요.", status="OK", evidence=evidence)
    return CandidateNotes(items=[item])


async def test_talent_question_cites_company(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 실제 모델은 인재상과 견준 답에도 지원자 문장만 근거로 단다. 견준 기준인 회사 인재상은 코드가 출처로 둔다
    context = make_context(
        sample_applicants, sample_company, sample_posting, message=TALENT_QUESTION, mentions=["정유민"]
    )
    llm = FakeLlm(talent_notes(), MultiSummary(message="함께 성장 인재상과 맞아요."))

    plan = await ask(llm, context)

    assert plan.sources == ["자기소개서", "회사 소개"]


async def test_talent_question_without_talents_has_no_company_source(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    company = sample_company.model_copy(update={"talents": []})
    context = make_context(sample_applicants, company, sample_posting, message=TALENT_QUESTION, mentions=["정유민"])
    llm = FakeLlm(talent_notes(), MultiSummary(message="자기소개서에 회고 경험이 있어요."))

    plan = await ask(llm, context)

    assert plan.sources == ["자기소개서"]


async def test_stage_ranking_with_checked_stays_with_checked(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="경력이 가장 많은 사람은?",
        checked=["김하늘", "박서준"],
    )
    respond = by_candidate(PAIR)
    llm = FakeLlm(respond, respond, MultiSummary(message="김하늘이 더 길어요."))

    await ask(llm, context)

    assert [call.output for call in llm.calls] == [CandidateNotes, CandidateNotes, MultiSummary]


async def test_multi_unverified_evidence_turns_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = by_candidate({**PAIR, "C3 박서준": note("은행 경력", "은행에서 10년 일했습니다.")})
    llm = FakeLlm(respond, respond, MultiSummary(message="비교했어요."))

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    assert [item.status for item in plan.items] == ["OK", "CHECK"]


async def test_multi_names_assessment_agent_of_notes(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    kim = sample_applicants["김하늘"].info.application_id
    evidence = AnswerEvidence(sentence=ASSESSMENT_NOTE, source="평가 메모")
    notes = CandidateNotes(items=[AnswerItem(label="소통", text="원인 설명", status="OK", evidence=[evidence])])
    respond = by_candidate({**PAIR, "C2 김하늘": notes})
    llm = FakeLlm(respond, respond, MultiSummary(message="비교했어요."))

    plan = await ask(
        llm, pair_context(sample_applicants, sample_company, sample_posting), with_evidence(assessment_note(kim))
    )

    assert [item.status for item in plan.items] == ["OK", "OK"]
    assert plan.sources == ["평가 메모", "이력서"]
    assert plan.agents == ["Assessment Agent"]


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


async def test_multi_waits_for_slow_candidate(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = with_summary(PAIR, "두 사람을 비교했어요.")
    llm = SlowLlm(FakeLlm(respond, respond, respond), lambda user, output: "정리할 지원자: C3 박서준" in user, 0.2)

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    assert plan.message == "두 사람을 비교했어요."
    assert [(item.status, item.text) for item in plan.items] == [("OK", "Oracle 원장 설계"), ("OK", "PostgreSQL 튜닝")]


async def test_multi_all_slow_still_compares(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = with_summary(PAIR, "비교했어요.")
    llm = SlowLlm(FakeLlm(respond, respond, respond), lambda user, output: output is CandidateNotes, 0.2)

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    assert (plan.intent, plan.message) == (Intent.ANSWER, "비교했어요.")
    assert [item.status for item in plan.items] == ["OK", "OK"]


async def test_multi_slow_summary_still_used(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = with_summary(PAIR, "비교했어요.")
    llm = SlowLlm(FakeLlm(respond, respond, respond), lambda user, output: output is MultiSummary, 0.2)

    plan = await ask(llm, pair_context(sample_applicants, sample_company, sample_posting))

    assert plan.message == "비교했어요."


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


async def test_single_answer_reports_name(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 한 명이면 "1명을 비교하고 있어요"는 내지 않는다
    context = one_context(sample_applicants, sample_company, sample_posting)
    progress = Recorder()
    llm = FakeLlm(
        CandidateNotes(items=[AnswerItem(label="확인할 점", text="본인 역할을 확인해야 해요.", status="CHECK")]),
        MultiSummary(message="정리했어요."),
    )

    await plan_answer(llm, ASK, context, resolve(context), default_toolkit(), progress=progress)

    assert progress.statuses == [ONE_STATUS.format(name="정유민")]
    assert len(progress.items) == 1
    assert progress.items[0].status == "CHECK"


async def test_stage_answer_reports_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="미결정이 몇 명 남았어?")
    progress = Recorder()

    await plan_answer(FakeLlm(answered()), ASK, context, resolve(context), default_toolkit(), progress=progress)

    assert progress.statuses == [STAGE_STATUS]


async def test_multi_streams_items_as_candidates_finish(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = pair_context(sample_applicants, sample_company, sample_posting)
    respond = by_candidate(PAIR)
    llm = FakeLlm(respond, respond, MultiSummary(message="비교했어요."))
    progress = Recorder()

    plan = await plan_answer(llm, ASK, context, resolve(context), default_toolkit(), progress=progress)

    assert progress.statuses == [MULTI_STATUS.format(count=2), COMPARE_STATUS.format(count=2)]
    # 스트림 항목은 최종 답과 같은 검증을 거친 것이다. 순서는 정리가 끝난 순서다
    assert sorted(progress.items, key=str) == sorted(plan.items, key=str)


async def test_multi_streams_items_in_finish_order(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = with_summary(PAIR, "비교했어요.")
    llm = SlowLlm(FakeLlm(respond, respond, respond), lambda user, output: "정리할 지원자: C3 박서준" in user, 0.2)
    context = pair_context(sample_applicants, sample_company, sample_posting)
    progress = Recorder()

    plan = await plan_answer(llm, ASK, context, resolve(context), default_toolkit(), progress=progress)

    # 늦은 지원자도 기다려 보낸다. 먼저 끝난 지원자가 먼저 간다
    assert progress.items == plan.items


async def test_multi_streams_verified_status(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    respond = by_candidate({**PAIR, "C3 박서준": note("은행 경력", "은행에서 10년 일했습니다.")})
    llm = FakeLlm(respond, respond, MultiSummary(message="비교했어요."))
    context = pair_context(sample_applicants, sample_company, sample_posting)
    progress = Recorder()

    await plan_answer(llm, ASK, context, resolve(context), default_toolkit(), progress=progress)

    # 원문에 없는 근거는 모델이 OK라고 했어도 스트림에서부터 확인 필요다
    park = sample_applicants["박서준"].info.application_id
    assert [item.status for item in progress.items if item.application_id == park] == ["CHECK"]


async def test_focus_reports_status(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    progress = Recorder()

    await plan_questions(FakeLlm(focused()), QUESTIONS, context, resolve(context), default_toolkit(), progress=progress)

    assert progress.statuses == [FOCUS_STATUS]


LATER_GAP = "면접 기록이 없어 실제 역량과 태도를 확인할 수 없어요."


class ToolsSpy:
    """도구 루프에 준 도구 이름을 남기는 LLM."""

    def __init__(self, fake: FakeLlm) -> None:
        self.fake = fake
        self.tools: list[str] = []

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
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
        self.tools = [tool.name for tool in tools]
        return self.fake.tool_agent(output, agent=agent, system=system, tools=tools, context=context)


def first_stage(applicants: Applicants, company: CompanyProfile, posting: PostingContent, **kwargs: Any) -> ChatContext:
    """면접 전형이 뒤에 있는 첫 서류 전형."""
    return make_context(applicants, company, posting, later_types=(StageType.INTERVIEW,), **kwargs)


async def test_notes_drop_gap_of_later_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = first_stage(
        sample_applicants, sample_company, sample_posting, message="@정유민 강점이 뭐야?", mentions=["정유민"]
    )
    strength = AnswerItem(
        label="강점", text="정산 배치 개선", status="OK", evidence=[AnswerEvidence(sentence=BATCH, source="이력서")]
    )
    gap = AnswerItem(label="확인할 점", text=LATER_GAP, status="CHECK")
    llm = FakeLlm(
        CandidateNotes(items=[strength, gap]),
        MultiSummary(message=f"정유민은 정산 배치를 줄였어요. {LATER_GAP}"),
    )

    plan = await ask(llm, context)

    assert [(item.label, item.status) for item in plan.items] == [("강점", "OK")]
    assert plan.message == "정유민은 정산 배치를 줄였어요."
    notes_prompt = llm.calls[0].user
    assert "전형 구성: 1. 서류 전형 (서류 · 진행 중, 현재) → 2. 1차 면접 (면접 · 시작 전)" in notes_prompt
    assert '<data kind="interview"' not in notes_prompt
    assert LATER_GAP not in llm.calls[1].user


async def test_tool_loop_drops_gap_of_later_stage_without_interview_tool(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = first_stage(sample_applicants, sample_company, sample_posting, message="강점이 뭐야?")
    strength = AnswerItem(
        candidate="C1",
        label="강점",
        text="정산 배치 시간을 줄였다",
        status="OK",
        evidence=[AnswerEvidence(sentence=BATCH, source="이력서")],
    )
    gap = AnswerItem(candidate="C1", label="확인할 점", text=LATER_GAP, status="CHECK")
    llm = ToolsSpy(FakeLlm(answered(strength, gap, message=f"정유민 님의 강점이에요. {LATER_GAP}")))

    plan = await ask(llm, context)

    assert [(item.label, item.status) for item in plan.items] == [("강점", "OK")]
    assert plan.message == "정유민 님의 강점이에요."
    assert "get_interview_records" not in llm.tools
    assert "전형 구성: 1. 서류 전형" in llm.fake.calls[0].user


async def test_tool_loop_asks_again_when_message_only_blames_later_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = first_stage(sample_applicants, sample_company, sample_posting, message="강점이 뭐야?")
    strength = AnswerItem(
        candidate="C1",
        label="강점",
        text="정산 배치 시간을 줄였다",
        status="OK",
        evidence=[AnswerEvidence(sentence=BATCH, source="이력서")],
    )
    llm = FakeLlm(answered(strength, message=LATER_GAP), answered(strength))

    plan = await ask(llm, context)

    assert plan.message == "정유민 님의 강점이에요."
    assert LATER_GAP_PROBLEM in llm.calls[1].user


async def test_interview_stage_keeps_interview_tool_and_its_gaps(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 면접 전형에서 면접 기록이 없다는 말은 실제 상태라 그대로 둔다
    context = context_for(sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW)
    gap = AnswerItem(candidate="C1", label="확인할 점", text=LATER_GAP, status="CHECK")
    llm = ToolsSpy(FakeLlm(answered(gap)))

    plan = await ask(llm, context)

    assert "get_interview_records" in llm.tools
    assert [item.text for item in plan.items] == [LATER_GAP]
