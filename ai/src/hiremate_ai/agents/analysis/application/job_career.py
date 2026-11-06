"""채용 직무와 관련된 경력 고르기. 화면의 경력 연수는 직무 관련 재직 기간만 센다.

재직 기간마다 그 기간에 맡은 일이 공고 직무와 같은 종류인지 모델이 한 번에 고르고, 개월 수는 코드가 센다.
다른 직무 경력과 판단하지 못한 기간은 경력 연수에서 빼고, 무엇을 뺐는지 담당자에게 알림으로 보인다.
모델을 부르지 못하면 모든 재직 기간을 센다 (분석을 실패로 만들지 않는다).
"""

import logging
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.career import EMPLOYMENT
from hiremate_ai.agents.analysis.application.context import readable
from hiremate_ai.agents.analysis.application.types import Note, Period
from hiremate_ai.contract import ApplicantDocument, PostingContent
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block, documents_block

log = logging.getLogger(__name__)

JOB_SYSTEM = f"""너는 지원자의 재직 기간마다 채용 직무와 관련된 경력인지 고른다. 지원자를 평가하지 않는다.
- YES: 그 기간에 본인이 맡은 일의 대부분이 공고 주요 업무와 같은 종류의 일(같은 직무)이다. 쓴 기술 · 도구가
  달라도 같은 직무의 일이면 YES다.
- NO: 맡은 일이 다른 직무의 일이다. 회사의 업종이나 서비스 분야가 공고와 같다는 것만으로는 YES가 아니다.
- UNCLEAR: 서류 어디에도(이력서 · 자기소개서 · 포트폴리오) 그 기간에 맡은 일도 직함도 없어 판단할 수 없다.
  맡은 일이 한 줄이라도 적혀 있으면 UNCLEAR를 쓰지 않고 YES · NO 가운데 고른다.
- reason에는 그 기간에 맡은 일을 서류 표현으로 짧게 쓴다 (20자 안팎).

{UNTRUSTED_RULE}"""


class JobFit(BaseModel):
    number: int = Field(description="재직 기간 번호 (1부터)")
    reason: str
    related: Literal["YES", "NO", "UNCLEAR"]


class JobCareer(BaseModel):
    periods: list[JobFit]


async def job_related(
    llm: LlmClient, periods: Sequence[Period], posting: PostingContent, documents: Sequence[ApplicantDocument]
) -> dict[int, JobFit] | None:
    """재직 기간 번호(periods 안의 위치, 1부터) → 직무 관련 판단. 재직 기간이 없으면 묻지 않고, 실패하면 None이다.

    같은 회사가 여러 문서에서 따로 뽑혀도 한 번만 묻고, 그 회사의 기간 모두에 같은 판단을 쓴다 (판단이 갈리지 않게).
    """
    companies: dict[str, list[int]] = {}
    for number, period in enumerate(periods, start=1):
        if period.kind == EMPLOYMENT:
            companies.setdefault(_company_key(period.company), []).append(number)
    usable = readable(documents)
    if not companies or not usable:
        return {}
    groups = list(companies.values())
    listing = "\n".join(
        f"{index}. {_line([periods[number - 1] for number in group])}" for index, group in enumerate(groups, start=1)
    )
    user = (
        f"채용 직무: {posting.title} ({posting.job_category})\n"
        "공고 주요 업무:\n" + data_block("duties", "\n".join(posting.duties) or "(없음)") + "\n\n"
        "재직 기간:\n" + data_block("periods", listing) + "\n\n"
        "서류:\n" + documents_block(usable)
    )
    try:
        answer = await ask(llm, JobCareer, system=JOB_SYSTEM, user=user)
    except Exception:  # 판단하지 못하면 모든 재직 기간을 센다
        log.warning("직무 관련 경력을 고르지 못해 모든 재직 기간을 센다", exc_info=True)
        return None
    by_index = {fit.number: fit for fit in answer.periods}
    return {
        number: by_index[index] for index, group in enumerate(groups, start=1) if index in by_index for number in group
    }


def job_periods(periods: Sequence[Period], fits: dict[int, JobFit] | None) -> list[Period]:
    """경력으로 셀 기간만 남긴 목록. 재직 기간은 직무 관련(YES)인 것만 남기고, 학력 · 프로젝트 같은 다른 기간은 그대로
    둔다 (신입 판단에 쓴다). 판단이 없으면(실패) 모두 남긴다."""
    if fits is None:
        return list(periods)
    return [
        period
        for number, period in enumerate(periods, start=1)
        if period.kind != EMPLOYMENT or ((fit := fits.get(number)) is not None and fit.related == "YES")
    ]


def job_notes(periods: Sequence[Period], fits: dict[int, JobFit] | None) -> list[Note]:
    """경력 연수에서 뺀 재직 기간 알림: 다른 직무 경력, 직무를 판단하지 못한 기간. 같은 회사는 한 번만 알린다."""
    if not fits:
        return []
    notes: list[Note] = []
    for related, title, lead in (
        ("NO", "경력 계산", "다른 직무 경력이라 경력 연수에서 뺐어요"),
        ("UNCLEAR", "경력 확인", "맡은 일을 서류로 확인하지 못해 경력 연수에서 뺐어요"),
    ):
        chosen = list(
            {
                _company_key(periods[number - 1].company): (periods[number - 1], fit)
                for number, fit in fits.items()
                if fit.related == related and number <= len(periods)
            }.values()
        )
        if chosen:
            listing = ", ".join(f"{period.company} {period.months}개월({fit.reason})" for period, fit in chosen)
            notes.append(Note(text=f"{lead}: {listing}", source=chosen[0][0].quote.document.label, title=title))
    return notes


def _company_key(company: str) -> str:
    return "".join(company.split()).lower()


def _line(periods: Sequence[Period]) -> str:
    """같은 회사의 기간들을 한 줄로: 회사 | 직함들 | 기간들."""
    roles = " / ".join(dict.fromkeys(period.role for period in periods if period.role)) or "직함 없음"
    spans = ", ".join(dict.fromkeys(f"{period.start} ~ {period.end or '재직 중'}" for period in periods))
    return f"{periods[0].company} | {roles} | {spans}"
