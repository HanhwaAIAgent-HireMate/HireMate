from root_context import extra_row, make_context

from hiremate_ai.agents.root.edit import NO_CHECKED, NO_TARGET, plan_edit
from hiremate_ai.agents.root.route import NOT_UNDERSTOOD, RootRoute
from hiremate_ai.agents.root.targets import resolve
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Decision, EditAction, Intent
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType

type Applicants = dict[str, ApplicantDetail]


def edit(context: ChatContext, action: EditAction | None, *, uses_checked: bool = False) -> ChatPlan:
    return plan_edit(RootRoute(kind="EDIT", edit=action, uses_checked=uses_checked), context, resolve(context))


def adjust(context: ChatContext, **changes: dict[str, object]) -> ChatContext:
    """이름별로 지원자 행을 바꾼다. 예: adjust(context, 정유민={"decision": Decision.PASS})."""
    rows = [row.model_copy(update=changes.get(row.name, {})) for row in context.candidates]
    return context.model_copy(update={"candidates": rows})


def test_remove_mentioned(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="@김하늘 빼줘", mentions=["김하늘"]
    )

    plan = edit(context, EditAction.REMOVE)

    assert plan.intent is Intent.EDIT
    assert plan.edit is EditAction.REMOVE
    assert plan.targets == [sample_applicants["김하늘"].info.application_id]
    assert plan.message == "김하늘 님을 선택 지원자에서 뺐어요."
    assert plan.mode is None
    assert plan.question_targets == []


def test_add_by_name(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="정유민도 추가해줘")

    plan = edit(context, EditAction.ADD)

    assert plan.edit is EditAction.ADD
    assert plan.targets == [sample_applicants["정유민"].info.application_id]
    assert plan.message == "정유민 님을 선택 지원자에 넣었어요."


def test_uses_checked(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="이 3명 빼줘", checked=["정유민", "김하늘", "박서준"]
    )

    plan = edit(context, EditAction.REMOVE, uses_checked=True)

    assert len(plan.targets) == 3
    assert plan.message == "정유민, 김하늘, 박서준 님을 선택 지원자에서 뺐어요."


def test_checked_empty_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="이 사람들 빼줘")

    assert edit(context, EditAction.REMOVE, uses_checked=True) == ChatPlan.answer(Intent.CLARIFY, NO_CHECKED)


def test_no_target_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="그 사람 빼줘")

    assert edit(context, EditAction.REMOVE) == ChatPlan.answer(Intent.CLARIFY, NO_TARGET)


def test_same_name_clarifies_without_executing(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="정유민, 김하늘 빼줘",
        extra_rows=[extra_row("정유민")],
    )

    plan = edit(context, EditAction.REMOVE)

    assert plan == ChatPlan.answer(Intent.CLARIFY, "정유민 이름의 지원자가 여러 명이에요. @로 골라 주세요.")


def test_clear_and_restore(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="비워줘")

    cleared = edit(context, EditAction.CLEAR)
    restored = edit(context, EditAction.RESTORE)

    assert (cleared.intent, cleared.edit, cleared.targets) == (Intent.EDIT, EditAction.CLEAR, [])
    assert cleared.message == "선택 지원자를 비웠어요. [되돌리기]로 돌아갈 수 있어요."
    assert (restored.edit, restored.message) == (EditAction.RESTORE, "이전 선택 지원자로 되돌렸어요.")


def test_edit_without_action_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="정유민 어떻게 해줘")

    assert edit(context, None) == ChatPlan.answer(Intent.CLARIFY, NOT_UNDERSTOOD)


def test_mention_wins_over_checked(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="@김하늘 빼줘",
        mentions=["김하늘"],
        checked=["정유민", "박서준", "이도윤"],
    )

    plan = edit(context, EditAction.REMOVE, uses_checked=True)

    assert plan.targets == [sample_applicants["김하늘"].info.application_id]


def test_add_refuses_decided_applicants(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="이 둘 올려줘", checked=["정유민", "김하늘"]
    )
    context = adjust(context, 정유민={"decision": Decision.PASS}, 김하늘={"decision": Decision.PASS})

    plan = edit(context, EditAction.ADD, uses_checked=True)

    # backend는 결정한 지원자를 선택 지원자에 넣지 않는다 (409 ALREADY_DECIDED). 보내지 않고 이유를 말한다
    assert plan == ChatPlan.answer(
        Intent.CLARIFY,
        "정유민, 김하늘 님은 이미 합격 처리한 지원자라 선택 지원자에 넣을 수 없어요. "
        "리스트의 '합격' 탭에서 모아 볼 수 있어요.",
    )


def test_add_keeps_selectable_and_explains_the_rest(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="셋 다 넣어줘",
        checked=["정유민", "김하늘", "박서준"],
    )
    context = adjust(context, 김하늘={"decision": Decision.FAIL}, 박서준={"above_line": False})

    plan = edit(context, EditAction.ADD, uses_checked=True)

    assert plan.edit is EditAction.ADD
    assert plan.targets == [sample_applicants["정유민"].info.application_id]
    assert plan.message == (
        "정유민 님을 선택 지원자에 넣었어요. "
        "김하늘 님은 이미 불합격 처리한 지원자라 선택 지원자에 넣을 수 없어요. "
        "리스트의 '불합격' 탭에서 모아 볼 수 있어요. "
        "박서준 님은 기준선 아래라 선택 지원자에 넣을 수 없어요. 먼저 기준선 위로 올려 주세요."
    )


def test_add_names_both_decisions_when_mixed(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="이 둘 넣어줘", checked=["정유민", "김하늘"]
    )
    context = adjust(context, 정유민={"decision": Decision.PASS}, 김하늘={"decision": Decision.FAIL})

    plan = edit(context, EditAction.ADD, uses_checked=True)

    assert plan.intent is Intent.CLARIFY
    assert plan.message == (
        "정유민, 김하늘 님은 이미 합격 · 불합격을 정한 지원자라 선택 지원자에 넣을 수 없어요. "
        "리스트의 '합격' · '불합격' 탭에서 모아 볼 수 있어요."
    )


def test_line_only_matters_in_document_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="정유민도 넣어줘", stage_type=StageType.ASSESSMENT
    )
    context = adjust(context, 정유민={"above_line": False})

    plan = edit(context, EditAction.ADD)

    assert plan.targets == [sample_applicants["정유민"].info.application_id]
