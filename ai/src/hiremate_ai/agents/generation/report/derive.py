"""부품이 그리는 값 중 묶음 값을 세어 만드는 것 (교차 인원, 그룹 비율, 전형 안 위치).

화면 · PDF와 문장 검사가 같은 계산을 쓴다. 문장에 이 숫자를 쓰면 check.py가 여기서 다시 계산해 맞춰 본다.
"""

from collections import Counter
from dataclasses import dataclass

from hiremate_ai.agents.generation.report.bundle import ReportBundle, ReportKind

POSITIVE = frozenset({"MET", "YES", "PASS", "CONFIRMED", "RECOMMENDED"})
"""있음 · 충족으로 세는 판정 값."""
HAVE = frozenset({"YES", "NO"})
"""있음 · 없음 key의 값."""


def values_of(bundle: ReportBundle, key: str) -> dict[str, float | str]:
    return {fact.applicant: fact.value for fact in bundle.facts if fact.key == key}


def cross_counts(bundle: ReportBundle, row_key: str, col_key: str) -> Counter[tuple[str, str]]:
    """두 판정 key의 (행 값, 열 값)별 인원. 두 값이 다 있는 지원자만 센다."""
    rows, cols = values_of(bundle, row_key), values_of(bundle, col_key)
    return Counter((str(rows[number]), str(cols[number])) for number in rows if number in cols)


def share_percents(
    bundle: ReportBundle, keys: list[str], group_key: str, group_value: str
) -> dict[str, tuple[int, int]]:
    """key별 (그룹 비율 %, 전체 비율 %). 있음 · 충족(POSITIVE) 지원자의 비율이다."""
    everyone = [applicant.number for applicant in bundle.applicants]
    groups = values_of(bundle, group_key)
    group = [number for number in everyone if groups.get(number) == group_value]
    result = {}
    for key in keys:
        values = values_of(bundle, key)
        result[key] = (_percent(values, group), _percent(values, everyone))
    return result


def scope_of(bundle: ReportBundle) -> list[str]:
    """부품이 그리는 지원자 범위. 비교면 비교 대상, 아니면 전형 전체다."""
    if bundle.kind is ReportKind.COMPARE:
        return list(bundle.targets)
    return [applicant.number for applicant in bundle.applicants]


def tally(bundle: ReportBundle, key: str, people: list[str]) -> tuple[Counter[str], int]:
    """판정 key의 값별 인원과 충족 · 있음 비율(%)."""
    values = values_of(bundle, key)
    counts = Counter(str(values[number]) for number in people if number in values)
    total = sum(counts.values())
    met = sum(count for value, count in counts.items() if value in POSITIVE)
    return counts, round(100 * met / total) if total else 0


def ring_percent(bundle: ReportBundle, keys: list[str], applicant: str) -> tuple[int, str] | None:
    """관점 도넛의 비율(%)과 아래 글. 숫자 key 하나면 점수 / 만점, 판정 key면 충족 · 있음 항목 비율이다."""
    facts = {fact.key: fact for fact in bundle.facts if fact.applicant == applicant and fact.key in keys}
    if len(facts) != len(keys):
        return None
    if len(keys) == 1 and isinstance(facts[keys[0]].value, float | int):
        fact = facts[keys[0]]
        if not fact.max or not isinstance(fact.value, float | int):
            return None
        return round(100 * fact.value / fact.max), f"{fact.value:g}/{fact.max:g}점"
    if any(isinstance(fact.value, float | int) for fact in facts.values()):
        return None
    met = sum(1 for fact in facts.values() if fact.value in POSITIVE)
    return round(100 * met / len(keys)), f"충족 {met}/{len(keys)}"


def score_view(bundle: ReportBundle, keys: list[str]) -> bool:
    """영역 점수처럼 만점이 있는 숫자 key 하나인 관점인가. 점수가 빈(보류) 지원자가 있어도 그린다."""
    return len(keys) == 1 and any(
        fact.key == keys[0] and isinstance(fact.value, float | int) and fact.max for fact in bundle.facts
    )


def top_percent(bundle: ReportBundle, key: str, applicant: str) -> int | None:
    """전형 전체에서 그 지원자 값이 상위 몇 %인지. 같은 값은 같은 위치다."""
    values = [value for value in values_of(bundle, key).values() if isinstance(value, float | int)]
    mine = values_of(bundle, key).get(applicant)
    if not isinstance(mine, float | int) or not values:
        return None
    above = sum(1 for value in values if value > mine)
    return max(1, round(100 * (above + 1) / len(values)))


def _percent(values: dict[str, float | str], people: list[str]) -> int:
    if not people:
        return 0
    return round(100 * sum(1 for number in people if values.get(number) in POSITIVE) / len(people))


@dataclass(frozen=True)
class Drawable:
    """영역 밖에서 바로 그릴 수 있는 자료. 전형 · 최종 리포트는 이 자료를 부품으로 그려야 한다."""

    flags: dict[str, frozenset[str]]
    """두 갈래 판정 key와 그 값 (예: document.ai_pick의 RECOMMENDED · NOT_RECOMMENDED). cross · distribution split"""
    families: dict[str, list[str]]
    """있음 · 없음 key 묶음 (예: document.skill → key 6개). share"""
    groups: dict[str, list[str]]
    """조각 지표 group과 지표 id. donut · composition"""


def drawable(bundle: ReportBundle) -> Drawable:
    in_areas = {key for area in bundle.areas for key in area.keys}
    values: dict[str, set[str]] = {}
    for fact in bundle.facts:
        if isinstance(fact.value, str) and fact.key not in in_areas:
            values.setdefault(fact.key, set()).add(fact.value)
    two_way = {key: frozenset(found) for key, found in values.items() if len(found) == 2}
    families: dict[str, list[str]] = {}
    for key, found in two_way.items():
        if found <= HAVE:
            families.setdefault(key.rsplit(".", 1)[0], []).append(key)
    groups: dict[str, list[str]] = {}
    for metric in bundle.metrics:
        if metric.group:
            groups.setdefault(metric.group, []).append(metric.id)
    return Drawable(
        flags={key: found for key, found in two_way.items() if not found <= HAVE},
        families={prefix: keys for prefix, keys in families.items() if len(keys) > 1},
        groups=groups,
    )
