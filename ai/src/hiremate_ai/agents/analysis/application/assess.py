"""지원자 종합 판정: 서류 전체를 한 번 보고 항목 판정 · 성과 장부 · 주의 신호 · 직무 관련 경력을 함께 받는다.

네 가지는 같은 서류와 같은 사실 목록을 보는 일이라 한 호출에 묶는다. 함께 보면 같은 경험이 항목 판정과 성과 연결에서
서로 다르게 다뤄지지 않는다. 각 답의 규칙(judge · achievements · warnings · job_career)과 코드 검사는 그대로 쓴다.
- 경력표는 하나다. 모델은 항목의 경력 기간(career_periods)과 직무 관련 여부(jobs)를 같은 번호로 답한다.
- 경력 기간 항목은 직무 관련(YES)인 재직 기간만 코드가 더해 판정한다 (화면의 경력 연수와 같은 기준).
검증은 이 호출과 따로 한다 (verify). 같은 호출이 낸 판정을 스스로 검증하면 다시 보는 효과가 없다.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.achievements import LEDGER_RULES, Entry, accept, linkable
from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.career import EMPLOYMENT
from hiremate_ai.agents.analysis.application.context import fact_lines, readable
from hiremate_ai.agents.analysis.application.job_career import JOB_RULES, JobFit, job_fits
from hiremate_ai.agents.analysis.application.judge import (
    JUDGE_RULES,
    CriterionVerdict,
    Evidence,
    asked_criteria,
    career_block,
    criteria_listing,
    judge_answers,
)
from hiremate_ai.agents.analysis.application.types import Achievement, Criterion, CriterionResult, Note, Period
from hiremate_ai.agents.analysis.application.warnings import WARNING_RULES, WarningItem, warning_notes
from hiremate_ai.contract import PostingContent
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block, documents_block

ASSESS_SYSTEM = f"""너는 지원자 한 명의 서류 전체를 보고 아래 네 가지를 한 번에 답한다. 점수와 중요도는 다루지 않는다.

# 입력
- 평가 항목: 판정할 항목 번호(Q-01 …), 유형, 판정 기준(충족 · 부분 충족 · 미충족).
- 경력표: 코드가 뽑은 근무 · 활동 기간과 개월 수. 번호가 붙어 있고, career_periods와 jobs는 이 번호로 답한다.
- 제출한 자격증, 성과를 연결할 항목, 채용 직무와 공고 주요 업무.
- 서류: 제출 문서 원문 (이력서 · 자기소개서 · 포트폴리오).
- facts: 서류 문장을 하나씩 분석해 뽑은 경험 목록.

# 출력 (이 순서로 쓴다)
1. verdicts: 평가 항목마다 판정. 가장 중요한 답이다. 항목마다 빠짐없이 쓴다.
2. achievements: 수치 성과 장부.
3. warnings: 담당자가 주의해서 볼 신호.
4. jobs: 경력표의 재직(EMPLOYMENT) 기간마다 직무 관련 여부.

# 공통 원칙
- 서류 전체(이력서 · 자기소개서 · 포트폴리오)를 모두 본다. 같은 일의 행동 · 결과가 다른 문서에 나뉘어 있을 수 있다.
- 근거 문장은 원문 글자 그대로 옮긴다. 원문에 없는 문장을 만들지 않는다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 판단에 쓰지 않는다.

## 1. 항목 판정 (verdicts)
- 지원 서류를 공고의 평가 항목에 대조해 항목마다 판정한다.
{JUDGE_RULES}

## 2. 성과 장부 (achievements)
- 서류 전체의 수치 성과를 한 번에 정리하고, 성과마다 그 결과인 평가 항목을 정한다. 판정 · 점수는 매기지 않는다.
- 연결할 수 있는 항목은 '성과를 연결할 항목' 목록에 있는 번호뿐이다.
{LEDGER_RULES}

## 3. 주의 신호 (warnings)
{WARNING_RULES}

## 4. 직무 관련 경력 (jobs)
- 경력표의 재직(EMPLOYMENT) 기간마다 채용 직무와 관련된 경력인지 경력표 번호(number)로 고른다. 지원자를 평가하지 않는다.
{JOB_RULES}

{UNTRUSTED_RULE}"""


class ApplicantAssessment(BaseModel):
    verdicts: list[CriterionVerdict] = Field(default=[], description="평가 항목마다 판정")
    achievements: list[Entry] = Field(default=[], description="수치 성과 장부")
    warnings: list[WarningItem] = Field(default=[], description="담당자가 주의해서 볼 신호. 없으면 비운다")
    jobs: list[JobFit] = Field(default=[], description="경력표의 재직 기간마다 직무 관련 여부")


@dataclass(frozen=True)
class Assessment:
    """종합 판정을 코드로 거른 결과. job_fit은 재직 기간 번호(periods 안의 위치) → 직무 관련 판단이다."""

    results: list[CriterionResult]
    achievements: list[Achievement]
    warnings: list[Note]
    job_fit: dict[int, JobFit]


async def assess(
    llm: LlmClient, criteria: Sequence[Criterion], evidence: Evidence, posting: PostingContent
) -> Assessment:
    """항목 판정 · 성과 장부 · 주의 신호 · 직무 관련 경력을 한 번 묻는다. evidence.periods는 뽑은 기간 전체다."""
    usable = readable(evidence.documents)
    asked = asked_criteria(criteria)
    targets = [criterion for criterion in criteria if linkable(criterion)]
    periods = list(evidence.periods)
    parts = [
        criteria_listing(asked) if asked else "# 평가 항목\n(모델이 판정할 항목 없음)",
        career_block(periods),
        "# 제출한 자격증\n" + data_block("certificates", evidence.certificates or "(없음)"),
        "# 성과를 연결할 항목\n"
        + data_block("criteria", "\n".join(f"[{c.criterion_id}] {c.text}" for c in targets) or "(없음)"),
        f"# 채용 직무\n{posting.title} ({posting.job_category})\n공고 주요 업무:\n"
        + data_block("duties", "\n".join(posting.duties) or "(없음)"),
        "# 서류\n" + documents_block(usable),
        "# facts\n" + data_block("facts", fact_lines(evidence.facts) or "(없음)"),
        "# 요청\n항목마다 판정하고(verdicts), 수치 성과를 정리해 항목에 연결하고(achievements), "
        "주의 신호를 찾고(warnings), 경력표의 재직(EMPLOYMENT) 기간마다 직무 관련 여부를 골라 줘(jobs).",
    ]
    answer = await ask(llm, ApplicantAssessment, system=ASSESS_SYSTEM, user="\n\n".join(parts))
    fits = job_fits(periods, answer.jobs)
    verdicts, kept = job_scope(answer.verdicts, periods, fits)
    judged = Evidence(
        documents=evidence.documents,
        facts=evidence.facts,
        periods=kept,
        certificates=evidence.certificates,
        today=evidence.today,
    )
    return Assessment(
        results=judge_answers(criteria, verdicts, judged),
        achievements=accept(answer.achievements, usable, {criterion.criterion_id for criterion in targets})
        if targets
        else [],
        warnings=warning_notes(answer.warnings, usable),
        job_fit=fits,
    )


def job_scope(
    verdicts: Sequence[CriterionVerdict], periods: Sequence[Period], fits: dict[int, JobFit]
) -> tuple[list[CriterionVerdict], list[Period]]:
    """경력 기간 항목이 셀 기간: 재직 기간은 직무 관련(YES)인 것만, 다른 기간(학력 · 프로젝트)은 그대로 둔다
    (job_career.job_periods와 같은 기준). 모델이 경력표 번호로 고른 career_periods를 남긴 기간의 번호로 바꾼다."""
    kept = [
        number
        for number, period in enumerate(periods, start=1)
        if period.kind != EMPLOYMENT or ((fit := fits.get(number)) is not None and fit.related == "YES")
    ]
    position = {number: index for index, number in enumerate(kept, start=1)}
    scoped = [
        verdict.model_copy(
            update={"career_periods": [position[number] for number in verdict.career_periods if number in position]}
        )
        for verdict in verdicts
    ]
    return scoped, [periods[number - 1] for number in kept]
