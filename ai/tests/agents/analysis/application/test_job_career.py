from hiremate_ai.agents.analysis.application.job_career import JobFit, job_fits, job_notes, job_periods
from hiremate_ai.agents.analysis.application.types import Period, Quote
from hiremate_ai.contract import DocumentType


def period(company: str, months: int, kind: str = "EMPLOYMENT") -> Period:
    quote = Quote(document=DocumentType.RESUME, sentence=f"{company} 근무")
    return Period(company=company, role="", kind=kind, start="2020-01", end="2022-12", months=months, quote=quote)


def test_same_company_is_judged_alike() -> None:
    # 같은 회사가 이력서 · 포트폴리오에서 따로 뽑혀도 판단이 갈리지 않게, 그 회사에서 처음 답한 판단을 모두에 쓴다
    periods = [period("가 마트", 36), period("나 은행", 24), period("가마트", 36), period("다 학원", 6, "EDUCATION")]
    answers = [
        JobFit(number=1, reason="매장 재고 · 직원 관리", related="YES"),
        JobFit(number=2, reason="예금 창구 업무", related="NO"),
        JobFit(number=3, reason="다르게 답함", related="NO"),
        JobFit(number=4, reason="재직이 아닌 기간", related="YES"),
    ]

    fits = job_fits(periods, answers)

    assert {number: fit.related for number, fit in fits.items()} == {1: "YES", 2: "NO", 3: "YES"}
    assert job_periods(periods, fits) == [periods[0], periods[2], periods[3]]  # 학력 등 재직이 아닌 기간은 그대로 둔다
    [note] = job_notes(periods, fits)
    assert note.title == "경력 계산" and "나 은행 24개월(예금 창구 업무)" in note.text


def test_unanswered_periods_are_not_counted() -> None:
    periods = [period("가 마트", 36), period("나 은행", 24)]

    fits = job_fits(
        periods, [JobFit(number=1, reason="매장 관리", related="YES"), JobFit(number=9, reason="", related="YES")]
    )

    assert list(fits) == [1]  # 경력표에 없는 번호는 버리고, 답하지 않은 기간은 세지 않는다
    assert job_periods(periods, fits) == [periods[0]]
    assert job_periods(periods, None) == periods  # 판단이 없으면(옛 저장 결과) 모두 센다
