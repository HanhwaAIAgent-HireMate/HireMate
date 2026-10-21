"""서류 평가 계산. 모델이 매긴 판정 · 항목 점수를 코드가 합친다.

- 자격요건: 채운 개수 ÷ 평가한 개수가 75% 이상이면 통과 (4개면 3개, 3개면 3개 모두). 반올림하지 않는다.
- AI 적합도 점수 (0~100) = 우대사항 · NCS 평가 조건 (60) + 직무 적합도 (40).
  - 우대사항: 평가 조건마다 근거가 있으면 1, 없으면 0. 우대 점수 = 만족한 조건 수 ÷ 조건 수.
    가중치(1~5)로 평균해 60점으로 바꾼다. 만족한 조건이 많을수록 점수가 오른다.
  - 직무 적합도: 모델이 항목마다 매긴 점수를 0~만점으로 잘라 더한다 (fit.py).
- 보류는 서류를 읽지 못했을 때만이다. 근거가 하나뿐이어도 보류하지 않고 개수대로 점수를 매긴다.
"""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from hiremate_ai.agents.analysis.application.types import (
    CriterionResult,
    FitLine,
    Level,
    PreferenceResult,
    PreferenceStatus,
    QualificationResult,
)

PASS_PERCENT = 75
PREFERENCE_POINTS = 60
FIT_POINTS = 40


def qualification_passed(results: Sequence[QualificationResult]) -> bool:
    """평가한 자격요건 가운데 75% 이상을 채웠는가. 평가할 자격요건이 없으면 통과다."""
    evaluated = [result for result in results if result.evaluated]
    met = sum(result.met for result in evaluated)
    return not evaluated or met * 100 >= PASS_PERCENT * len(evaluated)


def satisfied(criteria: Sequence[CriterionResult]) -> int:
    """근거가 있는 평가 조건 수."""
    return sum(criterion.level == Level.MET for criterion in criteria)


def preference_outcome(criteria: Sequence[CriterionResult]) -> tuple[PreferenceStatus, float | None]:
    """우대사항 하나의 상태와 점수(0~1). 평가 조건이 없으면 점수에 넣지 않는다."""
    if not criteria:
        return PreferenceStatus.UNRATED, None
    return PreferenceStatus.SCORED, satisfied(criteria) / len(criteria)


def preference_points(preferences: Sequence[PreferenceResult]) -> float:
    """우대 점수를 가중치로 평균해 0~60점으로 바꾼다. 가중치가 있는 우대사항이 없으면 0이다."""
    rated = [
        (preference.weight, preference.score)
        for preference in preferences
        if preference.weight is not None and preference.score is not None
    ]
    total_weight = sum(weight for weight, _ in rated)
    if total_weight == 0:
        return 0.0
    return PREFERENCE_POINTS * sum(weight * score for weight, score in rated) / total_weight


def fit_points(lines: Sequence[FitLine]) -> int:
    return min(FIT_POINTS, sum(max(0, min(line.points, line.max)) for line in lines))


def document_score(preferences: Sequence[PreferenceResult], lines: Sequence[FitLine]) -> int:
    """AI 적합도 점수 (0~100). 정수로 반올림한다."""
    value = Decimal(str(preference_points(preferences))) + Decimal(fit_points(lines))
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
