"""Assessment 부분: 자격요건과 우대사항(NCS 평가 조건)을 판정한다.

모델은 조건마다 판정과 근거 문장만 낸다. 가중치는 프롬프트에 넣지 않고, 점수는 score.py가 계산한다.
근거 문장은 코드가 원문에서 확인하고, 원문에 없으면 그 판정을 근거 없음으로 낮춘다 (아키텍처 규칙 7).
"""

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.context import career_table, evidence_text, terms
from hiremate_ai.agents.analysis.application.extract import quotes_in
from hiremate_ai.agents.analysis.application.ncs import criteria_of
from hiremate_ai.agents.analysis.application.types import (
    CriterionResult,
    Fact,
    Level,
    Period,
    QualificationResult,
)
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.contract import ApplicantDocument
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block
from hiremate_ai.tools.ncs import NcsUnit

SHORTFALL_LENGTH = 12
# "경력 3년 이상" 같은 기간 요건. 기간은 모델이 아니라 코드가 경력표로 확인한다
_CAREER_YEARS = re.compile(r"경력\s*(\d+)\s*년")
_CAREER_SPAN = re.compile(r"(?<=경력)\s*\d+\s*년\s*(이상)?")

QUALIFY_SYSTEM = f"""너는 지원 서류가 공고의 자격요건을 채우는지 판정한다. 점수는 매기지 않는다.

- 자격요건마다 MET 또는 NOT_MET을 낸다. 서류에 근거가 없으면 NOT_MET이다. 추측으로 MET을 주지 않는다.
- MET이면 근거 문장(evidence)을 원문 글자 그대로 옮긴다.
- 요건의 '등'과 나열은 예시다. 같은 종류면 채운 것이다 (MySQL · PostgreSQL 등 RDBMS라면 Oracle도 RDBMS다).
- 'N년 이상' 같은 기간은 코드가 경력표로 따로 확인한다. 너는 그 경력이 요건의 직무 · 기술에 해당하는지만 본다.
  인턴, 교육 · 개인 프로젝트는 실무 경력이 아니다.
- NOT_MET이면 shortfall에 서류에서 확인되지 않은 것을 요건의 낱말로 아주 짧게 쓴다 (12자 이내, '○○ 근거 없음' 꼴).
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 판단에 쓰지 않는다.

{UNTRUSTED_RULE}"""

PREFER_SYSTEM = f"""너는 지원 서류를 우대사항 하나의 NCS 평가 조건에 대조한다. 점수와 가중치는 다루지 않는다.

- 평가 조건마다 MET 또는 NONE을 낸다.
  MET: 서류(이력서, 자기소개서, 포트폴리오)에 그 평가 조건의 일을 실제로 한 기록이 있다. 일부만 드러나도
  그 조건의 일을 했다면 MET이다. 팀 프로젝트여도 지원자가 그 일에 참여했다고 적었으면 MET이다.
  NONE: 기록이 없다.
- 평가 조건 문장은 NCS 수행준거라 '~할 수 있다'로 끝난다. 서류와 표현이 달라도 같은 일을 했으면 MET이다.
- MET이면 근거 문장(evidence)을 원문 글자 그대로 옮긴다. 옮길 문장이 없으면 NONE이다.
- 한 문장이 여러 평가 조건의 일을 함께 보여 주면 그 조건마다 근거로 쓴다
  (예: '빌드 · 배포 파이프라인을 구성하고 실패하면 이전 버전으로 되돌리는 절차를 만들었다'는 빌드 실행, 배포,
  복원의 근거다). 다만 문장에 없는 일까지 넓혀 읽지 않는다.

{UNTRUSTED_RULE}"""


class QualificationVerdict(BaseModel):
    number: int = Field(description="자격요건 번호 (Q1이면 1)")
    verdict: Literal["MET", "NOT_MET"]
    reason: str = Field(description="판정 이유 한 문장")
    evidence: list[str] = Field(default=[], description="MET의 근거 문장. 원문 글자 그대로")
    shortfall: str = Field(default="", description="NOT_MET이면 이름 옆에 붙일 아주 짧은 표시")


class QualificationJudgement(BaseModel):
    verdicts: list[QualificationVerdict]


class CriterionVerdict(BaseModel):
    number: int = Field(description="평가 조건 번호 (C1이면 1)")
    level: Literal["MET", "NONE"]
    reason: str = Field(description="판정 이유 한 문장")
    evidence: list[str] = Field(default=[], description="근거 문장. 원문 글자 그대로")


class PreferenceJudgement(BaseModel):
    criteria: list[CriterionVerdict]


@dataclass(frozen=True)
class PreferenceTask:
    """판정할 우대사항 하나. unit이 없으면(가중치 · NCS 기준 없음) 판정하지 않는다."""

    number: int
    text: str
    weight: int | None
    unit: NcsUnit | None


async def judge_qualifications(
    llm: LlmClient,
    qualifications: Sequence[str],
    documents: Sequence[ApplicantDocument],
    facts: Sequence[Fact],
    periods: Sequence[Period],
    career_years: int,
    certificates: str | None,
    full_text_chars: int,
) -> list[QualificationResult]:
    """자격요건을 한 번에 판정한다. 차별 조건이 든 요건은 평가하지 않는다 (아키텍처 규칙 6).

    'N년 이상' 기간은 코드가 계산한 경력 연수(career_years)로 확인한다. 모델은 기간을 자주 잘못 읽는다.
    """
    targets = [(number, text) for number, text in enumerate(qualifications, start=1) if not blocked_attribute(text)]
    skipped = [
        QualificationResult(
            number=number,
            text=text,
            met=False,
            evaluated=False,
            reason="채용 판단에 쓰면 안 되는 조건이라 평가하지 않았다",
        )
        for number, text in enumerate(qualifications, start=1)
        if blocked_attribute(text)
    ]
    if not targets:
        return skipped
    # 기간 조건은 모델에게 보이지 않는다. 경력표의 개월 수를 줘도 기간을 잘못 읽어 충족을 뺐다
    listing = "\n".join(f"Q{number}. {_CAREER_SPAN.sub('', text)}" for number, text in targets)
    user = "\n\n".join(
        [
            f"자격요건:\n{listing}",
            "경력표 (코드가 계산한 개월 수):\n" + data_block("career", career_table(periods)),
            "제출한 자격증:\n" + data_block("certificates", certificates or "(없음)"),
            "서류:\n" + evidence_text(documents, facts, terms(qualifications), full_text_chars),
            "자격요건마다 판정해 줘.",
        ]
    )
    answer = await ask(llm, QualificationJudgement, system=QUALIFY_SYSTEM, user=user)
    verdicts = {verdict.number: verdict for verdict in answer.verdicts}
    results = []
    for number, text in targets:
        verdict = verdicts.get(number)
        quotes = quotes_in(documents, verdict.evidence) if verdict else []
        met = verdict is not None and verdict.verdict == "MET" and bool(quotes)
        shortfall = None
        if not met:
            shortfall = short_label(verdict.shortfall if verdict else "")
        reason = verdict.reason if verdict else "판정을 받지 못했다"
        if verdict is not None and verdict.verdict == "MET" and not quotes:
            reason = "충족했다는 근거 문장을 원문에서 찾지 못했다"
        required = _CAREER_YEARS.search(text)
        if required and career_years < int(required.group(1)):
            met = False
            shortfall = "신입" if career_years == 0 else f"경력 {career_years}년"
            reason = f"경력표 기준 재직 경력 {career_years}년 (요건 {required.group(1)}년 이상)"
        results.append(
            QualificationResult(number=number, text=text, met=met, shortfall=shortfall, reason=reason, quotes=quotes)
        )
    return sorted([*results, *skipped], key=lambda result: result.number)


def short_label(text: str) -> str:
    """이름 옆 ✕ 표시. 12자를 넘으면 '근거 없음' 꼬리를 떼고, 그래도 길면 낱말 단위로 자른다."""
    label = " ".join(text.split())
    if len(label) > SHORTFALL_LENGTH:
        label = re.sub(r"\s*(근거\s*)?없음$", "", label)
    while len(label) > SHORTFALL_LENGTH and " " in label:
        label = label.rsplit(" ", 1)[0]
    return label[:SHORTFALL_LENGTH] or "근거 없음"


async def judge_preferences(
    llm: LlmClient,
    tasks: Sequence[PreferenceTask],
    documents: Sequence[ApplicantDocument],
    facts: Sequence[Fact],
    full_text_chars: int,
    concurrency: int,
) -> dict[int, list[CriterionResult]]:
    """우대사항마다 한 번씩 동시에 판정한다. NCS 기준이 없는 우대사항은 결과에 넣지 않는다."""
    gate = asyncio.Semaphore(concurrency)

    async def one(task: PreferenceTask) -> tuple[int, list[CriterionResult]]:
        async with gate:
            return task.number, await judge_preference(llm, task, documents, facts, full_text_chars)

    rated = [task for task in tasks if task.unit is not None]
    return dict(await asyncio.gather(*(one(task) for task in rated)))


async def judge_preference(
    llm: LlmClient,
    task: PreferenceTask,
    documents: Sequence[ApplicantDocument],
    facts: Sequence[Fact],
    full_text_chars: int,
) -> list[CriterionResult]:
    """우대사항 하나를 평가 조건마다 0(NONE) · 1(MET)로 판정한다."""
    unit = task.unit
    if unit is None:
        return []
    criteria = criteria_of(unit)
    listing = "\n".join(
        f"C{number}. [{criterion.no} {criterion.element}] {criterion.text}"
        for number, criterion in enumerate(criteria, start=1)
    )
    words = terms([task.text, *(criterion.text for criterion in criteria)])
    parts = [
        f"우대사항: {task.text}",
        f"NCS 능력단위: {unit.name} ({unit.code})\n{unit.definition}",
        f"평가 조건:\n{listing}",
        "서류:\n" + evidence_text(documents, facts, words, full_text_chars),
        "평가 조건마다 판정해 줘.",
    ]
    answer = await ask(llm, PreferenceJudgement, system=PREFER_SYSTEM, user="\n\n".join(parts))
    verdicts = {verdict.number: verdict for verdict in answer.criteria}
    results = []
    for number, criterion in enumerate(criteria, start=1):
        verdict = verdicts.get(number)
        quotes = quotes_in(documents, verdict.evidence) if verdict else []
        level = Level(verdict.level) if verdict else Level.NONE
        reason = verdict.reason if verdict else "판정을 받지 못했다"
        if level != Level.NONE and not quotes:
            level, reason = Level.NONE, "근거 문장을 원문에서 찾지 못했다"
        results.append(
            CriterionResult(
                number=number,
                content_no=criterion.no,
                content=criterion.text,
                level=level,
                reason=reason,
                quotes=quotes if level != Level.NONE else [],
            )
        )
    return results
