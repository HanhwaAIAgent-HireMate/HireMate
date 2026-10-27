from typing import Never

import pytest
from root_context import make_context, root_reply

from hiremate_ai.agents.root.commands import ClarifyCommand, RootReply
from hiremate_ai.agents.root.graph import run_plan
from hiremate_ai.agents.root.types import Intent
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent
from hiremate_ai.llm.chat import LlmFailureReason, LlmOutputError
from hiremate_ai.llm.fake import FakeLlm, LlmCall, ToolCall


@pytest.mark.parametrize(
    ("reason", "expected_message"),
    [
        (
            LlmFailureReason.FORMAT,
            "답변을 올바른 형식으로 완성하지 못했어요. 잠시 후 다시 요청해 주세요.",
        ),
        (
            LlmFailureReason.VALIDATION,
            "답변의 근거와 실행 조건을 확인하지 못했어요. 질문을 다시 말씀해 주세요.",
        ),
        (
            LlmFailureReason.BUDGET,
            "한 번에 확인할 수 있는 처리 한도에 도달했어요. 요청을 나눠 다시 말씀해 주세요.",
        ),
    ],
    ids=["format", "validation", "budget"],
)
async def test_failure_reason_returns_matching_recovery_message_without_actions(
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    reason: LlmFailureReason,
    expected_message: str,
) -> None:
    internal_message = "RootReply internal schema: candidate C999 rejected at step 4"

    def broken(call: LlmCall) -> Never:
        raise LlmOutputError(internal_message, reason=reason)

    context = make_context(sample_applicants, sample_company, sample_posting, message="도와줘")

    plan = await run_plan(FakeLlm(broken), context)

    assert plan.intent is Intent.CLARIFY
    assert plan.message == expected_message
    assert plan.targets == []
    assert plan.items == []
    assert plan.question_targets == []
    assert plan.question_focus == {}
    assert plan.mode is None and plan.edit is None
    assert internal_message not in plan.model_dump_json()


async def test_nested_search_budget_failure_uses_reserved_answer_without_actions(
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_agent_max_calls", 2)
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융이나 결제 경험자를 찾아줘")
    llm = FakeLlm(
        [
            ToolCall("search_candidates", {"query": {"concepts": ["결제"]}}),
            ToolCall("search_candidates", {"query": {"concepts": ["금융"]}}),
        ],
        root_reply(RootReply(message="검색을 완료하지 못했어요.", command=ClarifyCommand())),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert plan.message == "이번 요청에서 조건 검색 검토를 완료하지 못했어요."
    assert plan.targets == []
    assert plan.items == []
    assert plan.question_targets == []
    assert plan.question_focus == {}
    assert plan.mode is None and plan.edit is None
    assert "LlmOutputError" not in plan.model_dump_json()
    assert "RecheckResult" not in plan.model_dump_json()
    assert [call.output.__name__ for call in llm.calls] == ["RootReply", "RootReply"]
