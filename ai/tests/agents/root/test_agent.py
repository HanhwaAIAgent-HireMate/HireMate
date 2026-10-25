import pytest
from root_context import make_context

from hiremate_ai.agents.root.find import RecheckItem, RecheckResult
from hiremate_ai.agents.root.graph import run_plan
from hiremate_ai.agents.root.types import EditAction, Intent
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.fake import FakeLlm, ToolCall

type Applicants = dict[str, ApplicantDetail]


async def test_root_chooses_a_read_tool_and_returns_a_command_without_classification(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="현재 인원 알려줘")
    llm = FakeLlm(
        ToolCall("get_stage_summary"),
        ToolCall("RootReply", {"message": "현재 지원자는 8명이에요.", "command": {"kind": "answer"}}),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.message == "현재 지원자는 8명이에요."
    assert len(llm.calls) == 2
    assert all(call.output.__name__ == "RootReply" for call in llm.calls)
    assert "미결정 8명" in llm.calls[-1].user


async def test_root_observes_search_results_then_reads_more_before_answering(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="결제 경험자를 찾아서 경험을 설명해줘"
    )
    sentence = "MySQL 정산 테이블을 파티셔닝해 월말 정산 배치 시간을 40% 줄였습니다."
    llm = FakeLlm(
        ToolCall("search_candidates", {"query": {"concepts": ["결제"]}, "pool": ["C1"]}),
        RecheckResult(results=[RecheckItem(candidate_no=1, met=True, sentence_nos=[1])]),
        ToolCall("get_candidate_briefs", {"candidates": ["C1"]}),
        ToolCall(
            "RootReply",
            {
                "message": "정유민 님의 정산 배치 개선 경험을 확인했어요.",
                "command": {"kind": "answer", "candidates": ["C1"]},
                "items": [
                    {
                        "candidate": "C1",
                        "label": "경험",
                        "text": "정산 배치 시간 40% 단축",
                        "status": "OK",
                        "evidence": [{"sentence": sentence, "source": "이력서"}],
                    }
                ],
            },
        ),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.ANSWER
    assert plan.targets == []
    assert plan.sources == ["이력서"]
    assert '"result": "S1"' in llm.calls[2].user
    assert sentence in llm.calls[-1].user
    assert [call.output.__name__ for call in llm.calls] == ["RootReply", "RecheckResult", "RootReply", "RootReply"]


async def test_empty_stage_answers_must_observe_the_stage_summary(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="인원 알려줘")
    answer = ToolCall("RootReply", {"message": "현재 지원자는 100명이에요.", "command": {"kind": "answer"}})

    plan = await run_plan(FakeLlm(answer, answer), context)

    assert plan.intent is Intent.CLARIFY
    assert "100명" not in plan.message


async def test_unsubstantiated_stage_items_cannot_bypass_summary_validation(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="인원 알려줘")
    answer = ToolCall(
        "RootReply",
        {
            "message": "지원자는 100명이에요.",
            "command": {"kind": "answer"},
            "items": [{"label": "인원", "text": "지원자 100명", "status": "OK"}],
        },
    )

    plan = await run_plan(FakeLlm(answer, answer), context)

    assert plan.intent is Intent.CLARIFY
    assert "100명" not in plan.message


async def test_question_confirmation_does_not_repeat_unverified_model_prose(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="면접 질문 만들어줘", stage_type=StageType.INTERVIEW
    )
    llm = FakeLlm(
        ToolCall(
            "RootReply",
            {
                "message": "정유민은 증권사에서 20년 일했으니 질문을 만들어요.",
                "command": {"kind": "questions", "candidates": ["C1"]},
            },
        )
    )

    plan = await run_plan(llm, context)

    assert plan.question_targets == [context.candidates[0].application_id]
    assert "증권사" not in plan.message
    assert "20년" not in plan.message


async def test_root_returns_the_models_explicit_edit_targets(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="앞에서 이야기한 분을 빼줘",
        checked=["김하늘"],
    )
    llm = FakeLlm(
        ToolCall(
            "RootReply",
            {"message": "선택에서 뺐어요.", "command": {"kind": "edit", "action": "REMOVE", "candidates": ["C1"]}},
        )
    )

    plan = await run_plan(llm, context)

    assert plan.edit is EditAction.REMOVE
    assert plan.targets == [sample_applicants["정유민"].info.application_id]


@pytest.mark.parametrize("query", [{"use_talents": True}, {"posting_criteria": "preferred"}])
async def test_discriminatory_company_or_posting_criteria_are_blocked_before_search(
    query: dict[str, object],
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    from hiremate_ai.agents.guardrails import BLOCKED_REPLY

    company = sample_company.model_copy(
        update={
            "talents": [
                sample_company.talents[0].model_copy(update={"title": "여성 우대", "description": "여성 지원자 선호"})
            ]
        }
    )
    posting = sample_posting.model_copy(update={"preferred": ["여성 지원자 우대"]})
    context = make_context(sample_applicants, company, posting, message="그 기준에 맞는 분을 찾아줘")
    llm = FakeLlm(
        ToolCall("search_candidates", {"query": query}),
        ToolCall("RootReply", {"message": "찾았어요.", "command": {"kind": "find", "result": "S1"}}),
    )

    plan = await run_plan(llm, context)

    assert plan.intent is Intent.BLOCKED
    assert plan.message == BLOCKED_REPLY
    assert all(call.output.__name__ == "RootReply" for call in llm.calls)
