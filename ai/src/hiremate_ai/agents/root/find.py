"""Root 조회 도구의 검색 실행기. 명시적 조건으로 후보를 모으고 근거를 재확인한다.

같은 검색 입력에 같은 후보가 나오도록 순서는 코드가 정한다. 재확인 판정은 같은 입력이면 앞 판정을 다시 쓴다.
결과는 계획 형태로 반환하고 선택 변경은 실행하지 않는다.
"""

from collections.abc import Iterable, Sequence
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from hiremate_ai.agents.guardrails import evidence_source
from hiremate_ai.agents.root.progress import SILENT, Progress
from hiremate_ai.agents.root.stages import StageData, not_yet, stage_data
from hiremate_ai.agents.root.toolkit import RootToolkit, cited_agents, scope_of
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
# 기억하는 재확인 판정 수. 넘으면 오래된 것부터 지운다
JUDGED_LIMIT = 256
EVIDENCE_LENGTH = 48
LIMIT_NOTE = " 조건에 가까운 30명 중에서 골랐어요."
_DOCUMENT_LABELS = {document.label for document in DocumentType}
DEFAULT_CLARIFY = "찾을 직무 조건이나 점수 기준을 알려 주세요."
NOT_UNDERSTOOD = "검색 결과를 확인하지 못했어요. 조건을 좁혀 다시 말씀해 주세요."
LOCKED = "결과를 확정한 전형이라 선택 지원자를 바꿀 수 없어요. 분석이나 요약은 계속 물어볼 수 있어요."
NO_ASSESSMENT = "이 채용에는 평가 전형이 없어요. 서류 점수나 직무 조건으로 찾아 주세요."
EARLIER_SCORE = "앞 평가 전형의 점수는 이 전형에서 불러오지 않았어요. 점수가 없다는 뜻은 아니에요."
REPLACED = "{scope} {pool}명 중 조건에 맞는 **{{count}}명**을 선택했어요."
ADDED = "조건에 맞는 **{count}명**을 선택 지원자에 더했어요."
NARROWED = "{pool}명 중 **{{count}}명**으로 좁혔어요."
NOT_FOUND = "조건에 맞는 지원자를 찾지 못했어요. 선택 지원자는 그대로예요."
# 합격, 불합격한 지원자 안에서 찾기. 결정한 지원자는 선택 지원자에 넣을 수 없어 대화로만 답한다
_DECIDED_LABELS = {Decision.PASS: "합격한", Decision.FAIL: "불합격한"}
DECIDED_FOUND = (
    "{label} 지원자 {pool}명 중 조건에 맞는 사람은 **{count}명**이에요. 결정한 지원자라 선택 지원자는 바꾸지 않았어요."
)
DECIDED_NOT_FOUND = "{label} 지원자 {pool}명 중 조건에 맞는 사람을 찾지 못했어요."
NO_DECIDED = "아직 {label} 지원자가 없어요."
RECHECK_STATUS = "후보 {count}명을 다시 확인하고 있어요"
# 공고 기준 찾기 (기획 18절)
_SECTION_LABELS = {"qualifications": "자격 요건", "preferred": "우대 사항", "both": "자격 요건, 우대 사항"}
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
  다른 업계에서 비슷한 기능을 만든 일, 개인, 학교 프로젝트, 데이터를 분석만 한 일은 그 도메인 경험이 아니다.
- 금융 도메인에는 은행, 증권, 카드, 보험과 간편결제, PG의 결제 및 정산 서비스 재직 경험이 포함된다.
  일반 쇼핑몰에서 외부 결제 API를 연동하거나 모의 결제를 만든 경험만으로 금융권 재직이라고 판정하지 않는다.
- 후보는 블록의 번호(candidate_no)로, 근거는 블록 안 문장 번호(sentence_nos)로 답한다. 문장을 옮겨 쓰지 않는다.
  근거가 된 조건마다 문장 번호를 하나씩 적는다. met=false면 sentence_nos를 비운다."""

CRITERIA_SYSTEM = """너는 채용 담당자가 공고 항목을 기준으로 지원자를 찾을 때,
검색으로 모은 후보가 항목을 하나씩 충족하는지 판정한다.
후보마다 주어진 원문 문장만 보고 판단한다. 문장에 없는 내용을 짐작하지 않는다.

- 항목마다 따로 판정한다. 충족한 항목만 met에 적고, 항목 번호(criterion_no)와 근거 문장 번호(sentence_no)를 하나 단다.
- 도메인 경험은 그 업계의 회사나 서비스에서 일한 경력이다.
  다른 업계에서 비슷한 기능을 만든 일, 개인, 학교 프로젝트, 데이터를 분석만 한 일은 그 도메인 경험이 아니다.
- 금융 도메인에는 은행, 증권, 카드, 보험과 간편결제, PG의 결제 및 정산 서비스 재직 경험이 포함된다.
  일반 쇼핑몰에서 외부 결제 API를 연동하거나 모의 결제를 만든 경험만으로 금융권 재직이라고 판정하지 않는다.
- 기간 조건("3년 이상")은 문장에 기간이 드러날 때만 충족으로 본다.
- 후보는 블록의 번호(candidate_no)로 답하고 문장을 옮겨 쓰지 않는다. 충족한 항목이 없으면 met을 비운다."""


class SearchQuery(BaseModel):
    """검색 도구의 실행 인자. 요청 문장의 의미를 다시 해석하거나 보정하지 않는다."""

    # 모델은 조건이 없을 때도 []와 null을 직접 쓰게 한다. Python 호출의 기본값은 유지한다.
    model_config = ConfigDict(extra="forbid", json_schema_extra={"required": ["concepts", "min_score"]})

    mode: SelectionMode = Field(
        default=SelectionMode.REPLACE,
        description=(
            "새 완결 조건 검색의 기본값은 REPLACE다. 이전 결과나 현재 선택이 있어도 전체에서 새로 찾는다. "
            "사용자가 기존 선택에 더하라고 하면 ADD, 그중이나 선택된 사람 안으로 명시해 좁힐 때만 NARROW"
        ),
    )
    concepts: list[str] = Field(
        default_factory=list,
        description=(
            "지원자가 모두 충족해야 할 직무나 경력 조건. '금융권 경력 있는 사람'은 ['금융 업종 재직 경력']처럼 적는다. "
            "점수는 min_score와 score_source에, 지원자 범위는 pool에 적는다"
        ),
    )
    min_score: int | None = Field(
        default=None,
        description="점수 하한으로 같은 점수도 포함한다. '80점 이상'이면 80. 점수 하한 조건이 없으면 null",
    )
    score_source: Literal["document", "assessment"] = Field(
        default="assessment",
        description="점수 출처. 서류 점수는 document, 현재 평가 전형의 점수나 직무역량 평가 점수는 assessment",
    )
    without_score: bool = Field(default=False, description="score_source의 점수가 입력되지 않은 지원자만 찾으면 true")
    score_gap: bool = Field(
        default=False, description="서류 점수와 현재 평가 점수의 차이가 15점 이상인 지원자를 찾으면 true"
    )
    use_talents: bool = Field(
        default=False,
        description="회사 인재상 가운데 하나 이상을 충족해야 하면 true. 별도 concepts도 모두 충족해야 한다",
    )
    posting_criteria: Literal["none", "qualifications", "preferred", "both"] = Field(
        default="none",
        description="공고 기준. 자격 요건은 qualifications, 우대 사항은 preferred, 둘 다는 both, 사용하지 않으면 none",
    )
    criteria_match: Literal["any", "most", "all"] = Field(
        default="any", description="공고 기준 충족 방식. 하나 이상은 any, 가장 많이 충족하면 most, 모두 충족하면 all"
    )
    decision: Decision = Field(
        default=Decision.PENDING,
        description="검색할 결정 상태. 미결정 안에서 찾으면 PENDING, 합격자는 PASS, 불합격자는 FAIL",
    )


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


def candidate_pool(query: SearchQuery, context: ChatContext, pool: Sequence[UUID] | None = None) -> list[CandidateRow]:
    """명시한 결정의 지원자. 미결정 서류 지원자는 기준선 위만 조회한다.

    명시한 pool이 있으면 그 안에서만 찾는다. pool 없는 좁히기는 화면의 선택 지원자 안에서 찾는다.
    이미 결정한 지원자 조회에는 기준선과 화면 선택을 적용하지 않는다.
    """
    rows = [row for row in context.candidates if row.decision is query.decision]
    if query.decision is Decision.PENDING:
        if context.stage_type is StageType.DOCUMENT:
            rows = [row for row in rows if row.above_line]
        if query.mode is SelectionMode.NARROW and pool is None:
            rows = [row for row in rows if row.selected]
    if pool is not None:
        allowed = set(pool)
        rows = [row for row in rows if row.application_id in allowed]
    return rows


def score_filter(
    query: SearchQuery, context: ChatContext, rows: list[CandidateRow]
) -> tuple[list[CandidateRow], dict[UUID, str]]:
    """점수 조건을 적용하고 지원자별 점수 설명을 붙인다. score는 평가 전형 점수, document_scores는 서류 점수다.

    점수 하한과 미입력 조건에는 명시한 score_source를 사용한다.
    """
    notes: dict[UUID, str] = {}
    on_document = query.score_source == "document"
    if query.min_score is not None:
        minimum = query.min_score
        rows = [row for row in rows if (score := _score(context, row, on_document)) is not None and score >= minimum]
    if query.without_score:
        rows = [row for row in rows if _score(context, row, on_document) is None]
    for row in rows:
        if on_document:
            if (document := context.document_scores.get(row.application_id)) is not None:
                notes[row.application_id] = f"서류 {_points(document)}점"
        elif row.score is not None:
            notes[row.application_id] = f"평가 {_points(row.score)}점"
    if query.score_gap:
        gaps = []
        for row in rows:
            document = context.document_scores.get(row.application_id)
            if row.score is not None and document is not None and abs(row.score - document) >= SCORE_GAP:
                gaps.append((row, row.score, document))
        gaps.sort(key=lambda gap: -abs(gap[1] - gap[2]))
        rows = [row for row, _, _ in gaps]
        for row, score, document in gaps:
            direction = "평가가 지원서보다 높음" if score > document else "지원서에 비해 평가가 낮음"
            notes[row.application_id] = f"평가 {_points(score)}점, 서류 {_points(document)}점, {direction}"
    return rows, notes


async def plan_find(
    llm: LlmClient,
    query: SearchQuery,
    context: ChatContext,
    toolkit: RootToolkit,
    *,
    pool: Sequence[UUID] | None = None,
    progress: Progress = SILENT,
) -> ChatPlan:
    if query.decision is Decision.PENDING and not context.selectable:
        return ChatPlan.answer(Intent.CLARIFY, LOCKED)
    missing = _unavailable_scores(query, context)
    if missing:
        return ChatPlan.answer(Intent.CLARIFY, missing)
    candidates = candidate_pool(query, context, pool)
    decided = _decided(query)
    if decided is not None and not candidates:
        return ChatPlan.answer(Intent.ANSWER, NO_DECIDED.format(label=_DECIDED_LABELS[decided]))
    rows, notes = score_filter(query, context, candidates)
    section = query.posting_criteria
    if section != "none":
        return await _plan_posting(llm, query, context, toolkit, section, candidates, rows, progress)
    conditions = list(query.concepts)
    talents: list[str] = []
    if query.use_talents:
        talents = [f"{talent.title} {talent.description}" for talent in context.company.talents]
    concepts = conditions + talents
    has_score = query.min_score is not None or query.without_score or query.score_gap
    score_sources = _score_sources(query)
    if not concepts:
        if not has_score:
            return ChatPlan.answer(Intent.CLARIFY, DEFAULT_CLARIFY)
        chosen = [(row, notes.get(row.application_id, row.name)) for row in rows]
        return _plan(query, context, len(candidates), chosen, score_sources)

    allowed = {row.application_id: row for row in rows}
    found = await toolkit.search(scope_of(context), concepts, list(allowed))
    matches = [match for match in found if match.application_id in allowed]
    limited = len(matches) > RECHECK_LIMIT
    matches = matches[:RECHECK_LIMIT]
    if not matches:
        return _not_found(query, len(candidates))
    progress.status(RECHECK_STATUS.format(count=len(matches)))
    try:
        verified = await recheck(llm, context, matches, conditions=conditions, talents=talents, memo=toolkit.judged)
    except LlmOutputError:
        return ChatPlan.answer(Intent.CLARIFY, NOT_UNDERSTOOD)
    chosen = [(allowed[application_id], _shorten(evidence[0].sentence)) for application_id, evidence in verified]
    sources = list(dict.fromkeys(sourced.source for _, evidence in verified for sourced in evidence)) + score_sources
    agents = await _agents(
        toolkit, context, [(application_id, sourced) for application_id, evidence in verified for sourced in evidence]
    )
    plan = _plan(query, context, len(candidates), chosen, sources, agents)
    if limited and chosen:
        plan = plan.model_copy(update={"message": plan.message + LIMIT_NOTE})
    return plan


async def _plan_posting(
    llm: LlmClient,
    query: SearchQuery,
    context: ChatContext,
    toolkit: RootToolkit,
    section: Literal["qualifications", "preferred", "both"],
    pool: list[CandidateRow],
    rows: list[CandidateRow],
    progress: Progress,
) -> ChatPlan:
    """공고의 자격 요건, 우대 사항으로 찾는다. 항목은 공고에서 코드가 꺼내고, 충족한 항목 수로 고른다.

    HR이 따로 말한 조건은 반드시 충족해야 한다. 근거 문장이 원문에 있는 항목만 충족으로 센다 (규칙 7).
    """
    label = _SECTION_LABELS[section]
    posting = context.posting
    items = {"qualifications": posting.qualifications, "preferred": posting.preferred}.get(
        section, [*posting.qualifications, *posting.preferred]
    )
    if not items:
        return ChatPlan.answer(Intent.CLARIFY, NO_POSTING_ITEMS.format(label=label))
    required = list(query.concepts)
    criteria = [*items, *required]
    allowed = {row.application_id: row for row in rows}
    found = await toolkit.search(scope_of(context), criteria, list(allowed))
    matches = [match for match in found if match.application_id in allowed]
    limited = len(matches) > RECHECK_LIMIT
    matches = matches[:RECHECK_LIMIT]
    if not matches:
        return _not_found(query, len(pool))
    progress.status(RECHECK_STATUS.format(count=len(matches)))
    try:
        judged = await recheck_criteria(llm, context, matches, items, required, toolkit.judged)
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
    match_mode = query.criteria_match
    if match_mode == "all" and best < n:
        if not best:
            return _not_found(query, len(pool))
        return ChatPlan.answer(Intent.ANSWER, NONE_ALL.format(label=label, n=n, k=best))
    keep = n if match_mode == "all" else best if match_mode == "most" else 1
    kept = sorted((entry for entry in scored if entry[1] >= keep), key=lambda entry: -entry[1])
    chosen = [
        (allowed[application_id], f"{label} {count}/{n}, {_shorten(_first(met).sentence)}")
        for application_id, count, met in kept
    ]
    sources = list(dict.fromkeys(sourced.source for _, _, met in kept for sourced in met.values())) + [POSTING_SOURCE]
    agents = await _agents(
        toolkit, context, [(application_id, sourced) for application_id, _, met in kept for sourced in met.values()]
    )
    plan = _plan(query, context, len(pool), chosen, sources, agents)
    if not chosen:
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
    memo: dict[str, dict[str, Any]],
) -> list[tuple[UUID, dict[int, SourcedSentence]]]:
    """후보마다 충족한 항목(0부터 센 번호)과 그 근거 문장. 검색 순서를 지킨다.

    모델은 항목, 후보, 문장을 번호로만 답한다. 제출 문서 문장은 원문에 있는지 한 번 더 확인한다 (규칙 7).
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
    user = f"요청: {context.message}\n{data_block('criteria', f'공고 항목:\n{listed}')}\n\n{blocks}"
    result = await _judge(llm, memo, CriteriaResult, f"{CRITERIA_SYSTEM}\n\n{UNTRUSTED_RULE}", user)
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
    memo: dict[str, dict[str, Any]],
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
        parts.append(
            data_block(
                "talents", "인재상 (하나 이상 드러나야 한다):\n" + "\n".join(f"- {talent}" for talent in talents)
            )
        )
    user = "\n".join(parts) + f"\n\n{blocks}"
    result = await _judge(llm, memo, RecheckResult, f"{RECHECK_SYSTEM}\n\n{UNTRUSTED_RULE}", user)
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


async def _judge[T: BaseModel](
    llm: LlmClient, memo: dict[str, dict[str, Any]], output: type[T], system: str, user: str
) -> T:
    """재확인 모델 판정. 같은 입력(지시문, 요청, 조건, 후보 문장)이면 기억한 앞 판정을 다시 쓴다.

    모델은 temperature 0에서도 근거가 애매한 후보의 판정을 실행마다 바꾼다. 기억하면 같은 질문에 같은 후보가 나온다.
    후보 문장이나 범위가 바뀌면 입력이 달라져 다시 판정한다. 판정에는 번호만 있고 문서 글은 없다.
    """
    key = sha256(f"{output.__name__}\n{system}\n{user}".encode()).hexdigest()
    # 다시 쓴 판정은 꺼냈다 넣어 가장 최근 것으로 둔다
    saved = memo.pop(key, None)
    if saved is not None:
        result = output.model_validate(saved)
    else:
        result = await llm.structured(output, agent="root", system=system, user=user)
    memo[key] = result.model_dump(mode="json")
    while len(memo) > JUDGED_LIMIT:
        del memo[next(iter(memo))]
    return result


def _in_source(context: ChatContext, application_id: UUID, sourced: SourcedSentence) -> bool:
    """제출 문서에서 왔다는 문장은 그 지원자 문서에 실제로 있어야 한다.

    다른 출처(평가 결과 등)는 검색 도구가 보증한다.
    """
    if sourced.source not in _DOCUMENT_LABELS:
        return True
    return evidence_source(sourced.sentence, context.documents.get(application_id, [])) is not None


async def _agents(
    toolkit: RootToolkit, context: ChatContext, cited: Iterable[tuple[UUID, SourcedSentence]]
) -> list[str]:
    """찾기 근거를 낸 분석 Agent. 프로필 검색이 돌려준 문장이면 그 항목을 만든 Agent다."""
    pairs = [(application_id, sourced.sentence) for application_id, sourced in cited]
    recorded = await toolkit.evidence(scope_of(context), [application_id for application_id, _ in pairs])
    return cited_agents(recorded, pairs)


def _plan(
    query: SearchQuery,
    context: ChatContext,
    pool_size: int,
    chosen: list[tuple[CandidateRow, str]],
    sources: list[str],
    agents: Sequence[str] = (),
) -> ChatPlan:
    """찾은 지원자로 선택 지원자 변경 명령을 낸다. 결정한 지원자 안에서 찾았으면 선택 지원자를 바꾸지 않고 답한다."""
    if not chosen:
        return _not_found(query, pool_size)
    decided = _decided(query)
    if decided is not None:
        # 선택 지원자처럼 따로 볼 곳이 없어 찾은 사람을 모두 항목으로 보여 준다
        found = [
            ChatItem(application_id=row.application_id, label=row.name, text=text, status=None) for row, text in chosen
        ]
        message = DECIDED_FOUND.format(label=_DECIDED_LABELS[decided], pool=pool_size, count=len(chosen))
        return ChatPlan.answer(Intent.ANSWER, message, found, sources, agents)
    mode = query.mode
    scope = "기준선 위 미결정 지원자" if context.stage_type is StageType.DOCUMENT else "미결정 지원자"
    message = {
        SelectionMode.REPLACE: REPLACED.format(scope=scope, pool=pool_size),
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
        agents=list(agents),
        question_targets=[],
        question_focus={},
    )


def _decided(query: SearchQuery) -> Decision | None:
    """이미 결정한 지원자 안에서 조회하는 검색이면 그 결정이다."""
    return query.decision if query.decision in _DECIDED_LABELS else None


def _not_found(query: SearchQuery, pool_size: int) -> ChatPlan:
    decided = _decided(query)
    if decided is None:
        return ChatPlan.answer(Intent.ANSWER, NOT_FOUND)
    return ChatPlan.answer(Intent.ANSWER, DECIDED_NOT_FOUND.format(label=_DECIDED_LABELS[decided], pool=pool_size))


def _unavailable_scores(query: SearchQuery, context: ChatContext) -> str:
    uses_score = query.min_score is not None or query.without_score
    if not query.score_gap and not (uses_score and query.score_source == "assessment"):
        return ""
    match stage_data(context, StageType.ASSESSMENT):
        case StageData.CURRENT:
            return ""
        case StageData.EARLIER:
            return EARLIER_SCORE
        case StageData.LATER:
            return not_yet(context, StageType.ASSESSMENT)
        case StageData.NONE:
            return NO_ASSESSMENT


def _points(value: float) -> str:
    return f"{value:g}"


def _score(context: ChatContext, row: CandidateRow, on_document: bool) -> float | None:
    return context.document_scores.get(row.application_id) if on_document else row.score


def _score_sources(query: SearchQuery) -> list[str]:
    """명시적 점수 조건이 사용한 출처."""
    has_filter = query.min_score is not None or query.without_score
    return [
        source
        for source, used in (
            ("평가 결과", query.score_gap or (has_filter and query.score_source == "assessment")),
            ("서류 점수", query.score_gap or (has_filter and query.score_source == "document")),
        )
        if used
    ]


def _shorten(text: str) -> str:
    trimmed = " ".join(text.split())
    return trimmed if len(trimmed) <= EVIDENCE_LENGTH else trimmed[: EVIDENCE_LENGTH - 1] + "…"
