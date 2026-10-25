import pytest
from root_context import make_context

from hiremate_ai.agents.root.agent import run_agent
from hiremate_ai.agents.root.commands import RootReply, compile_reply
from hiremate_ai.agents.root.conversation import ConversationReview
from hiremate_ai.agents.root.graph import run_plan
from hiremate_ai.agents.root.toolkit import default_toolkit
from hiremate_ai.agents.root.turns import turn_of
from hiremate_ai.agents.root.types import ChatPlan, Intent
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent
from hiremate_ai.llm.fake import FakeLlm, ToolCall
from hiremate_ai.llm.prompt import UNTRUSTED_RULE

type Applicants = dict[str, ApplicantDetail]


def conversation(message: str) -> ToolCall:
    return ToolCall("RootReply", {"message": message, "command": {"kind": "conversation"}})


@pytest.mark.parametrize(
    "question,response",
    [
        ("안녕", "안녕하세요. 무엇을 도와드릴까요?"),
        ("고마워", "도움이 되었다니 다행이에요."),
        ("어떤 일을 도와줄 수 있어?", "지원자 탐색과 자료 분석, 면접 질문 준비를 도와드려요."),
        ("선택과 합격은 어떻게 달라?", "선택은 검토할 지원자를 모으는 것이고, 합격 결정은 담당자가 화면에서 내려요."),
        ("Hello", "Hello! How can I help with your hiring work?"),
    ],
)
async def test_general_conversation_answers_without_business_reads(
    question: str,
    response: str,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message=question)
    llm = FakeLlm(conversation(response), ConversationReview(allowed=True))

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.message == response
    assert plan.targets == plan.question_targets == plan.items == plan.sources == []
    assert plan.edit is None
    assert [call.output.__name__ for call in llm.calls] == ["RootReply", "ConversationReview"]


async def test_previous_general_explanation_can_be_rephrased_without_fetching_current_data(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="방금 설명을 더 쉽게 말해줘")
    prior = turn_of(context, None, ChatPlan.answer(Intent.ANSWER, "선택은 검토할 지원자를 모으는 것이에요."), "ANSWER")
    llm = FakeLlm(conversation("선택은 나중에 살펴볼 사람을 담아두는 목록이에요."), ConversationReview(allowed=True))

    result = await run_agent(llm, context, default_toolkit(), turns=[prior])

    assert result.plan.intent is Intent.ANSWER
    assert result.plan.message == "선택은 나중에 살펴볼 사람을 담아두는 목록이에요."
    assert "선택은 검토할 지원자를 모으는 것이에요." in llm.calls[-1].user
    assert len(llm.calls) == 2


async def test_conversation_review_does_not_receive_candidate_documents_or_screen_data(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="안녕")
    llm = FakeLlm(conversation("안녕하세요."), ConversationReview(allowed=True))

    await run_plan(llm, context)

    check = llm.calls[-1]
    assert UNTRUSTED_RULE in check.system
    assert "안녕" in check.user
    assert "screen" not in check.user
    assert sample_applicants["정유민"].documents[0].text not in check.user
    assert str(context.company.company_id) not in check.user


@pytest.mark.parametrize(
    "text", ["현재 지원자는 백 명이에요.", "모두 합격 상태예요.", "미결정자가 대부분이에요.", "선택을 바꿨어요."]
)
async def test_business_claims_disguised_as_conversation_are_rejected_without_effects(
    text: str, sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="지금 상황을 알려줘")
    llm = FakeLlm(conversation(text), ConversationReview(allowed=False), conversation(text))

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert plan.targets == plan.question_targets == plan.items == []
    assert text not in plan.message
    assert [call.output.__name__ for call in llm.calls] == ["RootReply", "ConversationReview", "RootReply"]


async def test_rejected_conversation_is_repaired_using_the_same_react_loop(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="현재 인원 알려줘")
    llm = FakeLlm(
        conversation("현재 지원자는 백 명이에요."),
        ConversationReview(allowed=False),
        ToolCall("get_stage_summary"),
        ToolCall("RootReply", {"message": "현재 지원자는 8명이에요.", "command": {"kind": "answer"}}),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.message == "현재 지원자는 8명이에요."
    assert len(llm.calls) == 4
    assert "미결정 8명" in llm.calls[-1].user


@pytest.mark.parametrize("message", ["C1은 결제 경험이 풍부해요.", "정유민은 결제 경험이 풍부해요."])
async def test_conversation_cannot_hide_candidate_facts_in_the_message(
    message: str, sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="이 사람 어때?")
    reply = RootReply.model_validate({"message": message, "command": {"kind": "conversation"}})

    with pytest.raises(ValueError, match="대상과 근거"):
        await compile_reply(reply, context, default_toolkit(), {})


async def test_conversation_cannot_smuggle_analysis_items(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="안녕")
    reply = RootReply.model_validate(
        {
            "message": "안녕하세요.",
            "command": {"kind": "conversation"},
            "items": [{"candidate": "C1", "label": "검토", "text": "자료 확인 필요", "status": "CHECK"}],
        }
    )

    with pytest.raises(ValueError, match="일반 대화"):
        await compile_reply(reply, context, default_toolkit(), {})


async def test_conversation_output_review_shares_the_request_budget(
    monkeypatch: pytest.MonkeyPatch,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    monkeypatch.setattr(settings, "llm_agent_max_calls", 1)
    context = make_context(sample_applicants, sample_company, sample_posting, message="안녕")
    llm = FakeLlm(conversation("안녕하세요."), ConversationReview(allowed=True))

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert len(llm.calls) == 1
    assert "처리 한도" in plan.message
    assert plan.targets == plan.question_targets == []
