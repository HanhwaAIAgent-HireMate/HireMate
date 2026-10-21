import pytest

from hiremate_ai.agents.analysis.application.judge import short_label
from hiremate_ai.agents.analysis.application.score import (
    document_score,
    fit_points,
    preference_outcome,
    preference_points,
    qualification_passed,
)
from hiremate_ai.agents.analysis.application.types import (
    CriterionResult,
    FitLine,
    Level,
    PreferenceResult,
    PreferenceStatus,
    QualificationResult,
)


def qualifications(*met: bool) -> list[QualificationResult]:
    return [
        QualificationResult(number=number, text=f"Q{number}", met=value, reason="")
        for number, value in enumerate(met, start=1)
    ]


def criteria(*levels: Level) -> list[CriterionResult]:
    return [
        CriterionResult(number=number, content_no=f"1-{number}", content="조건", level=level, reason="")
        for number, level in enumerate(levels, start=1)
    ]


def preference(number: int, weight: int, score: float | None, status: PreferenceStatus) -> PreferenceResult:
    return PreferenceResult(
        number=number, text=f"P{number}", weight=weight, unit_code="x", unit_name="x", status=status, score=score
    )


def line(points: int, top: int) -> FitLine:
    return FitLine(key="k", label="항목", points=points, max=top, reason="")


@pytest.mark.parametrize(
    ("met", "passed"),
    [
        ((True, True, True, False), True),  # 4개 중 3개 = 75%
        ((True, True, True, True, False), True),  # 5개 중 4개 = 80%
        ((True, True, True, False, False), False),  # 5개 중 3개 = 60%
        ((True, True, False), False),  # 3개 중 2개 = 66.7%
        ((), True),  # 자격요건이 없으면 통과
    ],
)
def test_qualification_passes_at_75_percent(met: tuple[bool, ...], passed: bool) -> None:
    assert qualification_passed(qualifications(*met)) is passed


def test_unevaluated_qualification_is_left_out_of_the_rate() -> None:
    results = [
        *qualifications(True, True, True),
        QualificationResult(number=4, text="", met=False, evaluated=False, reason=""),
    ]

    assert qualification_passed(results)


def test_preference_score_is_share_of_satisfied_criteria() -> None:
    # 근거가 하나뿐이어도 보류하지 않고 개수대로 매긴다
    one = criteria(Level.MET, Level.NONE, Level.NONE, Level.NONE)
    two = criteria(Level.MET, Level.MET, Level.NONE, Level.NONE)
    assert preference_outcome(one) == (PreferenceStatus.SCORED, 0.25)
    assert preference_outcome(two) == (PreferenceStatus.SCORED, 0.5)
    assert preference_outcome(criteria(Level.NONE, Level.NONE)) == (PreferenceStatus.SCORED, 0.0)
    assert preference_outcome([]) == (PreferenceStatus.UNRATED, None)


def test_preference_points_are_weighted_to_60() -> None:
    preferences = [
        preference(1, 5, 0.8, PreferenceStatus.SCORED),
        preference(2, 4, 0.5, PreferenceStatus.SCORED),
        preference(3, 3, 4 / 6, PreferenceStatus.SCORED),
        preference(4, 3, 0.0, PreferenceStatus.SCORED),
        preference(5, 2, 0.4, PreferenceStatus.SCORED),
        preference(6, 1, None, PreferenceStatus.UNRATED),
    ]

    # 60 × 8.8 ÷ 17 = 31.06
    assert round(preference_points(preferences), 2) == 31.06
    assert preference_points([]) == 0


def test_fit_points_are_clamped() -> None:
    assert fit_points([line(12, 10), line(-3, 8), line(5, 8)]) == 15


def test_document_score_adds_both_parts_and_rounds_half_up() -> None:
    preferences = [preference(1, 1, 0.5, PreferenceStatus.SCORED)]  # 30점
    assert document_score(preferences, [line(10, 10), line(5, 8)]) == 45
    assert document_score([preference(1, 2, 1 / 8, PreferenceStatus.SCORED)], [line(0, 10)]) == 8  # 7.5 → 8


def test_shortfall_label_fits_beside_name() -> None:
    assert short_label("Git 근거 없음") == "Git 근거 없음"
    assert short_label("RDBMS 경험 근거 없음") == "RDBMS 경험"
    assert short_label("Spring Boot REST API 경험 근거 없음") == "Spring Boot"
    assert short_label("  ") == "근거 없음"
