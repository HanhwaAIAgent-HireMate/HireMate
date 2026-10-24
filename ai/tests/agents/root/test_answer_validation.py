from collections.abc import Sequence

import pytest
from root_context import make_context

from hiremate_ai.agents.root.answer import (
    MULTI_FALLBACK,
    AnswerEvidence,
    AnswerItem,
    CandidateNotes,
    MultiSummary,
    RootAnswer,
    plan_answer,
)
from hiremate_ai.agents.root.route import RootRoute
from hiremate_ai.agents.root.targets import Targets, resolve
from hiremate_ai.agents.root.toolkit import default_toolkit
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Intent
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent
from hiremate_ai.llm.fake import FakeLlm, ToolCall

type Applicants = dict[str, ApplicantDetail]

BATCH = "MySQL 정산 테이블을 파티셔닝해 월말 정산 배치 시간을 40% 줄였습니다."


def context_for(applicants: Applicants, company: CompanyProfile, posting: PostingContent) -> ChatContext:
    return make_context(applicants, company, posting, message="@정유민 강점과 확인할 점은?", mentions=["정유민"])


def answer(
    *, message: str = "정산 배치 개선 경험을 확인했어요.", items: Sequence[AnswerItem] | None = None
) -> RootAnswer:
    return RootAnswer(
        message=message,
        items=list(items)
        if items is not None
        else [
            AnswerItem(
                candidate="C1",
                label="강점",
                text="정산 배치 시간 40% 단축",
                status="OK",
                evidence=[AnswerEvidence(sentence=BATCH, source="이력서")],
            )
        ],
    )


async def ask(llm: FakeLlm, context: ChatContext) -> ChatPlan:
    targets = resolve(context)
    # 명시한 한 명의 정리와 분리해 도구 루프의 검증 및 보완을 검사한다.
    targets = Targets(rows=targets.rows, ambiguous=targets.ambiguous, implied=bool(targets.rows))
    return await plan_answer(llm, RootRoute(kind="ANSWER"), context, targets, default_toolkit())


async def test_missing_items_is_repaired_using_the_documents_already_read(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        ToolCall("get_candidate_documents", {"candidate": "C1"}),
        ToolCall("RootAnswer", {"message": "상세 근거는 items를 참고하세요. (C1)}},"}),
        answer(),
    )

    plan = await ask(llm, context)

    assert plan.intent is Intent.ANSWER
    assert [(item.text, item.status) for item in plan.items] == [("정산 배치 시간 40% 단축", "OK")]
    assert plan.sources == ["이력서"]
    assert "items" not in plan.message and "}}" not in plan.message
    assert len(llm.calls) == 3
    assert BATCH in llm.calls[-1].user


async def test_empty_candidate_answer_gets_feedback_and_is_completed(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(answer(items=[]), answer())

    plan = await ask(llm, context)

    assert len(plan.items) == 1
    assert plan.items[0].status == "OK"
    assert len(llm.calls) == 2
    assert "항목" in llm.calls[1].user


async def test_unverified_claim_is_retried_then_replaced_with_an_honest_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    invented = "10년 동안 증권사 시스템을 설계했습니다."
    invalid = answer(
        message=invented,
        items=[
            AnswerItem(
                candidate="C1",
                label="강점",
                text=invented,
                status="OK",
                evidence=[AnswerEvidence(sentence=invented, source="이력서")],
            )
        ],
    )
    llm = FakeLlm(invalid, invalid)

    plan = await ask(llm, context)

    assert len(llm.calls) == 2
    assert "근거" in llm.calls[1].user
    assert plan.items[0].status == "CHECK"
    assert invented not in plan.message
    assert invented not in plan.items[0].text
    assert plan.sources == []


async def test_an_honest_check_does_not_trigger_another_model_call(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        answer(
            message="본인 역할은 추가 확인이 필요해요.",
            items=[AnswerItem(candidate="C1", label="본인 역할", text="추가 확인이 필요해요.", status="CHECK")],
        )
    )

    plan = await ask(llm, context)

    assert plan.items[0].status == "CHECK"
    assert plan.message == "본인 역할은 추가 확인이 필요해요."
    assert len(llm.calls) == 1


@pytest.mark.parametrize(
    "message",
    [
        "정리했어요. (C1)}},",
        "정리했어요. (C1)}}, 다음 내용을 보세요.",
        "상세 근거는 items를 참고하세요.",
        "상세 근거는 items에 정리했어요.",
        "상세 내용은 `items` 배열을 참고하세요.",
        "<think>요약을 작성하자</think>",
    ],
)
async def test_bad_message_is_rewritten_without_losing_verified_items(
    message: str, sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(answer(message=message), answer())

    plan = await ask(llm, context)

    assert len(llm.calls) == 2
    assert plan.message == "정산 배치 개선 경험을 확인했어요."
    assert plan.items[0].status == "OK"


async def test_failed_rewrite_preserves_good_items_and_discards_bad_message(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(answer(message="아래 items로 정리했습니다. (C1)}},"), answer(items=[]))

    plan = await ask(llm, context)

    assert plan.intent is Intent.ANSWER
    assert [(item.text, item.status) for item in plan.items] == [("정산 배치 시간 40% 단축", "OK")]
    assert "items" not in plan.message and "}}" not in plan.message
    assert plan.sources == ["이력서"]
    assert len(llm.calls) == 2


async def test_repeated_empty_answers_end_with_a_candidate_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(answer(items=[]), answer(items=[]))

    plan = await ask(llm, context)

    assert plan.intent is Intent.ANSWER
    assert len(plan.items) == 1
    assert plan.items[0].application_id == sample_applicants["정유민"].info.application_id
    assert plan.items[0].status == "CHECK"
    assert "확인" in plan.items[0].text
    assert plan.sources == []
    assert len(llm.calls) == 2


async def test_stage_count_can_finish_without_candidate_items(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="미결정이 몇 명 남았어?")
    llm = FakeLlm(answer(message="미결정은 8명이에요.", items=[]))

    plan = await ask(llm, context)

    assert plan.message == "미결정은 8명이에요."
    assert plan.items == []
    assert len(llm.calls) == 1


@pytest.mark.parametrize("checked", [["정유민"], ["정유민", "김하늘"]])
async def test_stage_count_ignores_unrelated_checked_candidates(
    checked: list[str], sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="미결정이 몇 명 남았어?", checked=checked
    )
    llm = FakeLlm(answer(message="미결정은 8명이에요.", items=[]))

    plan = await ask(llm, context)

    assert plan.message == "미결정은 8명이에요."
    assert plan.items == []
    assert len(llm.calls) == 1


async def test_technical_method_name_is_not_mistaken_for_an_internal_field(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    message = "dict.items() 사용 경험은 추가 확인이 필요해요."
    llm = FakeLlm(answer(message=message))

    plan = await ask(llm, context)

    assert plan.message == message
    assert len(llm.calls) == 1


async def test_stage_overview_words_keep_the_candidate_recalled_from_previous_turns(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="그 사람 현황 알려줘")
    targets = Targets(rows=[context.candidates[0]], ambiguous=[], implied=True)
    llm = FakeLlm(answer())

    plan = await plan_answer(llm, RootRoute(kind="ANSWER", previous_ref="subject"), context, targets, default_toolkit())

    assert plan.items[0].application_id == sample_applicants["정유민"].info.application_id
    assert "대상 지원자: C1 정유민" in llm.calls[0].user
    assert len(llm.calls) == 1


async def test_missing_items_until_the_limit_still_explains_candidate_uncertainty(
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hiremate_ai.config import settings

    monkeypatch.setattr(settings, "llm_agent_max_calls", 3)
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(*(ToolCall("RootAnswer", {"message": "상세 근거는 items에 정리했어요."}) for _ in range(3)))

    plan = await ask(llm, context)

    assert plan.intent is Intent.CLARIFY
    assert plan.items[0].application_id == sample_applicants["정유민"].info.application_id
    assert plan.items[0].status == "CHECK"
    assert "items" not in plan.message
    assert len(llm.calls) == 3


async def test_single_candidate_empty_notes_are_completed_after_one_rewrite(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        CandidateNotes(items=[]),
        CandidateNotes(items=answer().items),
        MultiSummary(message="정산 배치 개선 경험을 확인했어요."),
    )

    plan = await plan_answer(llm, RootRoute(kind="ANSWER"), context, resolve(context), default_toolkit())

    assert plan.intent is Intent.ANSWER
    assert [(item.application_id, item.text, item.status) for item in plan.items] == [
        (sample_applicants["정유민"].info.application_id, "정산 배치 시간 40% 단축", "OK")
    ]
    assert plan.message == "정산 배치 개선 경험을 확인했어요."
    assert plan.sources == ["이력서"]
    assert [call.output for call in llm.calls] == [CandidateNotes, CandidateNotes, MultiSummary]
    assert BATCH in llm.calls[1].user
    assert "항목" in llm.calls[1].user


async def test_single_candidate_repeated_empty_notes_end_with_an_honest_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        CandidateNotes(items=[]),
        CandidateNotes(items=[]),
        MultiSummary(message="근거를 더 확인해야 해요."),
    )

    plan = await plan_answer(llm, RootRoute(kind="ANSWER"), context, resolve(context), default_toolkit())

    assert plan.intent is Intent.ANSWER
    assert len(plan.items) == 1
    assert plan.items[0].application_id == sample_applicants["정유민"].info.application_id
    assert plan.items[0].status == "CHECK"
    assert "확인" in plan.items[0].text
    assert plan.sources == []
    assert [call.output for call in llm.calls] == [CandidateNotes, CandidateNotes, MultiSummary]
    assert plan.items[0].text in llm.calls[-1].user


async def test_single_candidate_invented_notes_are_replaced_before_summary(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    invented = "10년 동안 증권사 시스템을 설계했습니다."
    invalid = CandidateNotes(
        items=[
            AnswerItem(
                label="강점",
                text=invented,
                status="OK",
                evidence=[AnswerEvidence(sentence=invented, source="이력서")],
            )
        ]
    )
    llm = FakeLlm(
        invalid,
        invalid,
        MultiSummary(message="경력의 근거는 추가 확인이 필요해요."),
    )

    plan = await plan_answer(llm, RootRoute(kind="ANSWER"), context, resolve(context), default_toolkit())

    assert plan.intent is Intent.ANSWER
    assert len(plan.items) == 1
    assert plan.items[0].application_id == sample_applicants["정유민"].info.application_id
    assert plan.items[0].status == "CHECK"
    assert "확인" in plan.items[0].text
    assert invented not in plan.items[0].text
    assert invented not in plan.message
    assert invented not in llm.calls[-1].user
    assert plan.sources == []
    assert [call.output for call in llm.calls] == [CandidateNotes, CandidateNotes, MultiSummary]
    assert "근거" in llm.calls[1].user


async def test_single_candidate_failed_rewrite_keeps_already_verified_notes(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    invalid = AnswerItem(
        label="경력",
        text="증권사 경력 10년",
        status="OK",
        evidence=[AnswerEvidence(sentence="증권사에서 10년 일했습니다.", source="이력서")],
    )
    llm = FakeLlm(
        CandidateNotes(items=[*answer().items, invalid]),
        CandidateNotes(items=[]),
        MultiSummary(message="확인된 경험과 추가 확인할 점을 정리했어요."),
    )

    plan = await plan_answer(llm, RootRoute(kind="ANSWER"), context, resolve(context), default_toolkit())

    assert any(item.text == "정산 배치 시간 40% 단축" and item.status == "OK" for item in plan.items)
    assert plan.sources == ["이력서"]
    assert all("증권사" not in item.text for item in plan.items)
    assert len(llm.calls) == 3


@pytest.mark.parametrize("message", ["정리했어요. (C1)}},", "상세 근거는 items를 참고하세요."])
async def test_single_candidate_bad_summary_uses_a_safe_fallback(
    message: str, sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(CandidateNotes(items=answer().items), MultiSummary(message=message))

    plan = await plan_answer(llm, RootRoute(kind="ANSWER"), context, resolve(context), default_toolkit())

    assert plan.message == MULTI_FALLBACK.format(names="정유민")
    assert [(item.text, item.status) for item in plan.items] == [("정산 배치 시간 40% 단축", "OK")]
    assert plan.sources == ["이력서"]
    assert [call.output for call in llm.calls] == [CandidateNotes, MultiSummary]
