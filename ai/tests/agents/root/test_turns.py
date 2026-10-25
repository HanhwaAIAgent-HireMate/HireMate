from uuid import UUID, uuid4

from root_context import make_context

from hiremate_ai.agents.root.find import NOT_FOUND
from hiremate_ai.agents.root.turns import next_result, turn_of
from hiremate_ai.agents.root.types import ChatItem, ChatPlan, EditAction, Intent, SelectionMode
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent

type Applicants = dict[str, ApplicantDetail]

A, B, C = (str(uuid4()) for _ in range(3))


def found(*ids: str, mode: SelectionMode = SelectionMode.REPLACE) -> ChatPlan:
    return ChatPlan(
        intent=Intent.FIND,
        mode=mode,
        edit=None,
        targets=[UUID(application_id) for application_id in ids],
        message="찾았어요.",
        items=[],
        sources=[],
        agents=[],
        question_targets=[],
        question_focus={},
    )


NOT_FOUND_PLAN = ChatPlan.answer(Intent.ANSWER, NOT_FOUND)


def test_replace_sets_result() -> None:
    assert next_result([A], "FIND", SelectionMode.REPLACE, found(B, C)) == [B, C]


def test_empty_replace_empties_result() -> None:
    assert next_result([A], "FIND", SelectionMode.REPLACE, NOT_FOUND_PLAN) == []
    assert next_result([A], "FIND", None, NOT_FOUND_PLAN) == []


def test_empty_narrow_keeps_result() -> None:
    assert next_result([A, B], "FIND", SelectionMode.NARROW, NOT_FOUND_PLAN) == [A, B]
    assert next_result([A, B], "FIND", SelectionMode.ADD, NOT_FOUND_PLAN) == [A, B]


def test_narrow_sets_result() -> None:
    assert next_result([A, B], "FIND", SelectionMode.NARROW, found(B, mode=SelectionMode.NARROW)) == [B]


def test_add_appends_new() -> None:
    assert next_result([A, B], "FIND", SelectionMode.ADD, found(B, C, mode=SelectionMode.ADD)) == [A, B, C]
    assert next_result(None, "FIND", SelectionMode.ADD, found(C, mode=SelectionMode.ADD)) == [C]


def test_question_targets_become_result() -> None:
    plan = ChatPlan.answer(Intent.ANSWER, "질문을 만들었어요.").model_copy(update={"question_targets": [UUID(C)]})

    assert next_result([A], "ANSWER", None, plan) == [C]


def test_answer_and_edit_keep_result() -> None:
    edit = ChatPlan(
        intent=Intent.EDIT,
        mode=None,
        edit=EditAction.REMOVE,
        targets=[UUID(B)],
        message="뺐어요.",
        items=[],
        sources=[],
        agents=[],
        question_targets=[],
        question_focus={},
    )

    assert next_result([A, B], "EDIT", None, edit) == [A, B]
    assert next_result([A, B], "ANSWER", None, ChatPlan.answer(Intent.ANSWER, "강점이에요.")) == [A, B]
    assert next_result(None, "ANSWER", None, ChatPlan.answer(Intent.ANSWER, "강점이에요.")) is None


def test_clarify_keeps_result() -> None:
    assert next_result([A], "FIND", SelectionMode.REPLACE, ChatPlan.answer(Intent.CLARIFY, "무엇을 찾을까요?")) == [A]


def test_answer_turn_preserves_explicit_target_order(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="그 둘 확인해줘")
    targets = [context.candidates[2].application_id, context.candidates[0].application_id]

    turn = turn_of(context, targets, ChatPlan.answer(Intent.ANSWER, "확인이 필요해요."), "ANSWER")

    assert turn["targets"] == [str(target) for target in targets]


def test_find_turn_targets_are_only_found(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="양자 컴퓨팅 경험자 찾아줘")
    kim = next(row for row in context.candidates if row.name == "김하늘")

    turn = turn_of(context, [kim.application_id], NOT_FOUND_PLAN, "FIND")

    assert turn["targets"] == []


def found_among_decided(*ids: str) -> ChatPlan:
    """합격과 불합격한 지원자 안에서 찾은 답. 선택 지원자를 바꾸지 않아 찾은 사람은 항목에만 있다."""
    items = [
        ChatItem(application_id=UUID(application_id), label="이름", text="근거", status=None) for application_id in ids
    ]
    return ChatPlan.answer(Intent.ANSWER, "합격한 지원자 3명 중 조건에 맞는 사람은 **2명**이에요.", items)


def test_find_among_decided_sets_result() -> None:
    assert next_result([A], "FIND", SelectionMode.REPLACE, found_among_decided(B, C)) == [B, C]


def test_find_among_decided_turn_keeps_found(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="합격자 중 금융 경험자 찾아줘")

    turn = turn_of(context, [], found_among_decided(B, C), "FIND")

    assert turn["targets"] == [B, C]
