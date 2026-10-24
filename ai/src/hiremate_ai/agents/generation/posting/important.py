"""자격 요건 · 우대 사항 '중요' 추천. HR이 '중요'로 표시할 만한 항목을 목록마다 몇 개 고르고 근거 주요 업무를 붙인다.

공고 초안의 마지막 단계다. 작은 모델은 항목을 쓰면서 고르기까지 하면 둘 다 나빠져서, 목록을 다 쓴 뒤 따로 묻는다.
목록마다 한 번 묻고, 앞부분(지금 공고)을 같게 둬서 모델이 앞부분을 다시 읽지 않는다.

- 주요 업무와 항목에 번호를 붙여 모델이 번호로 고르게 한다. 근거 문장은 코드가 공고에서 가져와서
  모델이 다른 문장을 옮기는 실수가 없다 (규칙 7).
- NCS 조사 점수는 참고로 보여 준다. 판단 기준은 주요 업무에 바로 쓰이는지다.
- 목록의 3분의 1까지만 추천한다 (IMPORTANT_SHARE). 전부 '중요'면 표시하지 않은 것과 같다.

추천은 참고값이다. '중요'는 HR이 정한다.
"""

import math
from collections.abc import Mapping

from pydantic import BaseModel, Field

from hiremate_ai.agents.generation.posting.reviser import AGENT, NCS_FIELDS, SourcedItem
from hiremate_ai.contract import PostingContent
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.tools.ncs import NcsUnit, ncs_data, survey_score, unit_by_code

IMPORTANT_SHARE = 1 / 3
"""목록마다 '중요'로 추천하는 최대 비율. 항목 수의 3분의 1을 반올림한다 (예: 5개 중 2개, 10개 중 3개).

'중요'는 소수여야 서류 점수의 가중치가 의미 있다. 적게 추천하고 HR이 필요하면 더 표시한다.
"""


class Pick(BaseModel):
    item: int = Field(description="항목 번호")
    duty: int = Field(description="그 항목이 바로 쓰이는 주요 업무 번호")


class ImportantPicks(BaseModel):
    picks: list[Pick] = Field(description="'중요'로 추천할 항목. 지금 할 일에 적힌 개수까지")


class ImportantItem(BaseModel):
    """'중요' 추천 하나. index는 목록 안 위치(0부터), duty는 근거가 된 주요 업무 문장(공고의 그 줄 그대로)이다."""

    index: int
    duty: str


class ImportantAdvice(BaseModel):
    qualifications: list[ImportantItem] = Field(description="자격 요건 중 '중요' 추천")
    preferred: list[ImportantItem] = Field(description="우대 사항 중 '중요' 추천")


IMPORTANT_SYSTEM = """너는 채용 공고의 자격 요건 · 우대 사항 목록에서 HR이 '중요'로 표시할 만한 항목을 추천한다.
추천은 참고값이고 '중요'는 HR이 정한다.

규칙:
1. 주요 업무에 바로 쓰이는 핵심 항목만 고른다. 고를 수 있는 개수는 "지금 할 일"에 적혀 있고, 다 고르지 않아도 된다.
2. 고른 항목마다 그 항목이 바로 쓰이는 주요 업무의 번호를 duty에 적는다.
   바로 쓰이는 주요 업무가 없는 항목은 고르지 않는다.
3. 현장 조사 점수는 NCS 현장 응답자들이 그 능력을 중요하고 자주 쓴다고 본 정도다 (3점 만점).
   주요 업무에 비슷하게 쓰이는 항목끼리 고를 때만 참고한다."""


async def recommend_important(
    llm: LlmClient, content: PostingContent, lists: Mapping[str, list[SourcedItem]]
) -> ImportantAdvice:
    """목록마다 '중요'로 추천할 항목을 고른다.

    lists의 키는 qualifications · preferred이고, 항목의 sources는 근거 능력단위 코드다 (HR이 쓴 항목은 비어 있다).
    항목이 둘보다 적거나 주요 업무가 없으면 그 목록은 묻지 않고 추천하지 않는다.
    """
    context = _context(content)
    advice: dict[str, list[ImportantItem]] = {}
    for name, label in NCS_FIELDS:
        items = lists.get(name, [])
        limit = important_limit(len(items))
        if limit < 1 or not content.duties:
            advice[name] = []
            continue
        picks = await llm.structured(
            ImportantPicks,
            agent=AGENT,
            system=IMPORTANT_SYSTEM,
            user=f"{context}\n\n{_list_prompt(label, items, limit)}",
        )
        advice[name] = _checked(picks.picks, len(items), content.duties, limit)
    return ImportantAdvice.model_validate(advice)


def important_limit(size: int) -> int:
    """항목 수에 맞춘 추천 최대 개수. 최소 1개이고 전부는 추천하지 않는다 (한 항목 목록은 0)."""
    return min(max(1, math.floor(size * IMPORTANT_SHARE + 0.5)), size - 1)


def _checked(picks: list[Pick], size: int, duties: list[str], limit: int) -> list[ImportantItem]:
    """번호가 맞는 것만, 한 항목에 한 번씩, 정한 개수까지. 주요 업무 번호가 틀리면 근거가 없어 버린다 (규칙 7)."""
    chosen: dict[int, ImportantItem] = {}
    for pick in picks:
        index, duty = pick.item - 1, pick.duty - 1
        if 0 <= index < size and 0 <= duty < len(duties) and index not in chosen:
            chosen[index] = ImportantItem(index=index, duty=duties[duty].strip())
    return list(chosen.values())[:limit]


def _context(content: PostingContent) -> str:
    """모든 호출의 앞부분. 목록마다 같다."""
    lines = [f"지금 공고: {content.title} ({content.job_category}, {content.career})", "주요 업무:"]
    lines += [f"[업무 {number}] {duty}" for number, duty in enumerate(content.duties, 1)]
    return "\n".join(lines)


def _list_prompt(label: str, items: list[SourcedItem], limit: int) -> str:
    lines = [f"{label} 목록:"]
    lines += [f"[항목 {number}] {item.text.strip()}{_ncs_note(item)}" for number, item in enumerate(items, 1)]
    lines.append(
        f"지금 할 일: 이 {label} 목록에서 '중요'로 추천할 항목을 최대 {limit}개 picks에 고른다. "
        "항목 번호는 item, 주요 업무 번호는 duty에 적는다."
    )
    return "\n".join(lines)


def _ncs_note(item: SourcedItem) -> str:
    """항목의 근거 능력단위와 그 현장 조사 점수. 조사가 없는 능력단위는 이름만 적는다."""
    units = list({unit.code: unit for code in item.sources if (unit := unit_by_code(code.strip()))}.values())
    return f" (NCS: {', '.join(_unit_note(unit) for unit in units)})" if units else ""


def _unit_note(unit: NcsUnit) -> str:
    survey = ncs_data().surveys.get(unit.code)
    return f"{unit.name} · 현장 조사 점수 {survey_score(survey):.2f}" if survey else unit.name
