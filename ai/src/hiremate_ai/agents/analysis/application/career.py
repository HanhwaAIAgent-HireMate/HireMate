"""경력 기간 → 경력 연수 · 마지막 회사. 모델이 날짜를 계산하지 않게 코드가 한다.

정규 · 계약 재직(EMPLOYMENT)만 경력으로 센다. 인턴, 교육 · 개인 프로젝트는 세지 않는다 (가상 지원자 이도윤).
겹치는 기간은 한 번만 센다. 재직 중이면 분석한 날까지다.
"""

import re
from collections.abc import Sequence
from datetime import date

from hiremate_ai.agents.analysis.application.types import Period

EMPLOYMENT = "EMPLOYMENT"
_MONTH = re.compile(r"((?:19|20)\d{2})\s*[-./년]\s*(\d{1,2})")


def month_index(text: str) -> int | None:
    """'2022-03', '2022.03', '2022년 3월'을 달 번호로 바꾼다. 읽지 못하면 None."""
    found = _MONTH.search(text)
    if not found:
        return None
    month = int(found.group(2))
    if not 1 <= month <= 12:
        return None
    return int(found.group(1)) * 12 + month - 1


def months_between(start: str, end: str | None, today: date) -> int | None:
    begin = month_index(start)
    finish = month_index(end) if end else today.year * 12 + today.month - 1
    if begin is None or finish is None or finish < begin:
        return None
    # 시작 달과 끝 달을 모두 센다 (2024.05 ~ 2025.04는 12개월)
    return finish - begin + 1


def career_years(periods: Sequence[Period], today: date) -> int:
    """재직 기간의 합(겹침은 한 번, 시작 달과 끝 달 포함)을 연 단위로 내린 값. 재직 기간이 없으면 0(신입)이다."""
    spans = []
    current = today.year * 12 + today.month - 1
    for period in periods:
        if period.kind != EMPLOYMENT:
            continue
        begin = month_index(period.start)
        finish = month_index(period.end) if period.end else current
        if begin is not None and finish is not None and finish >= begin:
            spans.append((begin, finish + 1))
    total, reach = 0, -1
    for begin, finish in sorted(spans):
        if finish <= reach:
            continue
        total += finish - max(begin, reach)
        reach = finish
    return total // 12


def last_company(periods: Sequence[Period]) -> str | None:
    """재직 중인 회사, 없으면 가장 늦게 끝난 회사."""
    jobs = [period for period in periods if period.kind == EMPLOYMENT and month_index(period.start) is not None]
    if not jobs:
        return None
    current = [period for period in jobs if period.end is None]
    if current:
        return max(current, key=lambda period: month_index(period.start) or 0).company
    return max(jobs, key=lambda period: month_index(period.end or "") or 0).company
