"""지원자 프로필 검색 (FR-13, 14). Root Agent의 A 지원자 찾기가 쓰는 검색 함수.

tools.candidates.CandidateSearch 모양을 따른다. (조회 범위, 조건들, 후보 id) → 조건에 걸린 지원자.
- 프로필 항목(내용, 근거 문장)에서 조건 낱말을 찾는다. 원문 전체를 다시 읽지 않는다.
- 확인 필요(CHECK) 항목은 근거로 쓰지 않는다. "결제 도메인은 처음"이 금융 경험으로 잡히지 않게 하기 위해서다.
- 상충 항목과, 분석 Agent가 미확인이라고 적은 경험 항목도 근거로 쓰지 않는다. 기술 목록은 미확인이어도 쓴다.
- 현재 기업 · 채용 · 전형 범위 안의 후보만 본다 (아키텍처 규칙 4).
- 같은 입력에는 늘 같은 순서로 돌려준다: 맞은 조건 수가 많은 순, 같으면 후보 id를 받은 순서.
- 넓게 모으고, 조건을 정말 충족하는지는 Root Agent가 재확인한다.

서류 점수 · 평가 점수 같은 숫자 조건은 Root가 backend 값(ChatContext)으로 거른 뒤 후보 id로 넘긴다.

Root에 연결하는 예
    search = profile_search(session_factory(), terms=concept_terms)
    toolkit = RootToolkit(search=search, ...)
"""

import asyncio
import logging
import math
import re
from collections.abc import Awaitable, Callable, Sequence
from functools import cache
from typing import Protocol
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.guardrails import blocked_attribute, personal_fact
from hiremate_ai.config import settings
from hiremate_ai.contract import DocumentType
from hiremate_ai.db.profile import CandidateProfile, ItemCategory, ProfileItem, Verification
from hiremate_ai.ncs_search.reference import EmbedClient, NcsUnavailable
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch, SearchResults, SourcedSentence
from hiremate_ai.tools.scope import ToolScope

# 조건 하나에 모으는 근거 문장 수. Root의 재확인이 이 가운데 근거를 고른다
SENTENCES_PER_CONCEPT = 3
PROFILE_EMBEDDING_MODEL = "BAAI/bge-m3"
MIN_PROFILE_SIMILARITY = 0.35
EMBEDDING_DIMENSIONS = 1024
logger = logging.getLogger(__name__)

type TermsOf = Callable[[str], list[str]]
"""조건 하나("금융 도메인 경험")를 찾을 낱말들(["금융"])로 바꾸는 함수."""


class ProfileEmbedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


type ProfileIndexer = Callable[[UUID, UUID, UUID], Awaitable[None]]


async def index_profile_safely(
    indexer: ProfileIndexer,
    company_id: UUID,
    recruitment_id: UUID,
    application_id: UUID,
    *,
    budget_seconds: float | None = None,
) -> None:
    try:
        async with asyncio.timeout(budget_seconds):
            await indexer(company_id, recruitment_id, application_id)
    except (NcsUnavailable, TimeoutError, ValueError):
        logger.warning("프로필 임베딩을 만들지 못했습니다", exc_info=True)


class DenseProfileEmbedder:
    def __init__(self, client: EmbedClient) -> None:
        self._client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.dense for vector in await self._client.embed(texts)]


@cache
def get_profile_embedder() -> ProfileEmbedder:
    http = httpx.AsyncClient(timeout=settings.ncs_embed_timeout_seconds)
    return DenseProfileEmbedder(EmbedClient(http, settings.ncs_embed_url))


def profile_indexer(
    sessions: async_sessionmaker[AsyncSession], embedder: ProfileEmbedder, *, model: str | None = None
) -> ProfileIndexer:
    async def index(company_id: UUID, recruitment_id: UUID, application_id: UUID) -> None:
        async with sessions() as session:
            await index_profile_embeddings(
                session, embedder, company_id, recruitment_id, application_id, model=model or settings.ncs_model
            )
            await session.commit()

    return index


def profile_embedding_search(
    sessions: async_sessionmaker[AsyncSession], embedder: ProfileEmbedder, *, model: str
) -> "ProfileEmbeddingSearch":
    return ProfileEmbeddingSearch(sessions, embedder, model=model)


class ProfileEmbeddingSearch:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], embedder: ProfileEmbedder, *, model: str) -> None:
        self._sessions = sessions
        self._embedder = embedder
        self._model = model
        self._indexer = profile_indexer(sessions, embedder, model=model)
        self._pending: dict[tuple[UUID, UUID, UUID], asyncio.Task[None]] = {}
        self._gate = asyncio.Semaphore(2)

    async def __call__(self, scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        order = [candidate for candidate in dict.fromkeys(pool) if candidate in scope.application_ids]
        if not order:
            return []
        async with self._sessions() as session:
            profiles = list(
                await session.scalars(
                    select(CandidateProfile).where(
                        CandidateProfile.company_id == scope.company_id,
                        CandidateProfile.recruitment_id == scope.recruitment_id,
                        CandidateProfile.application_id.in_(order),
                    )
                )
            )
            indexed = {
                profile.application_id
                for profile in profiles
                if (items := [item for item in profile.items if _semantic_candidate(item)])
                and all(
                    _embeddable(item) and item.embedding is not None and item.embedding_model == self._model
                    for item in items
                )
            }
            repair_ids = [
                profile.application_id
                for profile in profiles
                if any(
                    _embeddable(item) and (item.embedding is None or item.embedding_model != self._model)
                    for item in profile.items
                )
            ]
            has_vectors = any(
                item.embedding is not None and item.embedding_model == self._model and _embeddable(item)
                for profile in profiles
                for item in profile.items
            )
            warnings = []
            if len(indexed) != len(order):
                warnings.append("일부 지원자의 프로필 임베딩이 준비되지 않아 의미 검색이 불완전해요.")
            matches: list[CandidateMatch] = []
            if has_vectors:
                try:
                    matches = await search_profile_embeddings(
                        session, self._embedder, scope, concepts, order, model=self._model
                    )
                except (NcsUnavailable, ValueError):
                    warnings = ["의미 검색에 실패해 키워드 검색 결과만 보여 드려요."]
        for application_id in repair_ids:
            self._schedule(scope, application_id)
        return SearchResults(matches, warnings=warnings)

    def _schedule(self, scope: ToolScope, application_id: UUID) -> None:
        key = (scope.company_id, scope.recruitment_id, application_id)
        if key in self._pending:
            return
        task = asyncio.create_task(self._repair(key))
        self._pending[key] = task
        task.add_done_callback(lambda _: self._pending.pop(key, None))

    async def _repair(self, key: tuple[UUID, UUID, UUID]) -> None:
        try:
            async with self._gate:
                await self._indexer(*key)
        except (NcsUnavailable, SQLAlchemyError, ValueError):
            logger.warning("프로필 임베딩을 다시 만들지 못했습니다", exc_info=True)

    async def wait_pending(self) -> None:
        if self._pending:
            await asyncio.gather(*list(self._pending.values()))


async def backfill_profile_embeddings(
    sessions: async_sessionmaker[AsyncSession],
    embedder: ProfileEmbedder,
    company_id: UUID,
    recruitment_id: UUID,
    *,
    model: str = PROFILE_EMBEDDING_MODEL,
) -> int:
    async with sessions() as session:
        candidates = list(
            await session.scalars(
                select(CandidateProfile.application_id)
                .where(CandidateProfile.company_id == company_id, CandidateProfile.recruitment_id == recruitment_id)
                .order_by(CandidateProfile.application_id)
            )
        )
    for application_id in candidates:
        async with sessions() as session:
            await index_profile_embeddings(session, embedder, company_id, recruitment_id, application_id, model=model)
            await session.commit()
    return len(candidates)


async def index_profile_embeddings(
    session: AsyncSession,
    embedder: ProfileEmbedder,
    company_id: UUID,
    recruitment_id: UUID,
    application_id: UUID,
    *,
    model: str = PROFILE_EMBEDDING_MODEL,
) -> None:
    profile = await session.scalar(
        select(CandidateProfile).where(
            CandidateProfile.company_id == company_id,
            CandidateProfile.recruitment_id == recruitment_id,
            CandidateProfile.application_id == application_id,
        )
    )
    if profile is None:
        return
    items = [
        item
        for item in profile.items
        if _embeddable(item) and (item.embedding is None or item.embedding_model != model)
    ]
    for start in range(0, len(items), 4):
        batch = items[start : start + 4]
        vectors = await embedder.embed([f"{item.content}\n{item.evidence or ''}"[:2000] for item in batch])
        if len(vectors) != len(batch) or any(not _valid_vector(vector) for vector in vectors):
            raise ValueError("프로필 임베딩이 올바르지 않습니다")
        for item, vector in zip(batch, vectors, strict=True):
            item.embedding = vector
            item.embedding_model = model
    await session.flush()


async def search_profile_embeddings(
    session: AsyncSession,
    embedder: ProfileEmbedder,
    scope: ToolScope,
    concepts: Sequence[str],
    pool: Sequence[UUID],
    *,
    model: str = PROFILE_EMBEDDING_MODEL,
) -> list[CandidateMatch]:
    criteria = [concept for concept in concepts if concept.strip() and not blocked_attribute(concept)]
    order = [candidate for candidate in dict.fromkeys(pool) if candidate in scope.application_ids]
    if not criteria or not order:
        return []
    vectors = []
    for start in range(0, len(criteria), 4):
        batch = criteria[start : start + 4]
        found = await embedder.embed(batch)
        if len(found) != len(batch) or any(not _valid_vector(vector) for vector in found):
            raise ValueError("검색어 임베딩이 올바르지 않습니다")
        vectors.extend(found)
    profiles = await session.scalars(
        select(CandidateProfile).where(
            CandidateProfile.company_id == scope.company_id,
            CandidateProfile.recruitment_id == scope.recruitment_id,
            CandidateProfile.application_id.in_(order),
        )
    )
    by_id = {profile.application_id: profile for profile in profiles}
    matches: list[CandidateMatch] = []
    for application_id in order:
        profile = by_id.get(application_id)
        if profile is None:
            continue
        items = [
            item
            for item in profile.items
            if _embeddable(item) and item.embedding_model == model and item.embedding is not None
        ]
        sentences: list[SourcedSentence] = []
        hits = 0
        for vector in vectors:
            ranked = sorted(
                ((_cosine(vector, item.embedding), index, item) for index, item in enumerate(items)),
                key=lambda result: (-result[0], result[1]),
            )
            selected = [item for score, _, item in ranked if score >= MIN_PROFILE_SIMILARITY][:SENTENCES_PER_CONCEPT]
            hits += bool(selected)
            for item in selected:
                sentence = SourcedSentence(sentence=item.evidence or item.content, source=item.source)
                if sentence not in sentences:
                    sentences.append(sentence)
        if hits:
            matches.append(CandidateMatch(application_id=application_id, sentences=sentences, hits=hits))
    return sorted(matches, key=lambda match: -match.hits)


def _valid_vector(vector: list[float]) -> bool:
    return len(vector) == EMBEDDING_DIMENSIONS and all(math.isfinite(value) for value in vector) and any(vector)


def _embeddable(item: ProfileItem) -> bool:
    return _semantic_candidate(item) and not personal_fact(f"{item.content}\n{item.evidence or ''}")


def _semantic_candidate(item: ProfileItem) -> bool:
    return _usable(item) and item.category != ItemCategory.QUALIFICATION


def _cosine(left: Sequence[float], right: Sequence[float] | None) -> float:
    if right is None:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return dot / norm if norm else 0.0


_DOCUMENT_LABELS = {document.label for document in DocumentType}
_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z+#.]+")
_PARTICLE = re.compile(r"(이|가|을|를|은|는|도|만|의|과|와|에서|에|로|으로|이랑|랑)$")
# 조건을 말할 때 흔히 붙지만 지원자를 가르지 못하는 말
_STOP_WORDS = {
    "찾아줘",
    "찾아",
    "보여줘",
    "지원자",
    "사람",
    "경험",
    "경험자",
    "있는",
    "관련",
    "도메인",
    "처리",
    "능력",
    "역량",
    "프로젝트",
}


def simple_terms(concept: str) -> list[str]:
    """기본 낱말 나누기. 조사와 흔한 말을 뺀다. Root는 동의어까지 넓히는 자기 함수(concept_terms)를 넘길 수 있다."""
    terms: list[str] = []
    for match in _WORD.finditer(concept):
        word = _PARTICLE.sub("", match.group()).lower()
        if len(word) >= 2 and word not in _STOP_WORDS and word not in terms:
            terms.append(word)
    return terms


async def search_profiles(
    session: AsyncSession,
    scope: ToolScope,
    concepts: Sequence[str],
    pool: Sequence[UUID],
    *,
    terms: TermsOf = simple_terms,
) -> list[CandidateMatch]:
    """프로필에서 조건에 걸린 후보를 찾는다. pool 밖이나 조회 범위 밖의 지원자는 돌려주지 않는다."""
    # 차별 조건은 검색 낱말로 쓰지 않는다 (규칙 6). 요청 차단은 Root가 먼저 한다
    term_sets = [found for found in (terms(concept) for concept in concepts if not blocked_attribute(concept)) if found]
    order = [application_id for application_id in dict.fromkeys(pool) if application_id in scope.application_ids]
    if not term_sets or not order:
        return []

    profiles = await session.scalars(
        select(CandidateProfile).where(
            CandidateProfile.company_id == scope.company_id,
            CandidateProfile.recruitment_id == scope.recruitment_id,
            CandidateProfile.application_id.in_(order),
        )
    )
    by_id = {profile.application_id: profile for profile in profiles}

    matches = []
    for application_id in order:
        profile = by_id.get(application_id)
        if profile is None:
            continue  # 아직 분석 전이라 프로필이 없다
        # 한 번에 저장한 항목은 저장 시각이 같으므로 id로 순서를 고정해 늘 같은 문장 순서가 나오게 한다
        items = sorted((item for item in profile.items if _usable(item)), key=lambda item: (item.created_at, item.id))
        sentences: list[SourcedSentence] = []
        hits = 0
        for term_set in term_sets:
            found = _best(items, term_set)
            hits += bool(found)
            sentences += [sentence for sentence in found if sentence not in sentences]
        if hits:
            matches.append(CandidateMatch(application_id=application_id, sentences=sentences, hits=hits))
    # sorted는 같은 값의 순서를 지키므로 맞은 조건 수가 같으면 후보 순서 그대로다
    return sorted(matches, key=lambda match: -match.hits)


def profile_search(sessions: async_sessionmaker[AsyncSession], *, terms: TermsOf = simple_terms) -> CandidateSearch:
    """Root의 RootToolkit.search에 넣을 검색 함수를 만든다. 부를 때마다 세션을 열고 닫는다."""

    async def search(scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        async with sessions() as session:
            return await search_profiles(session, scope, concepts, pool, terms=terms)

    return search


def _usable(item: ProfileItem) -> bool:
    """검색 근거로 쓸 수 있는 항목. 확인 필요 · 상충 항목과, 문서 출처인데 근거 문장이 없는 항목은 뺀다.

    Root의 재확인은 문서 출처 문장이 원문에 있는지 다시 보므로, 문서 출처 항목은 원문 근거 문장을 돌려줘야 한다.
    """
    # 1) 확인 필요 분류는 내용이 조건과 맞아 보여도 쓰지 않는다
    if item.category == ItemCategory.CHECK:
        return False
    # 2) 자료끼리 어긋나는 항목은 쓰지 않는다
    if item.verification == Verification.CONFLICT:
        return False
    # 3) 근거 문장이 있는데도 미확인인 경험은 팀 성과이거나 본인 역할이 불분명한 것이라 쓰지 않는다.
    #    기술 목록은 지원자가 자기 기술로 적은 것이라 본인 여부를 따질 게 없다. 기술로 찾을 수 있게 쓴다
    if (
        item.verification == Verification.UNCONFIRMED
        and item.evidence is not None
        and item.category != ItemCategory.SKILL
    ):
        return False
    # 4) 평가 결과처럼 문서가 아닌 출처는 근거 문장이 없어도 내용으로 찾는다 (전과 같음)
    return item.evidence is not None or item.source not in _DOCUMENT_LABELS


def _best(items: list[ProfileItem], term_set: list[str]) -> list[SourcedSentence]:
    """조건 낱말이 많이 든 항목 순으로 근거 문장 몇 개. 같으면 저장된 순서."""
    scored = []
    for index, item in enumerate(items):
        text = f"{item.content} {item.evidence or ''}".lower()
        count = sum(term in text for term in term_set)
        if count:
            scored.append((-count, index, item))
    return [
        SourcedSentence(sentence=item.evidence or item.content, source=item.source)
        for _, _, item in sorted(scored, key=lambda scored_item: scored_item[:2])[:SENTENCES_PER_CONCEPT]
    ]
