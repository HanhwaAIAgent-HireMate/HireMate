import time
from collections.abc import Mapping
from uuid import UUID, uuid4

import pytest
from langchain.tools import ToolRuntime, tool
from root_context import make_context

from hiremate_ai.agents.root import answer
from hiremate_ai.agents.root.answer import (
    NOT_FINISHED,
    AnswerEvidence,
    AnswerItem,
    RootAnswer,
    plan_answer,
)
from hiremate_ai.agents.root.route import RootRoute
from hiremate_ai.agents.root.targets import resolve
from hiremate_ai.agents.root.toolkit import ANSWER_TOOLS, RootToolContext, RootToolkit, default_toolkit, keyword_search
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
from hiremate_ai.llm.fake import FakeLlm, LlmCall, ToolCall

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


async def ask(llm: FakeLlm, context: ChatContext, toolkit: RootToolkit | None = None) -> ChatPlan:
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
