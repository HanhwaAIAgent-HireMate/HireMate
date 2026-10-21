from datetime import date

from hiremate_ai.agents.analysis.application.career import career_years, last_company, month_index, months_between
from hiremate_ai.agents.analysis.application.types import Period, Quote
from hiremate_ai.contract import DocumentType

TODAY = date(2026, 10, 21)
QUOTE = Quote(document=DocumentType.RESUME, sentence="근무 기간")


def period(company: str, start: str, end: str | None, kind: str = "EMPLOYMENT") -> Period:
    return Period(company=company, role="", kind=kind, start=start, end=end, months=0, quote=QUOTE)


def test_month_index_reads_common_formats() -> None:
    assert month_index("2022-03") == month_index("2022.03") == month_index("2022년 3월") == 2022 * 12 + 2
    assert month_index("현재") is None
    assert months_between("2022-03", None, TODAY) == 55


def test_current_job_counts_until_today() -> None:
    # 2022.03 ~ 현재(2026.10) = 4년 7개월 → 4년 (가상 지원자 정유민)
    assert career_years([period("한빛카드", "2022-03", None)], TODAY) == 4


def test_overlapping_jobs_count_once() -> None:
    periods = [period("가", "2019-01", "2022-01"), period("나", "2021-01", "2023-01")]

    assert career_years(periods, TODAY) == 4


def test_projects_and_internships_are_not_career() -> None:
    periods = [
        period("모의 결제 서비스", "2025-03", "2025-12", kind="PROJECT"),
        period("인턴", "2024-01", "2024-12", "INTERN"),
    ]

    assert career_years(periods, TODAY) == 0
    assert last_company(periods) is None


def test_last_company_prefers_current_job() -> None:
    periods = [period("새솔은행", "2019-01", "2024-12"), period("페이온", "2025-01", None)]

    assert last_company(periods) == "페이온"
    assert last_company([period("가", "2019-01", "2020-01"), period("나", "2020-02", "2023-06")]) == "나"
