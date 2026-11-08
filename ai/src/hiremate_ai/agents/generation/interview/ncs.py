"""AI Chat 면접 질문의 NCS 참고. Root 계획이 참고하기로 정한 요청(REQUESTED, HELPFUL)에서만 쓴다.

1. 검색: 요청이나 Root가 정리한 확인할 점을 NCS식 업무 문장으로 바꿔 직무 자료 묶음을 찾는다(번호 N1부터).
   같은 요청을 여러 지원자에게 하면 검색어와 결과를 잠깐 기억해 다시 쓴다.
2. 질문 쓰기: 찾은 묶음마다 개념 빈틈 하나를 두고, 모델은 그 빈틈의 질문에 인용한 번호를 적는다(agent.py).
3. 판정: 인용한 질문마다 원문이 질문을 받쳐 주는지, 지원자가 그 일을 했다고 전제했는지를 모델 한 번으로 본다.

NCS 문장은 직무의 일반적인 업무이지 이 지원자가 한 일이 아니다. 출처는 질문의 생성 근거에만 남긴다.
"""

import json
import logging
import time
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.contract import PostingContent
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block
from hiremate_ai.ncs_search.cite import NcsSources, find_sources, source_path
from hiremate_ai.ncs_search.reference import NcsReference
from hiremate_ai.ncs_search.types import NcsTask

logger = logging.getLogger(__name__)

AGENT = "interview"
CACHE_SECONDS = 600

QUERY_SYSTEM = (
    """너는 채용 담당자의 면접 질문 요청을 NCS 직무 기준 검색어로 바꾸는 도구다.
검색 대상은 여러 직무의 업무, 지식, 기술, 태도 등 NCS 직무 자료다.

규칙:
- 요청에서 면접으로 확인하려는 실제 수행 업무만 뽑는다. 면접 질문, 지원자, 서류 같은 낱말은 업무가 아니다.
- 회사 고유의 서비스 이름은 일반적인 업무 용어로 바꾸되, 직무와 산업을 구별하는 말은 남긴다.
- 요청에 없는 업무, 특정 제품, 수치를 덧붙이지 않는다.
- tasks에는 '… 한다'로 끝나는 한 가지 업무 문장을 1개에서 3개 쓴다.
- units에는 그 업무를 주요 업무로 직접 다루는 능력단위를 능력단위 목록에서 관련도가 높은 순으로 최대 5개 고른다.
  각 줄은 '능력단위코드 능력단위명: 주요 업무들'이다. 목록에 있는 코드만 그대로 쓰고,
  낱말만 같고 직무나 산업이 다른 단위는 고르지 않는다. 맞는 단위가 없으면 빈 목록으로 둔다.
"""
    + UNTRUSTED_RULE
)

CHECK_SYSTEM = (
    """너는 면접관에게 보여 줄 면접 질문과, 그 질문이 참고한 NCS 원문 문장이 맞는지 확인한다.
항목마다 두 가지를 판정한다.
- verdict: 원문 문장이 질문이 묻는 업무를 직접 받쳐 주면 supports, 업무가 다르거나 일부 낱말만 겹치면 unrelated.
- assumes_experience: 질문이 지원자가 그 일을 실제로 했다고 전제하면 true('구현하셨을 때', '맡으셨던 경험에서'처럼
  과거 수행을 사실로 깔고 묻는 경우). 원리 · 판단 기준을 묻거나 '만약 …라면'처럼 가상 상황을 묻으면 false.
모든 항목에 판정을 하나씩 남긴다.
"""
    + UNTRUSTED_RULE
)

NCS_RULES = (
    "ncs_rules: ncs 블록이 붙은 빈틈은 그 NCS 직무 문장의 원리와 판단 기준을 묻는 CONCEPT 질문으로 쓴다. "
    "source_id에는 그 빈틈의 ncs 블록에 있는 번호(N1 등) 하나를 그대로 적는다. 질문 문장에는 번호를 쓰지 않는다. "
    "NCS 문장은 직무의 일반적인 업무이지 이 지원자가 한 일이 아니므로, 지원자가 그 일을 했다고 전제하지 않는다. "
    "문장을 그대로 읽지 말고 실제 업무를 묻는 말로 풀어 쓰며, 자료에 없는 수치나 도구 이름을 만들지 않는다."
)


class NcsVerdict(BaseModel):
    index: int = Field(description="판정한 항목 번호")
    verdict: Literal["supports", "unrelated"]
    assumes_experience: bool = Field(description="지원자가 그 일을 실제로 했다고 전제하면 true")


class NcsCheck(BaseModel):
    """항목마다 하나의 판정. 판정이 빠진 항목은 출처에서 뺀다."""

    verdicts: list[NcsVerdict]


SearchKey = tuple[str, str, tuple[str, ...]]
"""검색 기억의 키: (요청, 직무 이름, 공고 주요 업무). 검색에 들어가는 입력을 모두 담는다."""

_cache: dict[SearchKey, tuple[float, NcsSources | None]] = {}


def _now() -> float:
    return time.monotonic()


def clear_cache() -> None:
    _cache.clear()


def cached_keys() -> list[SearchKey]:
    return list(_cache)


def remember(key: SearchKey, sources: NcsSources | None) -> None:
    """검색 결과를 기억하고, 기한이 지난 기억은 이때 지운다 (서버를 오래 띄워도 쌓이지 않게)."""
    now = _now()
    for old in [old for old, (saved, _) in _cache.items() if now - saved >= CACHE_SECONDS]:
        del _cache[old]
    _cache[key] = (now, sources)


async def interview_sources(
    llm: LlmClient, ncs: NcsReference, focus: str, posting: PostingContent
) -> NcsSources | None:
    """요청에 맞는 NCS 문장. 찾지 못했으면 None이다. 같은 입력의 결과는 CACHE_SECONDS 동안 다시 쓴다.

    검색 서비스 실패(UNAVAILABLE)는 잠깐의 문제일 수 있어 기억하지 않는다.
    """
    job = posting.job_category or posting.title
    key: SearchKey = (focus, job, tuple(posting.duties))
    hit = _cache.get(key)
    if hit is not None and _now() - hit[0] < CACHE_SECONDS:
        return hit[1]
    sources, miss = await find_sources(
        llm, ncs, focus, job, agent=AGENT, system=QUERY_SYSTEM, prefix="N", strict_units=True
    )
    if miss != "UNAVAILABLE":
        remember(key, sources)
    return sources


def tasks_of(sources: NcsSources) -> list[tuple[NcsTask, list[str]]]:
    """검색 순서대로 묶음과 그 묶음 문장의 번호."""
    grouped: dict[str, tuple[NcsTask, list[str]]] = {}
    for number, (task, _) in sources.items.items():
        grouped.setdefault(task.chunk_id, (task, []))[1].append(number)
    return list(grouped.values())


def ncs_block(sources: NcsSources, numbers: list[str]) -> str:
    return data_block(
        "ncs",
        "\n".join(
            f"[{number}] {source_path(sources.items[number][0])}: {sources.items[number][1]}" for number in numbers
        ),
    )


async def check_cited(llm: LlmClient, items: list[tuple[str, str]]) -> list[NcsVerdict] | None:
    """(질문, 인용한 원문) 목록의 판정. 실패하면 None이다."""
    payload = [
        {"index": index, "question": question, "source": source} for index, (question, source) in enumerate(items)
    ]
    try:
        review = await llm.structured(
            NcsCheck,
            agent=AGENT,
            system=CHECK_SYSTEM,
            user=data_block("cited_questions", json.dumps(payload, ensure_ascii=False)),
        )
    except Exception as error:
        logger.warning("면접 질문 NCS 출처 판정 실패: %s", type(error).__name__)
        return None
    return review.verdicts


def ncs_reason(task: NcsTask, sentence: str) -> str:
    return f"출처: NCS {source_path(task)}\n원문: {sentence}"
