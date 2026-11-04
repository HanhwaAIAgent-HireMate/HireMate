"""Agent가 NCS를 참고할 때 쓰는 검색 단계. 요청을 NCS식 업무 문장과 능력단위로 바꾸고, 찾은 문장에 번호를 붙인다.

검색어 만들기의 지시문(system)과 Agent 이름은 부르는 쪽이 정한다. 찾지 못했을 때 HR에게 알릴지, 무슨 말로 알릴지도
부르는 쪽이 정하므로 여기서는 이유(NcsMiss)만 돌려준다.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.config import settings
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import data_block
from hiremate_ai.ncs_search.reference import NcsReference, NcsUnavailable
from hiremate_ai.ncs_search.types import NcsTask, NcsUnit

logger = logging.getLogger(__name__)

MAX_UNITS = 5

NcsMiss = Literal["NOT_FOUND", "UNAVAILABLE"]
"""찾지 못한 이유. UNAVAILABLE은 DB, 임베딩 서비스, 검색어 만들기의 실패나 시간 초과다."""


class NcsQuery(BaseModel):
    """검색어 만들기 답."""

    tasks: list[str] = Field(max_length=3, description="요청의 수행 업무를 '… 한다'로 끝나게 쓴 문장 1~3개")
    units: list[str] = Field(
        description="능력단위 목록에 있는 코드만, 관련도 순으로 최대 5개. 맞는 단위가 없으면 빈 목록"
    )


@dataclass(frozen=True)
class NcsSources:
    """이번 요청에서 찾은 NCS 문장. 번호(검색 순서 · 문장 순서) → (묶음, 문장)."""

    items: dict[str, tuple[NcsTask, str]]


async def find_sources(
    llm: LlmClient,
    ncs: NcsReference,
    request: str,
    job: str,
    *,
    agent: str,
    system: str,
    prefix: str = "S",
) -> tuple[NcsSources | None, NcsMiss | None]:
    """요청에 맞는 NCS 문장과, 찾지 못한 이유.

    표가 비어 있으면 모델을 부르지 않는다. DB, 검색어 만들기, 임베딩이 실패하거나 settings.ncs_reference_timeout_seconds
    안에 끝나지 않아도 예외를 내지 않는다.
    """
    try:
        async with asyncio.timeout(settings.ncs_reference_timeout_seconds):
            return await _find(llm, ncs, request, job, agent, system, prefix)
    except TimeoutError:
        logger.warning("NCS 참고가 %s초 안에 끝나지 않았습니다.", settings.ncs_reference_timeout_seconds)
        return None, "UNAVAILABLE"


async def _find(
    llm: LlmClient, ncs: NcsReference, request: str, job: str, agent: str, system: str, prefix: str
) -> tuple[NcsSources | None, NcsMiss | None]:
    try:
        units = await ncs.units()
    except NcsUnavailable as error:
        logger.warning("NCS 능력단위 목록 조회 실패: %s", error)
        return None, "UNAVAILABLE"
    if not units:
        return None, "NOT_FOUND"
    user = "\n\n".join([data_block("ncs_units", _unit_list(units)), f"직무: {job or '(비어 있음)'}\n요청: {request}"])
    try:
        query = await llm.structured(NcsQuery, agent=agent, system=system, user=user)
    except Exception as error:
        logger.warning("NCS 검색어 만들기 실패: %s", type(error).__name__)
        return None, "UNAVAILABLE"
    known = {unit.code for unit in units}
    # 모델이 '코드 단위명: 주요 업무' 줄을 통째로 적기도 해서 앞의 코드만 본다
    codes = (unit.split(maxsplit=1)[0] if unit.strip() else "" for unit in query.units)
    chosen = list(dict.fromkeys(code for code in codes if code in known))[:MAX_UNITS]
    try:
        found = await ncs.search(request, query.tasks, chosen)
    except NcsUnavailable as error:
        logger.warning("NCS 검색 실패: %s", error)
        return None, "UNAVAILABLE"
    items: dict[str, tuple[NcsTask, str]] = {}
    for task in found:
        for sentence in task.sentences:
            items[f"{prefix}{len(items) + 1}"] = (task, sentence)
    return (NcsSources(items=items), None) if items else (None, "NOT_FOUND")


def _unit_list(units: list[NcsUnit]) -> str:
    lines: list[str] = []
    for unit in units:
        heading = f"## {unit.duty_name}"
        if heading not in lines:
            lines.append(heading)
        lines.append(f"{unit.code} {unit.name}: {', '.join(unit.task_names)}")
    return "\n".join(lines)


def source_path(task: NcsTask) -> str:
    return f"{task.duty_name} › {task.unit_name} › {task.task_name}"


def sources_block(sources: NcsSources) -> str:
    return data_block(
        "ncs",
        "\n".join(f"[{number}] {source_path(task)}: {sentence}" for number, (task, sentence) in sources.items.items()),
    )
