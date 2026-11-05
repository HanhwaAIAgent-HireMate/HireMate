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


def split_keys(bundle: ReportBundle) -> list[str]:
    """비교 대상끼리 판정이 갈린 항목 판정 key. 영역 항목 순서이고, 값이 없는 대상은 빼고 본다."""
    if bundle.kind is not ReportKind.COMPARE:
        return []
    verdicts = {(fact.applicant, fact.key): fact.value for fact in bundle.facts if isinstance(fact.value, str)}
    keys = [key for area in bundle.areas for key in area.keys]
    return [key for key in keys if len({verdicts.get((number, key)) for number in bundle.targets} - {None}) > 1]


@dataclass(frozen=True)
class StageDigest:
    """최종 리포트의 전형 하나에서 합격자와 불합격자를 견준 기록. lines는 모델에게 주는 줄, numbers는 그 줄의 숫자다.
    모델은 이 숫자로 전형 해석을 쓰고, check.py는 같은 계산으로 문장의 숫자를 맞춰 본다."""

    area: str
    label: str
    lines: list[str]
    numbers: list[float]


def stage_digests(bundle: ReportBundle) -> list[StageDigest]:
    """최종 리포트 영역(전형)마다 합격 · 불합격 그룹의 항목 충족 수와 점수 범위 · 평균. 결정이 없거나 한쪽 그룹이
    비면 견줄 수 없어 뺀다. 지원자 한 명씩이 아니라 그룹 단위로만 센다."""
    if bundle.kind is not ReportKind.FINAL:
        return []
    digests = []
    for area in bundle.areas:
        decisions = values_of(bundle, f"{area.id}.decision")
        passed = [number for number, value in decisions.items() if value == "PASS"]
        failed = [number for number, value in decisions.items() if value != "PASS"]
        if not passed or not failed:
            continue
        lines: list[str] = []
        numbers: list[float] = [len(passed), len(failed)]
        for key in [area.score_key, *area.keys] if area.score_key else area.keys:
            values = values_of(bundle, key)
            label = next((fact.label for fact in bundle.facts if fact.key == key), key)
            if any(isinstance(value, float | int) for value in values.values()):
                line, found = _score_line(label, values, passed, failed)
            else:
                line, found = _verdict_line(label, values, passed, failed)
            if line:
                lines.append(line)
                numbers += found
        if lines:
            head = f"합격 {len(passed)}명, 불합격 {len(failed)}명"
            digests.append(StageDigest(area=area.id, label=area.label, lines=[head, *lines], numbers=numbers))
    return digests


def _verdict_line(
    label: str, values: dict[str, float | str], passed: list[str], failed: list[str]
) -> tuple[str | None, list[float]]:
    def met(people: list[str]) -> tuple[int, int]:
        known = [number for number in people if number in values]
        return sum(values[number] in POSITIVE for number in known), len(known)

    (pass_met, pass_n), (fail_met, fail_n) = met(passed), met(failed)
    if not pass_n or not fail_n:
        return None, []
    pass_rate, fail_rate = round(100 * pass_met / pass_n), round(100 * fail_met / fail_n)
    all_met, all_n = pass_met + fail_met, pass_n + fail_n
    line = (
        f"{label}: 합격자 {pass_n}명 중 충족 {pass_met}명({pass_rate}%), "
        f"불합격자 {fail_n}명 중 충족 {fail_met}명({fail_rate}%), 전체 {all_n}명 중 충족 {all_met}명"
    )
    return line, [pass_met, pass_n, pass_rate, fail_met, fail_n, fail_rate, all_met, all_n, abs(pass_rate - fail_rate)]


def _score_line(
    label: str, values: dict[str, float | str], passed: list[str], failed: list[str]
) -> tuple[str | None, list[float]]:
    def scores(people: list[str]) -> list[float]:
        return [float(value) for number in people if isinstance(value := values.get(number), float | int)]

    top, bottom = scores(passed), scores(failed)
    if not top or not bottom:
        return None, []
    top_mean, bottom_mean = round(sum(top) / len(top), 1), round(sum(bottom) / len(bottom), 1)
    gap = round(top_mean - bottom_mean, 1)
    edge = round(min(top) - max(bottom), 1)
    # 합격자 최저가 불합격자 최고보다 높으면 점수 구간이 나뉜 것이고, 아니면 두 그룹 점수가 겹친다
    border = f"합격자 최저가 불합격자 최고보다 {edge:g}점 높음" if edge >= 0 else f"두 그룹 점수가 {-edge:g}점 겹침"
    line = (
        f"{label}: 합격자 {_span(top)}점(평균 {top_mean:g}), "
        f"불합격자 {_span(bottom)}점(평균 {bottom_mean:g}), 평균 차이 {gap:g}점, {border}"
    )
    return line, [min(top), max(top), top_mean, min(bottom), max(bottom), bottom_mean, gap, abs(edge)]


def _span(scores: list[float]) -> str:
    low, high = min(scores), max(scores)
    return f"{low:g}" if low == high else f"{low:g}~{high:g}"
