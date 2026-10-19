"""A 지원자 찾기. 후보 범위와 점수 조건은 코드가 정하고, 검색으로 넓게 모은 뒤 재확인으로 좁힌다 (기획 §11, §13).

같은 질문에 같은 후보가 나오도록 순서는 코드가 정한다. 결과는 선택 지원자 변경 명령(FIND)으로만 낸다.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from hiremate_ai.agents.guardrails import evidence_source
from hiremate_ai.agents.root.route import DEFAULT_CLARIFY, NOT_UNDERSTOOD, RootRoute
from hiremate_ai.agents.root.toolkit import RootToolkit, scope_of
from hiremate_ai.agents.root.types import (
    CandidateRow,
    ChatContext,
    ChatItem,
    ChatPlan,
    Decision,
    Intent,
    SelectionMode,
)
from hiremate_ai.contract import StageType
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block
from hiremate_ai.tools.candidates import CandidateMatch

SCORE_GAP = 15
ITEM_LIMIT = 5
RECHECK_LIMIT = 30
EVIDENCE_LENGTH = 48
LIMIT_NOTE = " 조건에 가까운 30명 중에서 골랐어요."
REPLACED = "지원자 {total}명 중 조건에 맞는 **{count}명**을 선택했어요."
ADDED = "조건에 맞는 **{count}명**을 선택 지원자에 더했어요."
NARROWED = "{pool}명 중 **{{count}}명**으로 좁혔어요."
NOT_FOUND = "조건에 맞는 지원자를 찾지 못했어요. 선택 지원자는 그대로예요."

RECHECK_SYSTEM = """너는 채용 담당자의 지원자 찾기 요청에서, 검색으로 모은 후보가 조건을 실제로 충족하는지 판정한다.
후보마다 주어진 원문 문장만 보고 판단한다. 문장에 없는 내용을 짐작하지 않는다.

- 요청의 조건을 모두 충족하는 근거 문장이 있으면 met=true, 아니면 met=false다.
- 도메인 경험은 그 업계의 회사나 서비스에서 일한 경력이다.
  다른 업계에서 비슷한 기능을 만든 일, 개인 · 학교 프로젝트, 데이터를 분석만 한 일은 그 도메인 경험이 아니다.
- 근거 문장(sentence)은 주어진 문장 하나를 글자 그대로 옮긴다. met=false면 비운다.
- application_id는 후보 블록의 id를 그대로 쓴다."""


class RecheckItem(BaseModel):
    application_id: str = Field(description="후보 블록의 id")
    met: bool = Field(description="요청의 조건을 모두 충족하는 근거가 있으면 true")
    sentence: str | None = Field(default=None, description="근거 문장. 주어진 문장을 글자 그대로")


class RecheckResult(BaseModel):
    results: list[RecheckItem]


def candidate_pool(route: RootRoute, context: ChatContext) -> list[CandidateRow]:
    """미결정 지원자. 서류 전형은 기준선 위만, 좁히기는 지금 선택된 지원자 안에서만."""
    rows = [row for row in context.candidates if row.decision is Decision.PENDING]
    if context.stage_type is StageType.DOCUMENT:
        rows = [row for row in rows if row.above_line]
    if route.mode is SelectionMode.NARROW:
        rows = [row for row in rows if row.selected]
    return rows


def score_filter(
    route: RootRoute, context: ChatContext, rows: list[CandidateRow]
) -> tuple[list[CandidateRow], dict[UUID, str]]:
    """평가 점수 조건을 적용하고 지원자별 점수 설명을 붙인다. score는 평가 전형 점수, document_scores는 서류 점수다."""
    notes: dict[UUID, str] = {}
    if route.min_score is not None:
        rows = [row for row in rows if row.score is not None and row.score >= route.min_score]
    if route.without_score:
        rows = [row for row in rows if row.score is None]
    for row in rows:
        if row.score is not None:
            notes[row.application_id] = f"평가 {_points(row.score)}점"
    if route.score_gap:
        gaps = []
        for row in rows:
            document = context.document_scores.get(row.application_id)
            if row.score is not None and document is not None and abs(row.score - document) >= SCORE_GAP:
                gaps.append((row, row.score, document))
        gaps.sort(key=lambda gap: -abs(gap[1] - gap[2]))
        rows = [row for row, _, _ in gaps]
        for row, score, document in gaps:
            direction = "평가가 지원서보다 높음" if score > document else "지원서에 비해 평가가 낮음"
            notes[row.application_id] = f"평가 {_points(score)}점 · 서류 {document}점, {direction}"
    return rows, notes


async def plan_find(llm: LlmClient, route: RootRoute, context: ChatContext, toolkit: RootToolkit) -> ChatPlan:
    pool = candidate_pool(route, context)
    rows, notes = score_filter(route, context, pool)
    concepts = list(route.concepts)
    if route.use_talents:
        concepts += [f"{talent.title} {talent.description}" for talent in context.company.talents]
    has_score = route.min_score is not None or route.without_score or route.score_gap
    score_sources = (["평가 결과", "서류 점수"] if route.score_gap else ["평가 결과"]) if has_score else []
    if not concepts:
        if not has_score:
            return ChatPlan.answer(Intent.CLARIFY, DEFAULT_CLARIFY)
        chosen = [(row, notes.get(row.application_id, row.name)) for row in rows]
        return _plan(route, len(pool), chosen, score_sources)

    allowed = {row.application_id: row for row in rows}
    found = await toolkit.search(scope_of(context), concepts, list(allowed))
    matches = [match for match in found if match.application_id in allowed]
    limited = len(matches) > RECHECK_LIMIT
    matches = matches[:RECHECK_LIMIT]
    if not matches:
        return ChatPlan.answer(Intent.ANSWER, NOT_FOUND)
    try:
        verified = await recheck(llm, context, concepts, matches)
    except LlmOutputError:
        return ChatPlan.answer(Intent.CLARIFY, NOT_UNDERSTOOD)
    chosen = [(allowed[application_id], _shorten(sentence)) for application_id, sentence, _ in verified]
    sources = list(dict.fromkeys(source for _, _, source in verified)) + score_sources
    plan = _plan(route, len(pool), chosen, sources)
    if limited and plan.intent is Intent.FIND:
        plan = plan.model_copy(update={"message": plan.message + LIMIT_NOTE})
    return plan


async def recheck(
    llm: LlmClient, context: ChatContext, concepts: list[str], matches: list[CandidateMatch]
) -> list[tuple[UUID, str, str]]:
    """모델이 충족한다고 판정하고 근거 문장이 원문에 있는 후보만 (id, 문장, 출처)로 돌려준다. 검색 순서를 지킨다."""
    blocks = "\n\n".join(
        data_block(
            "candidate",
            "\n".join(f"- [{sourced.source}] {sourced.sentence}" for sourced in match.sentences),
            id=str(match.application_id),
        )
        for match in matches
    )
    user = f"요청: {context.message}\n조건:\n" + "\n".join(f"- {concept}" for concept in concepts) + f"\n\n{blocks}"
    result = await llm.structured(
        RecheckResult, agent="root", system=f"{RECHECK_SYSTEM}\n\n{UNTRUSTED_RULE}", user=user
    )
    judged = {item.application_id: item for item in result.results}
    verified = []
    for match in matches:
        item = judged.get(str(match.application_id))
        if item is None or not item.met or not item.sentence:
            continue
        source = evidence_source(item.sentence, context.documents.get(match.application_id, []))
        if source is not None:
            verified.append((match.application_id, item.sentence.strip(), source.label))
    return verified


def _plan(route: RootRoute, pool_size: int, chosen: list[tuple[CandidateRow, str]], sources: list[str]) -> ChatPlan:
    if not chosen:
        return ChatPlan.answer(Intent.ANSWER, NOT_FOUND)
    mode = route.mode or SelectionMode.REPLACE
    message = {
        SelectionMode.REPLACE: REPLACED,
        SelectionMode.ADD: ADDED,
        SelectionMode.NARROW: NARROWED.format(pool=pool_size),
    }[mode]
    items = [
        ChatItem(application_id=row.application_id, label=row.name, text=text, status=None)
        for row, text in chosen[:ITEM_LIMIT]
    ]
    return ChatPlan(
        intent=Intent.FIND,
        mode=mode,
        edit=None,
        targets=[row.application_id for row, _ in chosen],
        message=message,
        items=items,
        sources=sources,
        agents=[],
        question_targets=[],
    )


def _points(value: float) -> str:
    return f"{value:g}"


def _shorten(text: str) -> str:
    trimmed = " ".join(text.split())
    return trimmed if len(trimmed) <= EVIDENCE_LENGTH else trimmed[: EVIDENCE_LENGTH - 1] + "…"
