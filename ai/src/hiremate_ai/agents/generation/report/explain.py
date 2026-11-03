"""서류 전형 분포 해설. backend가 코드로 센 분포(지원자 이름 없이 숫자와 항목 글만)를 받아, 담당자가 무엇을 먼저
볼지 두세 문장으로 해석한다. 모델 호출은 한 번(structured)이고, 숫자는 받은 자료에 있는 값만 쓴다.

문장은 리포트 설계서와 같은 검사(차별 조건, 순위 · 추천 표현, 합니다체, 자료에 없는 숫자)를 거치고, 걸린 문장은 버린다.
차트마다 눈에 띄는 점(가장 높거나 낮은 값과 그 이름)은 코드가 골라 자료에 넣고, 차트 문장은 그 숫자를 하나 이상 쓴다.
숫자 없이 '확인해 보세요'로만 끝나는 차트 문장은 버리고, 버린 차트가 있으면 한 번 다시 쓰게 한다.
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
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

logger = logging.getLogger(__name__)

AGENT = "report-distribution"
MAX_LINES = 3
REWRITES = 1
"""숫자 없이 쓴 차트 문장이 있을 때 다시 쓰게 하는 횟수."""
MIN_BAND = 3
"""경력 구간의 눈에 띄는 점을 고를 때 쓰는 구간의 최소 인원."""
MIN_UNSURE_PERCENT = 10
"""확인 필요 비율을 눈에 띄는 점으로 알릴 최소 비율(%). 그보다 낮으면 모든 항목에 한두 명씩인 경우가 많다."""
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_CODE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,3}-\d+(?!\d)")
"""항목 코드(Q-01). 차트 문장에 숫자가 있는지 볼 때 뺀다."""


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
    """backend ReportDistribution.forAi(). 다시 볼 지원자 그룹은 인원만 있고 지원자는 없다.

    counts는 필수 조건 충족자의 항목 충족 수별 인원, cut은 목표 인원 자리에서 개수가 같은 구간
    (value · from · to · inside)이다.
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
"""화면 분포 차트. 서류 통과 목표까지 · 필수 조건 충족 현황 · 필수 조건 충족자의 항목 충족 수 · 항목별로 걸린 지원자 ·
경력별 필수 조건 충족 비율이다."""


class DistributionNote(ContractModel):
    """분포 해설. lines는 전체 해설, charts는 차트(CHARTS)마다 그 차트에서 읽을 점 한 문장이다.
    검사를 통과한 문장만 남고, 만들지 못한 차트는 빠진다."""

    lines: list[str]
    charts: dict[str, str] = {}


class _Charts(BaseModel):
    funnel: str = Field(
        description="지원자에서 서류 통과 목표까지(전체 → 분석 완료 → 필수 조건 충족 → 목표) 차트에서 읽을 점 한 문장"
    )
    required: str = Field(description="필수 조건 충족 현황(모두 충족 · 미충족 · 확인 필요) 차트에서 읽을 점 한 문장")
    counts: str = Field(description="필수 조건 충족자의 항목 충족 수별 인원과 목표선 차트에서 읽을 점 한 문장")
    criteria: str = Field(
        description="항목별로 걸린 지원자 차트에서 읽을 점 한 문장 (걸리는 항목, 확인 필요가 많은 항목)"
    )
    careers: str = Field(description="경력별 필수 조건 충족 비율 차트에서 읽을 점 한 문장. 나이로 읽히게 쓰지 않는다")


class _Draft(BaseModel):
    lines: list[str] = Field(description="담당자가 먼저 볼 점 두세 문장. 해요체, 받은 숫자만")
    charts: _Charts = Field(description="차트마다 그 차트에서 읽을 점 한 문장")


SYSTEM = f"""너는 채용 담당자를 돕는 Report Agent다. 서류 전형 지원자 전원을 코드가 센 분포를 받아,
담당자가 무엇을 먼저 보면 좋을지 두세 문장(lines)으로 해석하고, 화면의 차트마다 그 차트에서 읽을 점을 한 문장씩
(charts) 쓴다. 차트 문장은 그 차트의 자료만 보고 쓴다.

- 차트 문장은 자료 끝의 '차트마다 눈에 띄는 점'에서 그 차트의 숫자를 하나 이상 그대로 쓰고, 어느 항목 · 구간인지
  이름을 밝힌다. 예: '3~4년 경력은 필수 조건 충족이 78%로, 5~6년(100%)보다 낮아요.'
- 차트 문장은 그 차트에서 무엇이 보이는지 쓴다. '확인해 보세요 · 살펴보세요' 같은 할 일은 차트 문장에 쓰지 않고
  lines에만 쓴다. '차이가 있어요 · 많아요'처럼 어디가 얼마나인지 없이 끝내지 않는다.
- lines는 차트 문장을 되풀이하지 않는다. 숫자 사이의 관계(목표와 필수 조건 충족자의 차이, 많이 걸리는 필수 조건,
  서류만으로 판단이 어려운 항목, 다시 볼 지원자를 볼 까닭)를 읽어 다음에 할 일로 이어지게 쓴다.
- 숫자는 받은 자료에 있는 값만 쓴다. 새로 계산한 숫자는 쓰지 않는다.
- 항목은 코드(Q-01)가 아니라 짧은 이름(예: Java · Kotlin 경력)으로 쓴다.
- '선 위', '선 아래', '경계 그룹' 같은 내부 말은 쓰지 않고 '필수 조건을 모두 충족한 사람'처럼 풀어 쓴다.
- 합격 · 불합격, 순위('가장', '제일'), 누구를 뽑으라는 말은 쓰지 않는다. 지원자 개인은 다루지 않는다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다.
- 해요체(~어요 · ~예요)로 짧게 쓴다.
{UNTRUSTED_RULE}"""


def facts_text(facts: DistributionFacts) -> str:
    """모델에게 줄 분포 자료. 비율은 코드가 미리 계산해 넣어 모델이 계산하지 않게 한다."""

    def share(part: int, whole: int) -> str:
        return f"{round(100 * part / whole)}%" if whole else "0%"

    lines = [
        f"전체 지원자 {facts.total}명, 서류 분석 완료 {facts.analyzed}명",
        f"필수 조건을 모두 충족한 사람 {facts.above_line}명 (전체의 {share(facts.above_line, facts.total)})",
        f"서류 통과 목표 {facts.target}명, 필수 조건 충족자와 목표의 차이 {facts.above_line - facts.target}명",
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
        lines.append(f"필수 조건 충족자의 항목 충족 수별 인원: {shown}")
    if facts.cut:
        cut = facts.cut
        lines.append(
            f"목표 {facts.target}명째가 충족 {cut.get('value')}개, {cut.get('from')}~{cut.get('to')}번째가 같은 개수"
            f"(목표 안 {cut.get('inside')}명)라 개수로는 선발이 갈리지 않음"
        )
    for group in facts.groups:
        lines.append(f"다시 볼 지원자 '{group.label}' {group.size}명: {group.reason}")
    for band in facts.careers:
        lines.append(
            f"경력 {band.label}: 전체 {band.all}명 중 필수 조건 충족 {band.above_line}명"
            f"({share(band.above_line, band.all)})"
        )
    lines.append("차트마다 눈에 띄는 점 (코드가 고른 사실이다. 차트 문장에 이 숫자를 그대로 쓴다):")
    lines += [f"- {chart}: {point}" for chart, points in highlights(facts).items() for point in points]
    return "\n".join(lines)


def _share(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)}%" if whole else "0%"


def _judged(item: CriterionCount) -> int:
    return item.met + item.partial + item.not_met + item.unknown


def highlights(facts: DistributionFacts) -> dict[str, list[str]]:
    """차트마다 가장 높거나 낮은 값과 그 이름. 모델이 무난한 말로 빠지지 않게 코드가 고른다.

    비율은 facts_text와 같은 반올림이라 모델이 옮겨 써도 자료에 있는 숫자다.
    """
    found: dict[str, list[str]] = {}
    gap = facts.above_line - facts.target
    side = f"보다 {abs(gap)}명 {'많아요' if gap > 0 else '적어요'}" if gap else "과 같아요"
    found["funnel"] = [f"필수 조건 충족 {facts.above_line}명이 서류 통과 목표 {facts.target}명{side}"]
    required = facts.required
    if whole := required.met + required.unmet + required.unknown:
        found["required"] = [
            f"모두 충족 {required.met}명({_share(required.met, whole)}), 미충족 {required.unmet}명"
            f"({_share(required.unmet, whole)}), 확인 필요 {required.unknown}명({_share(required.unknown, whole)})"
        ]
    if facts.counts:
        most = max(facts.counts, key=lambda bucket: bucket.count)
        found["counts"] = [f"필수 조건 충족자 중 항목 {most.value}개를 충족한 사람이 {most.count}명으로 가장 많아요"]
        if cut := facts.cut:
            found["counts"].append(
                f"목표 {facts.target}명째가 항목 {cut.get('value')}개 충족이고, "
                f"{cut.get('from')}~{cut.get('to')}번째가 같은 개수예요"
            )
    if judged := [item for item in facts.criteria if _judged(item)]:
        worst = sorted(judged, key=lambda item: -(item.partial + item.not_met + item.unknown) / _judged(item))[:2]
        found["criteria"] = [
            f"충족이 아닌 비율이 높은 항목: {item.criterion_id} {item.text} "
            f"{_share(item.partial + item.not_met + item.unknown, _judged(item))}"
            for item in worst
        ]
        unsure = max(judged, key=lambda item: item.unknown / _judged(item))
        if 100 * unsure.unknown >= MIN_UNSURE_PERCENT * _judged(unsure):
            found["criteria"].append(
                f"확인 필요 비율이 가장 높은 항목: {unsure.criterion_id} {unsure.text} "
                f"{_share(unsure.unknown, _judged(unsure))}"
            )
    # 한두 명뿐인 구간의 0% · 100%는 크게 읽히므로, 사람이 MIN_BAND명 이상인 구간에서 고른다
    bands = [band for band in facts.careers if band.all >= MIN_BAND] or [band for band in facts.careers if band.all]
    if bands:
        low = min(bands, key=lambda band: band.above_line / band.all)
        high = max(bands, key=lambda band: band.above_line / band.all)

        def shown(band: CareerCount) -> str:
            return f"{band.label} {_share(band.above_line, band.all)}({band.all}명 중 {band.above_line}명)"

        point = f"필수 조건 충족 비율이 가장 낮은 경력: {shown(low)}"
        if high is not low:
            point += f", 가장 높은 경력: {shown(high)}"
        found["careers"] = [point]
    return found


async def explain_distribution(facts: DistributionFacts, llm: LlmClient) -> DistributionNote:
    """분포 해설 두세 문장과 차트마다 한 문장. 검사에 걸린 문장은 버리고, 모델이 형식을 지키지 못하면 빈 해설이다.

    차트 문장이 검사에 걸리면 그 차트만 다시 쓰게 한다(REWRITES번). 앞에서 통과한 문장은 그대로 둔다.
    """
    text = facts_text(facts)
    allowed = set(_NUMBER.findall(text))
    user = data_block("distribution", text)
    kept: list[str] = []
    charts: dict[str, str] = {}
    for attempt in range(REWRITES + 1):
        try:
            draft = await llm.structured(_Draft, agent=AGENT, system=SYSTEM, user=user)
        except LlmOutputError as error:
            logger.warning("분포 해설을 만들지 못했다 (reason=%s)", error.reason.value)
            break
        except APIError as error:
            logger.warning("모델 서버 오류로 분포 해설을 만들지 못했다 (%s)", type(error).__name__)
            break
        lines = [line.strip() for line in draft.lines]
        kept = kept or [
            line for index, line in enumerate(lines) if line and not _problems(f"lines[{index}]", line, allowed)
        ]
        rewrite: list[str] = []
        for name in CHARTS:
            if name in charts:
                continue
            line = getattr(draft.charts, name).strip()
            if found := _problems(f"charts.{name}", line, allowed) + _chart_problems(name, line):
                rewrite += found
            else:
                charts[name] = line
        if not rewrite or attempt == REWRITES:
            break
        logger.info("분포 해설 차트 문장을 다시 쓰게 한다: %s", " | ".join(rewrite))
        user = data_block("distribution", text) + "\n\n다시 쓸 차트 문장 (나머지 칸은 앞과 같게 둔다):\n"
        user += "\n".join(f"- {problem}" for problem in rewrite)
    return DistributionNote(lines=kept[:MAX_LINES], charts=charts)


def _problems(label: str, line: str, allowed: set[str]) -> list[str]:
    if found := sentence_problems(label, line, allowed):
        logger.info("분포 해설 문장을 버린다: %s", " | ".join(found))
    return found


def _chart_problems(name: str, line: str) -> list[str]:
    """차트 문장은 그 차트의 숫자를 하나 이상 쓴다. 숫자가 없으면 '확인해 보세요'로 끝나는 무난한 말이 되기 쉽다."""
    if not line:
        return [f"charts.{name}가 비었다. 그 차트의 눈에 띄는 점을 숫자와 함께 한 문장으로 쓴다"]
    if not _NUMBER.search(_CODE.sub("", line)):
        return [f"charts.{name}에 숫자가 없다. 그 차트의 눈에 띄는 점에서 숫자와 항목 · 구간 이름을 쓴다"]
    return []
