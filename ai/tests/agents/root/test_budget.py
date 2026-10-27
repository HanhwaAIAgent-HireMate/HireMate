import pytest
from root_context import make_context, root_reply

from hiremate_ai.agents.root.commands import ClarifyCommand, RootReply
from hiremate_ai.agents.root.find import RecheckItem, RecheckResult
from hiremate_ai.agents.root.graph import run_plan
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent
from hiremate_ai.llm.fake import FakeLlm, ToolCall


async def test_search_rechecks_share_the_roots_model_call_budget(
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_agent_max_calls", 3)
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융이나 결제 경험자를 찾아줘")
    rechecked = RecheckResult(results=[RecheckItem(candidate_no=1, met=True, sentence_nos=[1])])
    llm = FakeLlm(
        [
            ToolCall("search_candidates", {"query": {"concepts": ["결제"]}}),
            ToolCall("search_candidates", {"query": {"concepts": ["금융"]}}),
        ],
        rechecked,
        root_reply(RootReply(message="검색 조건을 좁혀 주세요.", command=ClarifyCommand())),
    )

    plan = await run_plan(llm, context)

    assert len(llm.calls) == 3
    assert [call.output.__name__ for call in llm.calls] == ["RootReply", "RecheckResult", "RootReply"]
    assert plan.targets == []
    assert "조건 검색" in plan.message and "완료하지 못" in plan.message
