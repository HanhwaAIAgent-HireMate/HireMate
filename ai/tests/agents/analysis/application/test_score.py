import pytest

from hiremate_ai.agents.analysis.application.judge import short_label, unknown_label, unmet_label
from hiremate_ai.agents.analysis.application.score import Weights, qualification_pass, scores
from hiremate_ai.agents.analysis.application.types import CriterionResult
from hiremate_ai.contract import CriterionCategory, CriterionType, QualificationStatus, Verdict

WEIGHTS = Weights(normal=1.0, important=1.5)
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
    # 경력 3년(중요) 0 · 자격증 1 · 커뮤니케이션 1 · 영어 1 → 50 × 3 ÷ 4.5 = 33.33, 우대사항 40점이면 총점 73.33
    results = [
        item(Q, Verdict.NOT_MET, important=True, number=1),
        item(Q, Verdict.MET, number=2),
        item(Q, Verdict.MET, number=3),
        item(Q, Verdict.MET, number=4),
        *(item(P, Verdict.MET, number=n) for n in range(1, 5)),
        item(P, Verdict.NOT_MET, number=5),
    ]

    computed = scores(results, WEIGHTS)

    assert (computed.qualification_score, computed.preference_score, computed.total) == (33.3, 40.0, 73.3)
    # 75% 통과는 계수를 쓰지 않는다: 4개 중 3개 → 통과. 중요 항목 미충족만으로 탈락하지 않는다
    assert qualification_pass(results) == (QualificationStatus.PASSED, 75.0)


def test_each_area_is_50_points_regardless_of_item_count() -> None:
    few = [item(Q, Verdict.MET), item(P, Verdict.MET)]
    many = [*(item(Q, Verdict.MET, number=n) for n in range(1, 9)), item(P, Verdict.MET)]

    assert scores(few, WEIGHTS).qualification_score == scores(many, WEIGHTS).qualification_score == 50.0


def test_general_items_count_and_importance_is_a_coefficient() -> None:
    results = [item(Q, Verdict.MET, important=True, number=1), item(Q, Verdict.NOT_MET, number=2), item(P, Verdict.MET)]

    # 50 × 1.5 ÷ 2.5 = 30. 일반 항목도 분모에 들어간다
    assert scores(results, WEIGHTS).qualification_score == 30.0
    assert scores(results, Weights(normal=1, important=2)).qualification_score == 33.3


def test_without_preferences_qualifications_take_100() -> None:
    results = [item(Q, Verdict.MET, number=1), item(Q, Verdict.PARTIAL, number=2)]

    computed = scores(results, WEIGHTS)

    assert (computed.qualification_max, computed.preference_max, computed.total) == (100, 0, 75.0)


def test_unknown_holds_the_area_and_the_total() -> None:
    results = [item(Q, Verdict.MET), item(P, Verdict.MET, number=1), item(P, Verdict.UNKNOWN, number=2)]

    computed = scores(results, WEIGHTS)

    # 확인 필요를 0으로 바꾸거나 분모에서 빼서 점수를 매기지 않는다
    assert (computed.qualification_score, computed.preference_score, computed.total) == (50.0, None, None)


def test_same_judgements_give_the_same_score() -> None:
    results = [item(Q, Verdict.PARTIAL, important=True, number=1), item(Q, Verdict.MET, number=2)]

    assert scores(results, WEIGHTS) == scores(list(results), WEIGHTS)


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
