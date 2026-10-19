"""A 지원자 찾기. 후보 범위와 점수 조건은 코드가 정하고, 검색으로 넓게 모은 뒤 재확인으로 좁힌다 (기획 §11, §13).

같은 질문에 같은 후보가 나오도록 순서는 코드가 정한다. 결과는 선택 지원자 변경 명령(FIND)으로만 낸다.
"""

from uuid import UUID

from hiremate_ai.agents.root.route import DEFAULT_CLARIFY, RootRoute
from hiremate_ai.agents.root.toolkit import RootToolkit
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
from hiremate_ai.llm.client import LlmClient

SCORE_GAP = 15
ITEM_LIMIT = 5
REPLACED = "지원자 {total}명 중 조건에 맞는 **{count}명**을 선택했어요."
ADDED = "조건에 맞는 **{count}명**을 선택 지원자에 더했어요."
NARROWED = "{pool}명 중 **{{count}}명**으로 좁혔어요."
NOT_FOUND = "조건에 맞는 지원자를 찾지 못했어요. 선택 지원자는 그대로예요."


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
    has_score = route.min_score is not None or route.without_score or route.score_gap
    if not concepts:
        if not has_score:
            return ChatPlan.answer(Intent.CLARIFY, DEFAULT_CLARIFY)
        sources = ["평가 결과", "서류 점수"] if route.score_gap else ["평가 결과"]
        chosen = [(row, notes.get(row.application_id, row.name)) for row in rows]
        return _plan(route, len(pool), chosen, sources)
    raise NotImplementedError("검색 경로는 다음 단계에서 붙인다")


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
