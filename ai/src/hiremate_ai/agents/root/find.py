"""A 지원자 찾기. 후보 범위와 점수 조건은 코드가 정하고, 검색으로 넓게 모은 뒤 재확인으로 좁힌다 (기획 §11, §13).

같은 질문에 같은 후보가 나오도록 순서는 코드가 정한다. 결과는 선택 지원자 변경 명령(FIND)으로만 낸다.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hiremate_ai.agents.guardrails import evidence_source
from hiremate_ai.agents.root.route import DEFAULT_CLARIFY, NOT_UNDERSTOOD, RootRoute, posting_section
from hiremate_ai.agents.root.toolkit import RootToolkit, concept_terms, scope_of
from hiremate_ai.agents.root.types import (
    CandidateRow,
    ChatContext,
    ChatItem,
    ChatPlan,
    Decision,
    Intent,
    SelectionMode,
)
from hiremate_ai.contract import DocumentType, StageType
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block
from hiremate_ai.tools.candidates import CandidateMatch, SourcedSentence

SCORE_GAP = 15
ITEM_LIMIT = 5
RECHECK_LIMIT = 30
EVIDENCE_LENGTH = 48
LIMIT_NOTE = " 조건에 가까운 30명 중에서 골랐어요."
_DOCUMENT_LABELS = {document.label for document in DocumentType}
# 인재상을 가리키기만 하는 말. 인재상으로 찾을 때 이런 말만 든 조건은 따로 세지 않는다
_TALENT_WORDS = {"인재상", "인재", "가치", "가치관", "핵심가치", "요소"}
REPLACED = "지원자 {total}명 중 조건에 맞는 **{count}명**을 선택했어요."
ADDED = "조건에 맞는 **{count}명**을 선택 지원자에 더했어요."
NARROWED = "{pool}명 중 **{{count}}명**으로 좁혔어요."
NOT_FOUND = "조건에 맞는 지원자를 찾지 못했어요. 선택 지원자는 그대로예요."
# 공고 기준 찾기 (기획 18절)
_SECTION_LABELS = {"qualifications": "자격 요건", "preferred": "우대 사항", "both": "자격 요건 · 우대 사항"}
# 공고 항목을 가리키기만 하는 말. 공고 기준으로 찾을 때 이런 말만 든 조건은 따로 세지 않는다
_POSTING_TERMS = {"공고", "우대", "사항", "자격", "요건", "필수", "조건", "적합", "적합성", "충족", "만족", "부합"}
NO_POSTING_ITEMS = "공고에 {label}이 없어요. 찾을 조건을 직접 말씀해 주세요."
CRITERIA_ALL = " {label} {n}개를 모두 충족한 사람이에요."
CRITERIA_MOST = " {label} {n}개 중 {k}개를 충족해 가장 많이 맞는 사람이에요."
CRITERIA_ANY = " {label} {n}개 중 하나 이상을 충족한 사람이에요. 많이 충족한 순서예요."
NONE_ALL = "{label} {n}개를 모두 충족한 지원자는 없어요. 가장 많이 충족한 사람은 {k}개예요. 선택 지원자는 그대로예요."
POSTING_SOURCE = "공고"

RECHECK_SYSTEM = """너는 채용 담당자의 지원자 찾기 요청에서, 검색으로 모은 후보가 조건을 실제로 충족하는지 판정한다.
후보마다 주어진 원문 문장만 보고 판단한다. 문장에 없는 내용을 짐작하지 않는다.

- "조건 (모두 충족해야 한다)"은 조건마다 근거가 있어야 한다.
- "인재상 (하나 이상 드러나야 한다)"은 그 가운데 하나 이상이 문장에 잘 드러나면 된다.
- 두 부분이 다 있으면 둘 다 만족해야 met=true다.
- 도메인 경험은 그 업계의 회사나 서비스에서 일한 경력이다.
  다른 업계에서 비슷한 기능을 만든 일, 개인 · 학교 프로젝트, 데이터를 분석만 한 일은 그 도메인 경험이 아니다.
- 후보는 블록의 번호(candidate_no)로, 근거는 블록 안 문장 번호(sentence_nos)로 답한다. 문장을 옮겨 쓰지 않는다.
  근거가 된 조건마다 문장 번호를 하나씩 적는다. met=false면 sentence_nos를 비운다."""

CRITERIA_SYSTEM = """너는 채용 담당자가 공고 항목을 기준으로 지원자를 찾을 때,
검색으로 모은 후보가 항목을 하나씩 충족하는지 판정한다.
후보마다 주어진 원문 문장만 보고 판단한다. 문장에 없는 내용을 짐작하지 않는다.

- 항목마다 따로 판정한다. 충족한 항목만 met에 적고, 항목 번호(criterion_no)와 근거 문장 번호(sentence_no)를 하나 단다.
- 도메인 경험은 그 업계의 회사나 서비스에서 일한 경력이다.
  다른 업계에서 비슷한 기능을 만든 일, 개인 · 학교 프로젝트, 데이터를 분석만 한 일은 그 도메인 경험이 아니다.
- 기간 조건("3년 이상")은 문장에 기간이 드러날 때만 충족으로 본다.
- 후보는 블록의 번호(candidate_no)로 답하고 문장을 옮겨 쓰지 않는다. 충족한 항목이 없으면 met을 비운다."""


class RecheckItem(BaseModel):
    candidate_no: int = Field(description="후보 블록의 번호 (no)")
    met: bool = Field(description="조건을 충족하는 근거가 있으면 true")
    sentence_nos: list[int] = Field(default=[], description="근거 문장 번호들 (블록 안의 1, 2, ...)")


class RecheckResult(BaseModel):
    results: list[RecheckItem]


class CriterionEvidence(BaseModel):
    criterion_no: int = Field(description="충족한 항목 번호")
    sentence_no: int = Field(description="그 항목의 근거 문장 번호 (블록 안의 1, 2, ...)")


class CriteriaItem(BaseModel):
    candidate_no: int = Field(description="후보 블록의 번호 (no)")
    met: list[CriterionEvidence] = Field(default=[], description="충족한 항목마다 근거 문장 하나")


class CriteriaResult(BaseModel):
    results: list[CriteriaItem]


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
    section = posting_section(route, context.message)
    if section is not None:
        return await _plan_posting(llm, route, context, toolkit, section, pool, rows)
    conditions = list(route.concepts)
    talents: list[str] = []
    if route.use_talents:
        conditions = [concept for concept in conditions if set(concept_terms(concept)) - _TALENT_WORDS]
        talents = [f"{talent.title} {talent.description}" for talent in context.company.talents]
    concepts = conditions + talents
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
        verified = await recheck(llm, context, matches, conditions=conditions, talents=talents)
    except LlmOutputError:
        return ChatPlan.answer(Intent.CLARIFY, NOT_UNDERSTOOD)
    chosen = [(allowed[application_id], _shorten(evidence[0].sentence)) for application_id, evidence in verified]
    sources = list(dict.fromkeys(sourced.source for _, evidence in verified for sourced in evidence)) + score_sources
    plan = _plan(route, len(pool), chosen, sources)
    if limited and plan.intent is Intent.FIND:
        plan = plan.model_copy(update={"message": plan.message + LIMIT_NOTE})
    return plan


async def _plan_posting(
    llm: LlmClient,
    route: RootRoute,
    context: ChatContext,
    toolkit: RootToolkit,
    section: Literal["qualifications", "preferred", "both"],
    pool: list[CandidateRow],
    rows: list[CandidateRow],
) -> ChatPlan:
    """공고의 자격 요건 · 우대 사항으로 찾는다. 항목은 공고에서 코드가 꺼내고, 충족한 항목 수로 고른다.

    HR이 따로 말한 조건은 반드시 충족해야 한다. 근거 문장이 원문에 있는 항목만 충족으로 센다 (규칙 7).
    """
    label = _SECTION_LABELS[section]
    posting = context.posting
    items = {"qualifications": posting.qualifications, "preferred": posting.preferred}.get(
        section, [*posting.qualifications, *posting.preferred]
    )
    if not items:
        return ChatPlan.answer(Intent.CLARIFY, NO_POSTING_ITEMS.format(label=label))
    required = [concept for concept in route.concepts if set(concept_terms(concept)) - _POSTING_TERMS]
    criteria = [*items, *required]
    allowed = {row.application_id: row for row in rows}
    found = await toolkit.search(scope_of(context), criteria, list(allowed))
    matches = [match for match in found if match.application_id in allowed]
    limited = len(matches) > RECHECK_LIMIT
    matches = matches[:RECHECK_LIMIT]
    if not matches:
        return ChatPlan.answer(Intent.ANSWER, NOT_FOUND)
    try:
        judged = await recheck_criteria(llm, context, matches, items, required)
    except LlmOutputError:
        return ChatPlan.answer(Intent.CLARIFY, NOT_UNDERSTOOD)

    n = len(items)
    scored = []
    for application_id, met in judged:
        if all(index in met for index in range(n, len(criteria))):
            count = sum(index in met for index in range(n))
            if count:
                scored.append((application_id, count, met))
    best = max((count for _, count, _ in scored), default=0)
    match_mode = route.criteria_match
    if match_mode == "all" and best < n:
        message = NONE_ALL.format(label=label, n=n, k=best) if best else NOT_FOUND
        return ChatPlan.answer(Intent.ANSWER, message)
    keep = n if match_mode == "all" else best if match_mode == "most" else 1
    kept = sorted((entry for entry in scored if entry[1] >= keep), key=lambda entry: -entry[1])
    chosen = [
        (allowed[application_id], f"{label} {count}/{n} · {_shorten(_first(met).sentence)}")
        for application_id, count, met in kept
    ]
    sources = list(dict.fromkeys(sourced.source for _, _, met in kept for sourced in met.values())) + [POSTING_SOURCE]
    plan = _plan(route, len(pool), chosen, sources)
    if plan.intent is not Intent.FIND:
        return plan
    note = {"all": CRITERIA_ALL, "most": CRITERIA_MOST, "any": CRITERIA_ANY}[match_mode]
    message = plan.message + note.format(label=label, n=n, k=best) + (LIMIT_NOTE if limited else "")
    return plan.model_copy(update={"message": message})


def _first(met: dict[int, SourcedSentence]) -> SourcedSentence:
    return met[min(met)]


async def recheck_criteria(
    llm: LlmClient,
    context: ChatContext,
    matches: list[CandidateMatch],
    items: list[str],
    required: list[str],
) -> list[tuple[UUID, dict[int, SourcedSentence]]]:
    """후보마다 충족한 항목(0부터 센 번호)과 그 근거 문장. 검색 순서를 지킨다.

    모델은 항목 · 후보 · 문장을 번호로만 답한다. 제출 문서 문장은 원문에 있는지 한 번 더 확인한다 (규칙 7).
    """
    criteria = [*items, *(f"{condition} (반드시 충족)" for condition in required)]
    listed = "\n".join(f"{number}. {criterion}" for number, criterion in enumerate(criteria, start=1))
    blocks = "\n\n".join(
        data_block(
            "candidate",
            "\n".join(
                f"{number}. [{sourced.source}] {sourced.sentence}"
                for number, sourced in enumerate(match.sentences, start=1)
            ),
            no=str(candidate_no),
        )
        for candidate_no, match in enumerate(matches, start=1)
    )
    user = f"요청: {context.message}\n공고 항목:\n{listed}\n\n{blocks}"
    result = await llm.structured(
        CriteriaResult, agent="root", system=f"{CRITERIA_SYSTEM}\n\n{UNTRUSTED_RULE}", user=user
    )
    judged = {item.candidate_no: item for item in result.results}
    verified = []
    for candidate_no, match in enumerate(matches, start=1):
        item = judged.get(candidate_no)
        if item is None:
            continue
        met: dict[int, SourcedSentence] = {}
        for evidence in item.met:
            index, number = evidence.criterion_no - 1, evidence.sentence_no
            if index in met or not 0 <= index < len(criteria) or not 1 <= number <= len(match.sentences):
                continue
            sourced = match.sentences[number - 1]
            if _in_source(context, match.application_id, sourced):
                met[index] = sourced
        if met:
            verified.append((match.application_id, met))
    return verified


async def recheck(
    llm: LlmClient,
    context: ChatContext,
    matches: list[CandidateMatch],
    *,
    conditions: list[str],
    talents: list[str],
) -> list[tuple[UUID, list[SourcedSentence]]]:
    """모델이 충족한다고 판정한 후보와 근거 문장들. 검색 순서를 지킨다.

    모델은 지원자 id와 문장을 옮겨 쓰지 않고 번호로만 답한다.
    제출 문서에서 온 문장은 원문에 있는지 한 번 더 확인한다 (규칙 7).
    """
    blocks = "\n\n".join(
        data_block(
            "candidate",
            "\n".join(
                f"{number}. [{sourced.source}] {sourced.sentence}"
                for number, sourced in enumerate(match.sentences, start=1)
            ),
            no=str(candidate_no),
        )
        for candidate_no, match in enumerate(matches, start=1)
    )
    parts = [f"요청: {context.message}"]
    if conditions:
        parts.append("조건 (모두 충족해야 한다):\n" + "\n".join(f"- {condition}" for condition in conditions))
    if talents:
        parts.append("인재상 (하나 이상 드러나야 한다):\n" + "\n".join(f"- {talent}" for talent in talents))
    user = "\n".join(parts) + f"\n\n{blocks}"
    result = await llm.structured(
        RecheckResult, agent="root", system=f"{RECHECK_SYSTEM}\n\n{UNTRUSTED_RULE}", user=user
    )
    judged = {item.candidate_no: item for item in result.results}
    verified = []
    for candidate_no, match in enumerate(matches, start=1):
        item = judged.get(candidate_no)
        if item is None or not item.met:
            continue
        evidence = [
            match.sentences[number - 1]
            for number in dict.fromkeys(item.sentence_nos)
            if 1 <= number <= len(match.sentences)
            and _in_source(context, match.application_id, match.sentences[number - 1])
        ]
        if evidence:
            verified.append((match.application_id, evidence))
    return verified


def _in_source(context: ChatContext, application_id: UUID, sourced: SourcedSentence) -> bool:
    """제출 문서에서 왔다는 문장은 그 지원자 문서에 실제로 있어야 한다.

    다른 출처(평가 결과 등)는 검색 도구가 보증한다.
    """
    if sourced.source not in _DOCUMENT_LABELS:
        return True
    return evidence_source(sourced.sentence, context.documents.get(application_id, [])) is not None


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
        question_focus={},
    )


def _points(value: float) -> str:
    return f"{value:g}"


def _shorten(text: str) -> str:
    trimmed = " ".join(text.split())
    return trimmed if len(trimmed) <= EVIDENCE_LENGTH else trimmed[: EVIDENCE_LENGTH - 1] + "…"
