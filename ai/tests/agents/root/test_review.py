from typing import Any

from root_context import make_context

from hiremate_ai.agents.root.analysis import FocusDraft, ItemDraft
from hiremate_ai.agents.root.ledger import Ledger
from hiremate_ai.agents.root.plan import QuestionsPlan
from hiremate_ai.agents.root.review import (
    MESSAGE_FALLBACK,
    REVIEW_INCOMPLETE,
    ClaimJudgement,
    ClaimVerdict,
    answer_plan,
    focus_drafts,
    questions_plan,
    review_items,
)
from hiremate_ai.agents.root.scope import Scope
from hiremate_ai.agents.root.types import ChatContext
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, InterviewerMemo, PostingContent, StageType
from hiremate_ai.llm.chat import LlmFailureReason, LlmOutputError
from hiremate_ai.llm.fake import FakeLlm, FakeReply, LlmCall

type Applicants = dict[str, ApplicantDetail]


def context_of(applicants: Applicants, company: CompanyProfile, posting: PostingContent, **kwargs: Any) -> ChatContext:
    return make_context(applicants, company, posting, **{"message": "협업 경험은 어때?", **kwargs})


def draft(
    *refs: str, status: str = "OK", candidate: str | None = "C1", text: str = "팀 회고를 이끌었어요"
) -> ItemDraft:
    return ItemDraft.model_validate(
        {"candidate": candidate, "label": "협업", "text": text, "status": status, "refs": list(refs)}
    )


def judged(*verdicts: tuple[str, str]) -> ClaimJudgement:
    return ClaimJudgement(verdicts=[ClaimVerdict.model_validate({"id": i, "verdict": v}) for i, v in verdicts])


async def test_team_fact_cannot_be_ok(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    owner = context.candidates[0].application_id
    ref = ledger.add(owner, "팀 · 회고를 진행했다", quote="팀이 회고를 진행했다.", source="자기소개서", cap="CHECK")
    llm = FakeLlm(judged(("I1", "SUPPORTED"), ("M", "SUPPORTED")))

    message, checked = await review_items(llm, context, ledger, "정리했어요.", [draft(ref)])

    assert checked[0].item.status == "CHECK" and message == "정리했어요."


async def test_overstated_becomes_check_and_unrelated_dropped(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    owner = context.candidates[0].application_id
    first = ledger.add(owner, "본인 · 결제 API 개발", quote="결제 API를 개발했다.", source="이력서", cap="OK")
    second = ledger.add(owner, "본인 · 회고 진행", quote="회고를 진행했다.", source="자기소개서", cap="OK")
    llm = FakeLlm(judged(("I1", "OVERSTATED"), ("I2", "UNRELATED"), ("M", "SUPPORTED")))

    _, checked = await review_items(llm, context, ledger, "정리했어요.", [draft(first), draft(second)])

    assert [each.item.status for each in checked] == ["CHECK"]
    assert "결제 API를 개발했다." in llm.calls[0].user


async def test_overstated_message_falls_back(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    ref = ledger.add(context.candidates[0].application_id, "본인 · 결제 API 개발", source="이력서", cap="OK")
    llm = FakeLlm(judged(("I1", "SUPPORTED"), ("M", "OVERSTATED")))

    message, _ = await review_items(llm, context, ledger, "업계 최고 수준이에요.", [draft(ref)])

    assert message == MESSAGE_FALLBACK


async def test_no_candidate_items_skip_model(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    ref = ledger.add(None, "지원자 8명: 미결정 8명", source="전형 결과", cap="OK")
    llm = FakeLlm()

    _, checked = await review_items(llm, context, ledger, "8명이에요.", [draft(ref, candidate=None, text="미결정 8명")])

    assert llm.calls == [] and checked[0].item.status == "OK"


async def test_budget_left_none_keeps_items_as_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    ref = ledger.add(context.candidates[0].application_id, "본인 · 결제 API 개발", source="이력서", cap="OK")

    def exhausted(call: LlmCall) -> FakeReply:
        raise LlmOutputError("예산 초과", reason=LlmFailureReason.BUDGET)

    _, checked = await review_items(FakeLlm(exhausted), context, ledger, "정리했어요.", [draft(ref)])

    assert checked[0].item.status == "CHECK"


async def test_item_without_refs_is_check_and_foreign_ref_is_ignored(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    other = ledger.add(context.candidates[1].application_id, "본인 · 결제 API 개발", source="이력서", cap="OK")
    llm = FakeLlm(judged(("I1", "SUPPORTED"), ("I2", "SUPPORTED"), ("M", "SUPPORTED")))

    _, checked = await review_items(llm, context, ledger, "정리했어요.", [draft(), draft(other)])

    assert [each.item.status for each in checked] == ["CHECK", "CHECK"]
    assert checked[1].evidence == []


async def test_common_item_keeps_candidate_lines_as_evidence(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    line = ledger.add(context.candidates[0].application_id, "C1 정유민, 미결정", source="전형 결과", cap="OK")
    total = ledger.add(None, "지원자 8명: 미결정 8명", source="전형 결과", cap="OK")
    llm = FakeLlm(judged(("I1", "SUPPORTED"), ("M", "SUPPORTED")))

    _, checked = await review_items(llm, context, ledger, "8명이에요.", [draft(total, line, candidate=None)])

    # 지원자별 줄을 인용한 공통 항목은 지원자에 대한 주장이므로 판정을 받는다
    assert checked[0].item.status == "OK" and len(checked[0].evidence) == 2 and len(llm.calls) == 1


async def test_unrelated_message_falls_back(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    ref = ledger.add(context.candidates[0].application_id, "본인 · 결제 API 개발", source="이력서", cap="OK")
    llm = FakeLlm(judged(("I1", "SUPPORTED"), ("M", "UNRELATED")))

    message, _ = await review_items(llm, context, ledger, "박서준은 결제 경험이 없어요.", [draft(ref)])

    assert message == MESSAGE_FALLBACK


async def test_missing_verdicts_lower_items_and_message(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    ref = ledger.add(context.candidates[0].application_id, "본인 · 결제 API 개발", source="이력서", cap="OK")
    llm = FakeLlm(ClaimJudgement(verdicts=[]))

    message, checked = await review_items(llm, context, ledger, "정리했어요.", [draft(ref)])

    assert checked[0].item.status == "CHECK" and message == MESSAGE_FALLBACK


async def test_message_naming_a_candidate_is_judged_without_candidate_items(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    total = ledger.add(None, "지원자 8명: 미결정 8명", source="전형 결과", cap="OK")
    llm = FakeLlm(judged(("M", "UNRELATED")))

    message, _ = await review_items(
        llm, context, ledger, "정유민이 가장 뛰어나요.", [draft(total, candidate=None, text="미결정 8명")]
    )

    assert len(llm.calls) == 1 and message == MESSAGE_FALLBACK


async def test_failed_review_falls_back_message_and_says_so(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    ref = ledger.add(context.candidates[0].application_id, "본인 · 결제 API 개발", source="이력서", cap="OK")

    def broken(call: LlmCall) -> FakeReply:
        raise LlmOutputError("형식 오류")

    message, _ = await review_items(FakeLlm(broken), context, ledger, "최고의 지원자예요.", [draft(ref)])

    assert message.startswith(MESSAGE_FALLBACK) and REVIEW_INCOMPLETE in message


async def test_later_stage_gap_is_removed_from_message(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, later_types=[StageType.INTERVIEW])
    ledger = Ledger()
    ref = ledger.add(context.candidates[0].application_id, "본인 · 결제 API 개발", source="이력서", cap="OK")
    llm = FakeLlm(judged(("I1", "SUPPORTED"), ("M", "SUPPORTED")))

    message, _ = await review_items(llm, context, ledger, "결제 경험이 있어요. 면접 기록이 없어요.", [draft(ref)])

    assert message == "결제 경험이 있어요."


async def test_candidate_item_needs_own_evidence_to_be_ok(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    talent = ledger.add(None, "인재상: 협업", source="회사 소개", cap="OK")
    llm = FakeLlm(judged(("I1", "SUPPORTED"), ("M", "SUPPORTED")))

    _, checked = await review_items(llm, context, ledger, "정리했어요.", [draft(talent, text="협업을 잘해요")])

    assert checked[0].item.status == "CHECK"


def test_nothing_left_is_none() -> None:
    assert answer_plan("답", []) is None


async def test_answer_plan_carries_sources_and_agents(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()
    owner = context.candidates[0].application_id
    ref = ledger.add(owner, "본인 · 결제 API 개발", source="이력서", cap="OK", agent="Application Agent")
    _, checked = await review_items(
        FakeLlm(judged(("I1", "SUPPORTED"), ("M", "SUPPORTED"))), context, ledger, "답", [draft(ref)]
    )

    plan = answer_plan("답", checked)

    assert plan is not None and plan.sources == ["이력서"] and plan.agents == ["Application Agent"]
    assert plan.items[0].application_id == owner


async def test_questions_plan_builds_focus_and_memo(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(
        sample_applicants,
        sample_company,
        sample_posting,
        stage_type=StageType.INTERVIEW,
        message="메모 반영해서 질문 다시 만들어줘",
    )
    row = context.candidates[0]
    memo = InterviewerMemo(stage_id=context.stage_id, stage_name="1차 면접", text="리더 역할 확인")
    ledger = Ledger()
    ref = ledger.add(row.application_id, "[1차 면접] 리더 역할 확인", source="면접관메모", cap="CHECK", memo=memo)
    focus = [FocusDraft(candidate="C1", text="리더 역할을 실제로 맡았는지", refs=[ref])]
    _, checked = await review_items(
        FakeLlm(judged(("I1", "SUPPORTED"), ("M", "SUPPORTED"))), context, ledger, "정리", focus_drafts(focus)
    )
    form = QuestionsPlan(scope=Scope(sources=["mentions"]), checks="memos", replace=True)

    plan = questions_plan(context, [row], form, checked)

    assert plan is not None
    assert plan.question_targets == [row.application_id] and plan.question_replace is True
    assert plan.question_focus[row.application_id].endswith(f"(담당자 요청: {context.message})")
    assert "추가 확인 필요" in plan.question_focus[row.application_id]
    assert plan.question_memos[row.application_id] == memo
    assert "Interview Agent" in plan.agents


async def test_later_stage_gap_is_rewritten(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, later_types=[StageType.INTERVIEW])
    ledger = Ledger()
    ref = ledger.add(context.candidates[0].application_id, "본인 · 결제 API 개발", source="이력서", cap="OK")
    text = "결제 API를 개발했어요. 면접 기록이 없어요."
    llm = FakeLlm(judged(("I1", "SUPPORTED"), ("M", "SUPPORTED")))

    _, checked = await review_items(llm, context, ledger, "정리했어요.", [draft(ref, text=text)])

    assert checked[0].item.text == "결제 API를 개발했어요."
