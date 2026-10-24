"""서류 평가 계산. 모델이 정한 판정과 사람이 정한 중요 표시를 코드가 합친다. 모델은 점수나 계수를 정하지 않는다.

- 점수: 자격요건 50점 + 우대사항 50점. 영역 점수 = 영역 만점 × Σ(계수 × 충족도) ÷ Σ계수.
  계수는 일반 1, 중요 1.5 (설정값). 항목 수와 상관없이 영역 만점은 50점이고, 한 영역만 있으면 그 영역이 100점이다.
- 확인 필요(UNKNOWN)는 0이나 0.5로 바꾸지 않고 분모에서도 빼지 않는다. 남아 있으면 그 영역 점수와 총점은 None(보류)이다.
- 계산은 원래 정밀도로 하고 표시할 점수만 소수 첫째 자리에서 사사오입한다. 같은 판정이면 결과가 같다.
- 자격요건 75% 통과는 점수와 따로 판단한다. 계수를 쓰지 않고 충족 1 · 부분 충족 0.5 · 미충족 0개로 센다.
  확인 필요는 0과 1을 모두 넣어 보고, 결과가 갈리면 판단 보류(UNDETERMINED)다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from hiremate_ai.agents.analysis.application.types import CriterionResult
from hiremate_ai.contract import CriterionCategory, QualificationStatus, Verdict

PASS_PERCENT = Decimal(75)
FULL = 100


@dataclass(frozen=True)
class Weights:
    normal: float
    important: float

    def of(self, result: CriterionResult) -> Decimal:
        return Decimal(str(self.important if result.important else self.normal))


@dataclass(frozen=True)
class Scores:
    qualification_score: float | None
    qualification_max: int
    preference_score: float | None
    preference_max: int
    total: float | None  # 보류면 None


def area_maxes(results: Sequence[CriterionResult]) -> dict[CriterionCategory, int]:
    """영역 만점. 두 영역이 다 있으면 50 · 50, 한 영역만 있으면 그 영역이 100이다."""
    present = [category for category in CriterionCategory if any(r.category == category for r in results)]
    return {category: (FULL // len(present) if category in present else 0) for category in CriterionCategory}


def allotted(result: CriterionResult, results: Sequence[CriterionResult], weights: Weights) -> Decimal:
    """항목 배점 = 영역 만점 × 항목 계수 ÷ 영역 계수 합."""
    same = [other for other in results if other.category == result.category]
    total = sum((weights.of(other) for other in same), Decimal(0))
    return Decimal(area_maxes(results)[result.category]) * weights.of(result) / total if total else Decimal(0)


def scores(results: Sequence[CriterionResult], weights: Weights) -> Scores:
    maxes = area_maxes(results)
    values: dict[CriterionCategory, Decimal | None] = {}
    for category in CriterionCategory:
        area = [result for result in results if result.category == category]
        if not area or any(result.verdict == Verdict.UNKNOWN for result in area):
            values[category] = None
            continue
        values[category] = sum(
            (allotted(result, results, weights) * Decimal(str(result.fulfillment)) for result in area), Decimal(0)
        )
    total: Decimal | None = Decimal(0) if any(maxes.values()) else None
    for category in CriterionCategory:
        part = values[category]
        if maxes[category] and total is not None:
            total = None if part is None else total + part
    quality, preference = values[CriterionCategory.QUALIFICATION], values[CriterionCategory.PREFERENCE]
    return Scores(
        qualification_score=_display(quality),
        qualification_max=maxes[CriterionCategory.QUALIFICATION],
        preference_score=_display(preference),
        preference_max=maxes[CriterionCategory.PREFERENCE],
        total=_display(total),
    )


def qualification_pass(results: Sequence[CriterionResult]) -> tuple[QualificationStatus, float | None]:
    """75% 통과 판단과 충족률(%). 자격요건이 없으면 통과다. 확인 필요가 있으면 충족률은 None이다."""
    area = [result for result in results if result.category == CriterionCategory.QUALIFICATION]
    if not area:
        return QualificationStatus.PASSED, None
    known = sum((Decimal(str(result.fulfillment)) for result in area if result.fulfillment is not None), Decimal(0))
    unknown = sum(result.verdict == Verdict.UNKNOWN for result in area)
    low = known * 100 / len(area)
    high = (known + unknown) * 100 / len(area)
    rate = _display(low) if unknown == 0 else None
    if low >= PASS_PERCENT:
        return QualificationStatus.PASSED, rate
    if high < PASS_PERCENT:
        return QualificationStatus.FAILED, rate
    return QualificationStatus.UNDETERMINED, rate


def _display(value: Decimal | None) -> float | None:
    return None if value is None else float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
