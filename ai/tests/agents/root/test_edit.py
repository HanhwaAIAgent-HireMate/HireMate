from root_context import make_context

from hiremate_ai.agents.root.edit import NO_TARGET, plan_edit
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Decision, EditAction, Intent
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType

type Applicants = dict[str, ApplicantDetail]


def adjust(context: ChatContext, **changes: dict[str, object]) -> ChatContext:
    rows = [row.model_copy(update=changes.get(row.name, {})) for row in context.candidates]
    return context.model_copy(update={"candidates": rows})


def test_edit_uses_only_the_explicit_candidates(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@김하늘 빼줘",
        mentions=["김하늘"],
        checked=["박서준"],
    )

    plan = plan_edit(EditAction.REMOVE, context, [context.candidates[0]])

    assert plan.intent is Intent.EDIT
    assert plan.edit is EditAction.REMOVE
    assert plan.targets == [context.candidates[0].application_id]
    assert plan.message == "정유민 님을 선택 지원자에서 뺐어요."
    assert plan.mode is None and plan.question_targets == []


def test_add_preserves_the_explicit_order(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="그 둘 넣어줘")

    plan = plan_edit(EditAction.ADD, context, [context.candidates[2], context.candidates[0]])

    assert plan.targets == [context.candidates[2].application_id, context.candidates[0].application_id]
    assert plan.message == "박서준, 정유민 님을 선택 지원자에 넣었어요."


def test_no_target_does_not_fall_back_to_checked_or_mentions(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="그 사람 빼줘",
        mentions=["정유민"],
        checked=["김하늘"],
    )

    assert plan_edit(EditAction.REMOVE, context, []) == ChatPlan.answer(Intent.CLARIFY, NO_TARGET)


def test_clear_and_restore_have_no_targets(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="비워줘")

    cleared = plan_edit(EditAction.CLEAR, context, [])
    restored = plan_edit(EditAction.RESTORE, context, [])

    assert (cleared.intent, cleared.edit, cleared.targets) == (Intent.EDIT, EditAction.CLEAR, [])
    assert cleared.message == "선택 지원자를 비웠어요. [되돌리기]로 돌아갈 수 있어요."
    assert (restored.edit, restored.message) == (EditAction.RESTORE, "이전 선택 지원자로 되돌렸어요.")


def test_add_refuses_decided_applicants(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="둘 다 넣어줘")
    context = adjust(context, 정유민={"decision": Decision.PASS}, 김하늘={"decision": Decision.PASS})

    plan = plan_edit(EditAction.ADD, context, context.candidates[:2])

    assert plan == ChatPlan.answer(
        Intent.CLARIFY,
        "정유민, 김하늘 님은 이미 합격 처리한 지원자라 선택 지원자에 넣을 수 없어요. "
        "리스트의 '합격' 탭에서 모아 볼 수 있어요.",
    )


def test_add_keeps_eligible_candidates_and_explains_the_rest(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="셋 다 넣어줘")
    context = adjust(context, 김하늘={"decision": Decision.FAIL}, 박서준={"above_line": False})

    plan = plan_edit(EditAction.ADD, context, context.candidates[:3])

    assert plan.edit is EditAction.ADD
    assert plan.targets == [context.candidates[0].application_id]
    assert plan.message == (
        "정유민 님을 선택 지원자에 넣었어요. "
        "김하늘 님은 이미 불합격 처리한 지원자라 선택 지원자에 넣을 수 없어요. "
        "리스트의 '불합격' 탭에서 모아 볼 수 있어요. "
        "박서준 님은 기준선 아래라 선택 지원자에 넣을 수 없어요. 먼저 기준선 위로 올려 주세요."
    )
    assert [(item.application_id, item.label, item.text, item.status) for item in plan.items] == [
        (
            None,
            "선택 불가",
            "김하늘 님은 이미 불합격 처리한 지원자라 선택 지원자에 넣을 수 없어요. "
            "리스트의 '불합격' 탭에서 모아 볼 수 있어요.",
            "CHECK",
        ),
        (
            None,
            "선택 불가",
            "박서준 님은 기준선 아래라 선택 지원자에 넣을 수 없어요. 먼저 기준선 위로 올려 주세요.",
            "CHECK",
        ),
    ]


def test_add_explains_both_decisions(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="둘 다 넣어줘")
    context = adjust(context, 정유민={"decision": Decision.PASS}, 김하늘={"decision": Decision.FAIL})

    plan = plan_edit(EditAction.ADD, context, context.candidates[:2])

    assert plan.intent is Intent.CLARIFY
    assert "합격과 불합격을 정한" in plan.message
    assert "'합격', '불합격'" in plan.message


def test_line_matters_only_in_document_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="넣어줘", stage_type=StageType.ASSESSMENT
    )
    context = adjust(context, 정유민={"above_line": False})

    plan = plan_edit(EditAction.ADD, context, context.candidates[:1])

    assert plan.targets == [context.candidates[0].application_id]
