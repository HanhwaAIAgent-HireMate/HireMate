from uuid import uuid4

from hiremate_ai.agents.analysis.application.job_career import (
    JobCareer,
    JobFit,
    job_notes,
    job_periods,
    job_related,
)
from hiremate_ai.agents.analysis.application.types import Period, Quote
from hiremate_ai.contract import ApplicantDocument, DocumentType, PostingContent
from hiremate_ai.llm.fake import FakeLlm

# 직무 이름에 기대지 않는지 매장 운영 공고로 확인한다
POSTING = PostingContent(
    title="매장 운영 담당",
    job_category="유통",
    employment_type="정규직",
    career="경력 무관",
    location="서울",
    intro="",
    duties=["매장 재고 관리", "직원 교육"],
    qualifications=[],
    preferred=[],
    benefits=[],
)
RESUME = ApplicantDocument(
    type=DocumentType.RESUME, file_id=uuid4(), file_name="", size=1, text="가 마트 점장 2020.01 ~ 2022.12\n나 은행 창구"
)


def period(company: str, months: int, kind: str = "EMPLOYMENT") -> Period:
    quote = Quote(document=DocumentType.RESUME, sentence=f"{company} 근무")
    return Period(company=company, role="", kind=kind, start="2020-01", end="2022-12", months=months, quote=quote)


async def test_same_company_is_asked_once_and_judged_alike() -> None:
    # 같은 회사가 이력서 · 포트폴리오에서 따로 뽑혀도 판단이 갈리지 않게 한 번만 묻는다
    periods = [period("가 마트", 36), period("나 은행", 24), period("가마트", 36), period("다 학원", 6, "EDUCATION")]
    answer = JobCareer(
        periods=[
            JobFit(number=1, reason="매장 재고 · 직원 관리", related="YES"),
            JobFit(number=2, reason="예금 창구 업무", related="NO"),
        ]
    )
    llm = FakeLlm(answer)

    fits = await job_related(llm, periods, POSTING, [RESUME])

    assert fits is not None
    listing = llm.calls[0].user.split('<data kind="periods">')[1].split("</data>")[0]
    assert listing.strip().splitlines() == [
        "1. 가 마트 | 직함 없음 | 2020-01 ~ 2022-12",
        "2. 나 은행 | 직함 없음 | 2020-01 ~ 2022-12",
    ]
    assert {number: fit.related for number, fit in fits.items()} == {1: "YES", 2: "NO", 3: "YES"}
    assert job_periods(periods, fits) == [periods[0], periods[2], periods[3]]  # 학력 등 재직이 아닌 기간은 그대로 둔다
    [note] = job_notes(periods, fits)
    assert note.title == "경력 계산" and "나 은행 24개월(예금 창구 업무)" in note.text


async def test_failed_call_counts_every_period() -> None:
    periods = [period("가 마트", 36)]

    fits = await job_related(FakeLlm(), periods, POSTING, [RESUME])  # 응답이 없어 판단하지 못한다

    assert fits is None
    assert job_periods(periods, fits) == periods
    assert job_notes(periods, fits) == []
