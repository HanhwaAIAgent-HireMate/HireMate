from uuid import uuid4

from hiremate_ai.agents.analysis.application.rubric_draft import (
    CONFIRM_MARK,
    RubricDraft,
    _Draft,
    draft_fallback_rules,
    fallback_rules,
    is_fallback,
)
from hiremate_ai.agents.analysis.application.types import Criterion, EvaluationRules, Note
from hiremate_ai.contract import CriterionCategory, CriterionType, PostingContent
from hiremate_ai.llm.fake import FakeLlm

POSTING = PostingContent(
    title="매장 운영 담당",
    job_category="유통",
    employment_type="정규직",
    career="경력 무관",
    location="서울",
    intro="",
    duties=["매장 재고 관리", "직원 교육"],
    qualifications=[],
    preferred=[],
    benefits=[],
)


def criterion(criterion_id: str, text: str, *, saved: bool = False) -> Criterion:
    rules = EvaluationRules(met="정해 둔 충족 기준", unmet="정해 둔 미충족 기준") if saved else fallback_rules(text)
    return Criterion(
        criterion_id=criterion_id,
        category=CriterionCategory.PREFERENCE,
        text=text,
        important=False,
        criterion_type=CriterionType.SINGLE,
        evaluation_rules=rules,
    )


async def test_only_unsaved_criteria_get_a_shared_draft() -> None:
    # 직무 이름 · 기술 이름 없이 쓰이는지 매장 운영 공고로 확인한다
    unsaved = criterion("P-01", f"재고 관리/발주 자동화 경험 {uuid4()}")
    saved = criterion("P-02", "고객 응대 경험", saved=True)
    draft = RubricDraft(
        items=[
            _Draft(
                number=1,
                criterion_type="COMPOSITE",
                met="재고 관리와 발주 자동화를 모두 본인이 했다",
                partial="둘 가운데 하나만 본인이 했다",
                unmet="둘 다 하지 않았다고 적혀 있다",
            )
        ]
    )
    llm = FakeLlm(draft)

    first, _ = await draft_fallback_rules(llm, [unsaved, saved], POSTING)
    second, _ = await draft_fallback_rules(llm, [unsaved, saved], POSTING)

    assert first == second
    assert len(llm.calls) == 1  # 같은 공고 문장은 초안을 다시 쓴다
    drafted, kept = first
    assert drafted.criterion_type == CriterionType.COMPOSITE and not is_fallback(drafted)
    assert drafted.evaluation_rules.partial == "둘 가운데 하나만 본인이 했다"
    assert kept == saved


async def test_failed_draft_keeps_the_posting_sentence() -> None:
    unsaved = criterion("P-01", f"매장 운영 경험 {uuid4()}")

    ([result], _) = await draft_fallback_rules(FakeLlm(), [unsaved], POSTING)  # 응답이 없어 초안을 만들지 못한다

    assert result == unsaved


async def test_chosen_interpretation_is_attached_for_the_recruiter_to_confirm() -> None:
    # 분야를 묶은 가운뎃점처럼 공고 문장만으로 정할 수 없는 해석은 담당자 확인으로 알린다
    unsaved = criterion("P-01", f"유통·커머스 도메인 경험 {uuid4()}")
    notice = Note(
        text=f"'{unsaved.text}'에 맞는 평가 기준이 없어 AI가 만든 판정 기준 초안으로 판정했어요.", source="평가 기준"
    )
    other = Note(text="다른 알림", source="공고")
    draft = RubricDraft(
        items=[
            _Draft(
                number=1,
                criterion_type="SINGLE",
                met="유통 또는 커머스 분야에서 매장 운영 업무를 본인이 했다. 다른 직무 경험은 충족 근거가 아니다",
                unmet="두 분야 모두 업무 경험이 없다고 적혀 있다",
                confirm="두 분야 중 한 분야만 있어도 인정할지, 매장 운영 업무로 좁혀도 될지 확인이 필요하다",
            )
        ]
    )

    (drafted,), notes = await draft_fallback_rules(FakeLlm(draft), [unsaved], POSTING, notes=[notice, other])

    assert drafted.criterion_type == CriterionType.SINGLE
    assert notes[0].text == f"{notice.text}{CONFIRM_MARK}{draft.items[0].confirm}"
    assert notes[1] == other
