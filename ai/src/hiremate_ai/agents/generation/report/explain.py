"""서류 전형 분포 해설. backend가 코드로 센 분포(지원자 이름 없이 숫자와 항목 글만)를 받아, 담당자가 무엇을 먼저
볼지 두세 문장으로 해석한다. 모델 호출은 한 번(structured)이고, 숫자는 받은 자료에 있는 값만 쓴다.

문장은 리포트 설계서와 같은 검사(차별 조건, 순위 · 추천 표현, 합니다체, 자료에 없는 숫자)를 거치고, 걸린 문장은 버린다.
합격 · 불합격이나 누구를 뽑을지는 쓰지 않는다. 해설을 만들지 못하면 빈 목록을 돌려주고 화면은 숫자 요약만 보여 준다.
"""

import logging
import re

from openai import APIError
from pydantic import BaseModel, Field

from hiremate_ai.agents.generation.report.check import sentence_problems
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import data_block

logger = logging.getLogger(__name__)

AGENT = "report-distribution"
MAX_LINES = 3
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


class RequiredCount(ContractModel):
    met: int
    unmet: int
    unknown: int


class CriterionCount(ContractModel):
    criterion_id: str
    text: str
    required: bool
    met: int
    partial: int
    not_met: int
    unknown: int


class GroupCount(ContractModel):
    label: str
    reason: str
    size: int


class CareerCount(ContractModel):
    label: str
    all: int
    above_line: int


class CountBucket(ContractModel):
    value: int
    count: int


class DistributionFacts(ContractModel):
    """backend ReportDistribution.forAi(). 경계 그룹은 인원만 있고 지원자는 없다.

    counts는 선 위 지원자의 충족 개수별 인원, cut은 목표 인원 자리에서 개수가 같은 구간(value · from · to · inside)이다.
    """

    total: int
    analyzed: int
    above_line: int
    target: int
    passed: int | None = None
    required: RequiredCount
    criteria: list[CriterionCount]
    groups: list[GroupCount]
    careers: list[CareerCount]
    counts: list[CountBucket] = []
    cut: dict[str, int] | None = None


CHARTS = ("funnel", "required", "counts", "criteria", "careers")
"""화면 분포 차트. 서류 통과까지 남는 인원 · 필수 조건 충족 현황 · 선 위 충족 개수 · 항목별 판정 · 경력 구간이다."""


class DistributionNote(ContractModel):
    """분포 해설. lines는 전체 해설, charts는 차트(CHARTS)마다 그 차트에서 읽을 점 한 문장이다.
    검사를 통과한 문장만 남고, 만들지 못한 차트는 빠진다."""

    lines: list[str]
    charts: dict[str, str] = {}


class _Charts(BaseModel):
    funnel: str = Field(description="서류 통과까지 남는 인원(전체 → 분석 완료 → 선 위 → 목표) 차트에서 읽을 점 한 문장")
    required: str = Field(description="필수 조건 충족 현황(모두 충족 · 미충족 · 확인 필요) 차트에서 읽을 점 한 문장")
    counts: str = Field(description="선 위 지원자의 충족 개수별 인원과 목표선 차트에서 읽을 점 한 문장")
    criteria: str = Field(description="항목별 판정 차트에서 읽을 점 한 문장 (걸리는 항목, 확인 필요가 많은 항목)")
    careers: str = Field(description="경력 구간별 선 위 비율 차트에서 읽을 점 한 문장. 나이로 읽히게 쓰지 않는다")


class _Draft(BaseModel):
    lines: list[str] = Field(description="담당자가 먼저 볼 점 두세 문장. 해요체, 받은 숫자만")
    charts: _Charts = Field(description="차트마다 그 차트에서 읽을 점 한 문장")


SYSTEM = """너는 채용 담당자를 돕는 Report Agent다. 서류 전형 지원자 전원을 코드가 센 분포를 받아,
담당자가 무엇을 먼저 보면 좋을지 두세 문장(lines)으로 해석하고, 화면의 차트마다 그 차트에서 읽을 점을 한 문장씩
(charts) 쓴다. 차트 문장은 그 차트의 자료만 보고 쓴다.

- 숫자를 다시 나열하지 않는다. 숫자 사이의 관계(목표와 선 위의 차이, 많이 걸리는 필수 조건, 서류만으로 판단이
  어려운 항목, 경계 그룹을 볼 까닭)를 읽어 다음에 할 일로 이어지게 쓴다.
- 숫자는 받은 자료에 있는 값만 쓴다. 새로 계산한 숫자는 쓰지 않는다.
- 항목은 코드(Q-01)가 아니라 짧은 이름(예: Java · Kotlin 경력)으로 쓴다.
- 합격 · 불합격, 순위('가장', '제일'), 누구를 뽑으라는 말은 쓰지 않는다. 지원자 개인은 다루지 않는다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다.
- 해요체(~어요 · ~예요)로 짧게 쓴다."""


def facts_text(facts: DistributionFacts) -> str:
    """모델에게 줄 분포 자료. 비율은 코드가 미리 계산해 넣어 모델이 계산하지 않게 한다."""

    def share(part: int, whole: int) -> str:
        return f"{round(100 * part / whole)}%" if whole else "0%"

    lines = [
        f"전체 지원자 {facts.total}명, 서류 분석 완료 {facts.analyzed}명",
        f"선 위(필수 조건 모두 충족) {facts.above_line}명 (전체의 {share(facts.above_line, facts.total)})",
        f"서류 통과 목표 {facts.target}명, 선 위와 목표의 차이 {facts.above_line - facts.target}명",
    ]
    if facts.passed is not None:
        lines.append(f"담당자가 합격 처리한 인원 {facts.passed}명")
    required = facts.required
    whole = required.met + required.unmet + required.unknown
    lines.append(
        f"필수 조건: 모두 충족 {required.met}명({share(required.met, whole)}), "
        f"미충족 {required.unmet}명({share(required.unmet, whole)}), "
        f"확인 필요 {required.unknown}명({share(required.unknown, whole)})"
    )
    lines.append("항목별 판정 (충족 · 부분 · 미충족 · 확인 필요, 충족이 아닌 비율):")
    for item in facts.criteria:
        judged = item.met + item.partial + item.not_met + item.unknown
        issue = share(item.partial + item.not_met + item.unknown, judged)
        mark = " [필수]" if item.required else ""
        lines.append(
            f"- {item.criterion_id} {item.text}{mark}: {item.met} · {item.partial} · {item.not_met} · "
            f"{item.unknown}, 충족이 아닌 비율 {issue}, 확인 필요 비율 {share(item.unknown, judged)}"
        )
    if facts.counts:
        shown = ", ".join(f"{bucket.value}개 {bucket.count}명" for bucket in facts.counts)
        lines.append(f"선 위 지원자의 충족 개수별 인원: {shown}")
    if facts.cut:
        cut = facts.cut
        lines.append(
            f"목표 {facts.target}명째가 충족 {cut.get('value')}개, {cut.get('from')}~{cut.get('to')}번째가 같은 개수"
            f"(목표 안 {cut.get('inside')}명)라 개수로는 선발이 갈리지 않음"
        )
    for group in facts.groups:
        lines.append(f"경계 그룹 '{group.label}' {group.size}명: {group.reason}")
    for band in facts.careers:
        lines.append(
            f"경력 {band.label}: 전체 {band.all}명 중 선 위 {band.above_line}명({share(band.above_line, band.all)})"
        )
    return "\n".join(lines)


async def explain_distribution(facts: DistributionFacts, llm: LlmClient) -> DistributionNote:
    """분포 해설 두세 문장. 검사에 걸린 문장은 버리고, 모델이 형식을 지키지 못하면 빈 해설이다."""
    text = facts_text(facts)
    try:
        draft = await llm.structured(_Draft, agent=AGENT, system=SYSTEM, user=data_block("distribution", text))
    except LlmOutputError as error:
        logger.warning("분포 해설을 만들지 못했다 (reason=%s)", error.reason.value)
        return DistributionNote(lines=[])
    except APIError as error:
        logger.warning("모델 서버 오류로 분포 해설을 만들지 못했다 (%s)", type(error).__name__)
        return DistributionNote(lines=[])
    allowed = set(_NUMBER.findall(text))

    def passes(label: str, line: str) -> bool:
        if found := sentence_problems(label, line, allowed):
            logger.info("분포 해설 문장을 버린다: %s", " | ".join(found))
            return False
        return bool(line)

    kept = [line.strip() for index, line in enumerate(draft.lines) if passes(f"lines[{index}]", line.strip())]
    charts = {
        name: line.strip() for name in CHARTS if passes(f"charts.{name}", (line := getattr(draft.charts, name)).strip())
    }
    return DistributionNote(lines=kept[:MAX_LINES], charts=charts)
