import pytest

from hiremate_ai.agents.analysis.application.judge import short_label, unknown_label, unmet_label
from hiremate_ai.agents.analysis.application.score import qualification_pass, scores, zeroed_scores
from hiremate_ai.agents.analysis.application.types import CriterionResult
from hiremate_ai.contract import CriterionCategory, CriterionType, QualificationStatus, Verdict

Q, P = CriterionCategory.QUALIFICATION, CriterionCategory.PREFERENCE


def item(category: CriterionCategory, verdict: Verdict, *, important: bool = False, number: int = 1) -> CriterionResult:
    return CriterionResult(
        criterion_id=f"{category.value[0]}-{number:02d}",
        category=category,
        text="항목",
        important=important,
        criterion_type=CriterionType.COMPOSITE,
        verdict=verdict,
        reason="",
    )


def test_design_example_qualifications_and_total() -> None:
    # 경력 3년 0 · 자격증 1 · 커뮤니케이션 1 · 영어 1 → 50 × 3 ÷ 4 = 37.5, 우대사항 40점이면 총점 77.5
    results = [
        item(Q, Verdict.NOT_MET, number=1),
        item(Q, Verdict.MET, number=2),
        item(Q, Verdict.MET, number=3),
        item(Q, Verdict.MET, number=4),
        *(item(P, Verdict.MET, number=n) for n in range(1, 5)),
        item(P, Verdict.NOT_MET, number=5),
    ]

    computed = scores(results)

    assert (computed.qualification_score, computed.preference_score, computed.total) == (37.5, 40.0, 77.5)
    # 4개 중 3개 → 통과. 모든 항목이 같은 비중이라 자격요건 37.5점(75%)이 곧 통과선이다
    assert qualification_pass(results) == (QualificationStatus.PASSED, 75.0)


def test_each_area_is_50_points_regardless_of_item_count() -> None:
    few = [item(Q, Verdict.MET), item(P, Verdict.MET)]
    many = [*(item(Q, Verdict.MET, number=n) for n in range(1, 9)), item(P, Verdict.MET)]

    assert scores(few).qualification_score == scores(many).qualification_score == 50.0


def test_every_item_in_an_area_has_the_same_share_even_if_marked_important() -> None:
    results = [item(Q, Verdict.MET, important=True, number=1), item(Q, Verdict.NOT_MET, number=2), item(P, Verdict.MET)]

    assert scores(results).qualification_score == 25.0


def test_without_preferences_qualifications_take_100() -> None:
    results = [item(Q, Verdict.MET, number=1), item(Q, Verdict.PARTIAL, number=2)]

    computed = scores(results)

    assert (computed.qualification_max, computed.preference_max, computed.total) == (100, 0, 75.0)


def test_unknown_holds_the_area_and_the_total() -> None:
    results = [item(Q, Verdict.MET), item(P, Verdict.MET, number=1), item(P, Verdict.UNKNOWN, number=2)]

    computed = scores(results)

    # 확인 필요를 0으로 바꾸거나 분모에서 빼서 점수를 매기지 않는다
    assert (computed.qualification_score, computed.preference_score, computed.total) == (50.0, None, None)


def test_held_score_counts_unknown_as_zero() -> None:
    results = [
        item(Q, Verdict.MET, number=1),
        item(Q, Verdict.UNKNOWN, number=2),
        item(P, Verdict.PARTIAL, number=1),
        item(P, Verdict.UNKNOWN, number=2),
    ]

    zeroed = zeroed_scores(results)

    assert (zeroed.qualification_score, zeroed.preference_score, zeroed.total) == (25.0, 12.5, 37.5)
    assert scores(results).total is None  # 확정 점수는 여전히 보류다


def test_zeroed_score_equals_score_without_unknown() -> None:
    results = [item(Q, Verdict.MET, number=1), item(Q, Verdict.PARTIAL, number=2), item(P, Verdict.NOT_MET)]

    assert zeroed_scores(results) == scores(results)


def test_no_criteria_has_no_zeroed_score() -> None:
    assert zeroed_scores([]).total is None


def test_same_judgements_give_the_same_score() -> None:
    results = [item(Q, Verdict.PARTIAL, number=1), item(Q, Verdict.MET, number=2)]

    assert scores(results) == scores(list(results))


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ((Verdict.MET, Verdict.MET, Verdict.MET, Verdict.NOT_MET), (QualificationStatus.PASSED, 75.0)),
        ((Verdict.MET, Verdict.MET, Verdict.PARTIAL, Verdict.NOT_MET), (QualificationStatus.FAILED, 62.5)),
        ((Verdict.MET, Verdict.MET, Verdict.MET, Verdict.UNKNOWN), (QualificationStatus.PASSED, None)),
        ((Verdict.MET, Verdict.MET, Verdict.UNKNOWN, Verdict.NOT_MET), (QualificationStatus.UNDETERMINED, None)),
        ((Verdict.MET, Verdict.UNKNOWN, Verdict.NOT_MET, Verdict.NOT_MET), (QualificationStatus.FAILED, None)),
        ((), (QualificationStatus.PASSED, None)),
    ],
)
def test_qualification_pass_counts_partial_as_half_and_holds_on_unknown(
    verdicts: tuple[Verdict, ...], expected: tuple[QualificationStatus, float | None]
) -> None:
    results = [item(Q, verdict, number=number) for number, verdict in enumerate(verdicts, start=1)]

    assert qualification_pass(results) == expected


def test_shortfall_labels_fit_beside_name() -> None:
    assert short_label("Git 근거 없음") == "Git 근거 없음"
    assert short_label("RDBMS 경험 근거 없음") == "RDBMS 경험"
    assert short_label("Spring Boot REST API 경험 근거 없음") == "Spring Boot"
    assert short_label("  ") == "근거 없음"
    assert unknown_label("Git 기반 협업 경험") == "Git 확인 필요"
    assert unmet_label("JUnit 등으로 테스트 코드를 작성한 경험") == "JUnit 근거 없음"
    assert unmet_label("JUnit 등으로 테스트 코드를 작성한 경험", "테스트 근거 없음") == "테스트 근거 없음"
