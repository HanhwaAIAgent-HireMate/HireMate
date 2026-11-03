"""공고 수정의 NCS 참고. NCS는 HR이 보고 판단하는 참고자료라 출처는 채팅 답에만 붙이고 공고에는 넣지 않는다.

1. 검색어 만들기: 모델 한 번으로 요청을 NCS식 업무 문장으로 바꾸고 능력단위 목록에서 최대 5개를 고른다.
2. 검색: 원문 요청, 바꾼 문장, 고른 단위로 '책임 및 역할' 묶음을 찾는다(ncs_search).
3. 본문 쓰기: 찾은 문장에 번호를 붙여 넣고, 모델은 참고한 목록 줄마다 번호를 적는다.
4. 출처 확인: 줄과 번호를 공고에 들어간 줄과 맞추고, 모델 한 번으로 원문이 줄을 받쳐 주는지 판정한다.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.contract import PostingContent
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block
from hiremate_ai.ncs_search.reference import NcsReference, NcsUnavailable
from hiremate_ai.ncs_search.types import NcsTask, NcsUnit

logger = logging.getLogger(__name__)

AGENT = "posting"

NCS_HEADER = "참고한 NCS:"
NCS_NOT_FOUND = "참고할 NCS 자료를 찾지 못했어요."
NCS_UNAVAILABLE = "NCS 검색에 문제가 생겨 NCS 없이 수정안을 만들었어요."
NCS_SOURCES_DROPPED = "일부 줄은 NCS 원문과 맞지 않아 출처에서 뺐어요."
NCS_REVIEW_FAILED = "출처 확인을 마치지 못해 NCS 출처를 표시하지 않았어요."

MAX_UNITS = 5

NcsUse = Literal["SKIP", "REQUESTED", "HELPFUL"]
"""NCS 참고 여부. REQUESTED는 HR이 NCS를 참고하라고 한 요청이라, 찾지 못하면 알린다."""
CitedLabel = Literal["주요 업무", "자격 요건", "우대 사항"]
_CITED_FIELDS: dict[CitedLabel, str] = {"주요 업무": "duties", "자격 요건": "qualifications", "우대 사항": "preferred"}

QUERY_SYSTEM = (
    """너는 채용 담당자의 공고 수정 요청을 NCS 직무 기준 검색어로 바꾸는 도구다.
검색 대상은 정보기술 직무의 '책임 및 역할' 문장이다. 이 문장들은 '…를 기반으로 …을 작성 한다'처럼 특정 회사나
서비스 이름 없이 일반적인 소프트웨어 개발 용어로 수행 업무를 적는다.

규칙:
- 요청에서 담당자가 찾으려는 실제 수행 업무만 뽑는다. 공고, 평가 기준, 면접 질문 같은 산출물 형식은 업무가 아니다.
- 회원, 주문, 배송사, 결제처럼 회사 서비스의 업무 영역 이름은 그 업무를 가리키는 일반적인 소프트웨어 개발 용어로 바꾼다.
- '백엔드', '개발자' 같은 직무명이나 'NCS'라는 낱말은 쓰지 않는다.
- 요청에 없는 업무, 특정 제품, 수치를 덧붙이지 않는다.
- tasks에는 '… 한다'로 끝나는 한 가지 업무 문장을 1개에서 3개 쓴다.
- units에는 그 업무를 주요 업무로 직접 다루는 능력단위를 능력단위 목록에서 관련도가 높은 순으로 최대 5개 고른다.
  각 줄은 '능력단위코드 능력단위명: 주요 업무들'이다. 직무명이나 서비스 이름이 능력단위명에 들어 있다는 이유만으로
  고르지 않는다. 목록에 있는 코드만 그대로 쓰고, 맞는 단위가 없으면 빈 목록으로 둔다.
"""
    + UNTRUSTED_RULE
)

SOURCES_STEP = (
    "NCS 참고자료: 아래 <data kind=\"ncs\">는 NCS 직무기술서의 '책임 및 역할' 문장이다. 직무에 맞을 때만 참고하고, "
    "맞지 않으면 쓰지 않는다. 문장을 그대로 옮기지 말고 공고 문장으로 쓴다. 자료에 없는 수치, 필수 자격증, 경력 연수를 "
    "만들지 않고, 관련 자격이나 숙련기간을 필수 조건으로 바꾸지 않는다. NCS를 참고해 쓴 주요 업무 · 자격 요건 · "
    "우대 사항 줄마다 citations에 칸 이름(field), 공고에 쓴 그 줄 그대로(line), 참고한 문장 번호(sources, 예: S2)를 "
    "적는다. 참고하지 않았으면 citations는 빈 목록이다."
)

SUPPORT_SYSTEM = (
    """너는 채용 담당자에게 보여 줄 공고 줄과 그 줄에 붙은 NCS 원문 출처가 맞는지 확인한다.
항목마다 원문 문장이 공고 줄의 업무 내용을 직접 받쳐 주면 supports, 업무가 다르거나 일부 낱말만 겹치거나
줄의 핵심을 설명하지 못하면 unrelated로 판정한다.
원문이 다른 직무 분야의 문장이어도 같은 업무를 설명하면 supports다.
기술이나 지식 이름만 있는 원문은 그 업무를 수행한다는 줄의 근거가 아니므로 unrelated다.
모든 항목에 판정을 하나씩 남긴다.
"""
    + UNTRUSTED_RULE
)


class NcsQuery(BaseModel):
    """검색어 만들기 답."""

    tasks: list[str] = Field(max_length=3, description="요청의 수행 업무를 '… 한다'로 끝나게 쓴 문장 1~3개")
    units: list[str] = Field(
        description="능력단위 목록에 있는 코드만, 관련도 순으로 최대 5개. 맞는 단위가 없으면 빈 목록"
    )


class LineCitation(BaseModel):
    """모델이 NCS를 참고해 쓴 목록 줄 하나와 참고한 문장 번호."""

    field: CitedLabel = Field(description="줄이 있는 칸")
    line: str = Field(description="공고에 쓴 그 줄 그대로")
    sources: list[str] = Field(description="참고한 NCS 문장 번호 (예: S2)")


class SupportVerdict(BaseModel):
    index: int = Field(description="판정한 항목 번호")
    verdict: Literal["supports", "unrelated"]


class SupportReview(BaseModel):
    """항목마다 하나의 판정. 판정이 빠진 항목은 출처에서 뺀다."""

    verdicts: list[SupportVerdict]


@dataclass(frozen=True)
class NcsSources:
    """이번 요청에서 찾은 NCS 문장. 번호(S1부터, 검색 순서 · 문장 순서) → (묶음, 문장)."""

    items: dict[str, tuple[NcsTask, str]]


@dataclass(frozen=True)
class Cited:
    """공고에 들어간 목록 줄 하나와 그 줄이 참고한 문장 번호 하나. number는 칸 안의 몇 번째 줄인지(1부터)다."""

    label: CitedLabel
    number: int
    line: str
    source: str


async def find_sources(
    llm: LlmClient, ncs: NcsReference, request: str, job: str
) -> tuple[NcsSources | None, str | None]:
    """요청에 맞는 NCS 문장과, 찾지 못했을 때의 안내. 안내를 HR에게 보일지는 부르는 쪽이 정한다.

    표가 비어 있으면 모델을 부르지 않는다. 검색어 만들기나 임베딩이 실패해도 예외를 내지 않는다.
    """
    units = await ncs.units()
    if not units:
        return None, NCS_NOT_FOUND
    user = "\n\n".join(
        [data_block("ncs_units", _unit_list(units)), f"직무: {job or '(비어 있음)'}\nHR 요청: {request}"]
    )
    try:
        query = await llm.structured(NcsQuery, agent=AGENT, system=QUERY_SYSTEM, user=user)
    except Exception as error:
        logger.warning("NCS 검색어 만들기 실패: %s", type(error).__name__)
        return None, NCS_UNAVAILABLE
    known = {unit.code for unit in units}
    chosen = list(dict.fromkeys(code for code in query.units if code in known))[:MAX_UNITS]
    try:
        found = await ncs.search(request, query.tasks, chosen)
    except NcsUnavailable as error:
        logger.warning("NCS 검색 실패: %s", error)
        return None, NCS_UNAVAILABLE
    items: dict[str, tuple[NcsTask, str]] = {}
    for task in found:
        for sentence in task.sentences:
            items[f"S{len(items) + 1}"] = (task, sentence)
    return (NcsSources(items=items), None) if items else (None, NCS_NOT_FOUND)


def _unit_list(units: list[NcsUnit]) -> str:
    lines: list[str] = []
    for unit in units:
        heading = f"## {unit.duty_name}"
        if heading not in lines:
            lines.append(heading)
        lines.append(f"{unit.code} {unit.name}: {', '.join(unit.task_names)}")
    return "\n".join(lines)


def sources_block(sources: NcsSources) -> str:
    return data_block(
        "ncs",
        "\n".join(f"[{number}] {_path(task)}: {sentence}" for number, (task, sentence) in sources.items.items()),
    )


def _path(task: NcsTask) -> str:
    return f"{task.duty_name} › {task.unit_name} › {task.task_name}"


def cite_lines(
    citations: list[LineCitation],
    content: PostingContent,
    changed: list[str],
    sources: NcsSources,
    clean: Callable[[str], str],
) -> list[Cited]:
    """모델의 인용을 공고에 들어간 줄과 맞춘다. 이번에 바뀐 칸의 줄만 받고, 줄이나 번호가 없으면 그 인용만 버린다."""
    cited: list[Cited] = []
    for citation in citations:
        name = _CITED_FIELDS[citation.field]
        items: list[str] = getattr(content, name)
        line = clean(citation.line)
        if name not in changed or line not in items:
            continue
        for source in citation.sources:
            entry = Cited(label=citation.field, number=items.index(line) + 1, line=line, source=source)
            if source in sources.items and entry not in cited:
                cited.append(entry)
    return cited


async def keep_supported(llm: LlmClient, cited: list[Cited], sources: NcsSources) -> tuple[list[Cited], str | None]:
    """원문이 받쳐 준다고 판정한 출처만 남긴다. 뺀 출처가 있으면 알리고, 판정에 실패하면 모두 뺀다."""
    if not cited:
        return [], None
    payload = [
        {"index": index, "line": entry.line, "source": sources.items[entry.source][1]}
        for index, entry in enumerate(cited)
    ]
    try:
        review = await llm.structured(
            SupportReview,
            agent=AGENT,
            system=SUPPORT_SYSTEM,
            user=data_block("cited_lines", json.dumps(payload, ensure_ascii=False)),
        )
    except Exception as error:
        logger.warning("NCS 출처 판정 실패: %s", type(error).__name__)
        return [], NCS_REVIEW_FAILED
    supported = {verdict.index for verdict in review.verdicts if verdict.verdict == "supports"}
    kept = [entry for index, entry in enumerate(cited) if index in supported]
    return kept, None if len(kept) == len(cited) else NCS_SOURCES_DROPPED


def source_lines(cited: list[Cited], sources: NcsSources) -> list[str]:
    """답 끝에 붙이는 출처 줄. 예: 주요 업무 2번 ← 직무 › 능력단위 › 주요 업무: "원문 문장"."""
    lines = []
    for entry in cited:
        task, sentence = sources.items[entry.source]
        lines.append(f'{entry.label} {entry.number}번 ← {_path(task)}: "{sentence}"')
    return lines
