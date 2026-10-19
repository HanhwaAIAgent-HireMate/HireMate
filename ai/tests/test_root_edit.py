from root_context import extra_row, make_context

from hiremate_ai.agents.root.edit import NO_CHECKED, NO_TARGET, plan_edit
from hiremate_ai.agents.root.route import NOT_UNDERSTOOD, RootRoute
from hiremate_ai.agents.root.targets import resolve
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, EditAction, Intent
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent

type Applicants = dict[str, ApplicantDetail]


def edit(context: ChatContext, action: EditAction | None, *, uses_checked: bool = False) -> ChatPlan:
    return plan_edit(RootRoute(kind="EDIT", edit=action, uses_checked=uses_checked), context, resolve(context))


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
