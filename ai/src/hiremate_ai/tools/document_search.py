"""정제 문서 임베딩에서 현재 전형의 지원자만 검색한다."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.contract import DocumentType
from hiremate_ai.db.document_index import DocumentIndex, DocumentIndexChunk
from hiremate_ai.ncs_search.reference import NcsUnavailable
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch, SearchResults, SourcedSentence
from hiremate_ai.tools.embedding import Embedder, valid_vector
from hiremate_ai.tools.scope import ToolScope

logger = logging.getLogger(__name__)
MIN_SIMILARITY = 0.35


@dataclass(frozen=True)
class DocumentProvenance:
    company_id: UUID
    recruitment_id: UUID
    application_id: UUID
    document_id: UUID
    revision: int
    blind: bool
    block_id: str
    pages: tuple[int, ...]
    evidence: str


@dataclass(frozen=True, kw_only=True)
class DocumentSentence(SourcedSentence):
    provenance: DocumentProvenance

    def belongs_to(self, scope: ToolScope, application_id: UUID) -> bool:
        p = self.provenance
        chat = getattr(scope, "chat", None)
        blind = bool(chat.posting.blind) if chat is not None else False
        return (
            p.company_id == scope.company_id
            and p.recruitment_id == scope.recruitment_id
            and p.blind == blind
            and p.application_id == application_id
            and application_id in scope.application_ids
            and bool(p.block_id)
            and bool(self.sentence.strip())
            and self.sentence == p.evidence
        )


async def search_document_embeddings(
    session: AsyncSession,
    embedder: Embedder,
    scope: ToolScope,
    concepts: Sequence[str],
    pool: Sequence[UUID],
    *,
    model: str,
) -> list[CandidateMatch]:
    order = [item for item in dict.fromkeys(pool) if item in scope.application_ids]
    criteria = [item for item in concepts if item.strip()]
    if not order or not criteria or any(blocked_attribute(item) for item in criteria):
        return []
    chat = getattr(scope, "chat", None)
    blind = bool(chat.posting.blind) if chat is not None else False
    vectors = await embedder.embed(criteria)
    if len(vectors) != len(criteria) or any(not valid_vector(vector) for vector in vectors):
        raise ValueError("검색 임베딩이 올바르지 않다")
    found: dict[UUID, list[SourcedSentence]] = {}
    hits: dict[UUID, int] = {}
    for vector in vectors:
        distance = DocumentIndexChunk.embedding.cosine_distance(vector)
        rows = await session.execute(
            select(DocumentIndex, DocumentIndexChunk)
            .join(DocumentIndexChunk, DocumentIndexChunk.document_id == DocumentIndex.document_id)
            .where(
                DocumentIndex.company_id == scope.company_id,
                DocumentIndex.recruitment_id == scope.recruitment_id,
                DocumentIndex.application_id.in_(order),
                DocumentIndex.model == model,
                DocumentIndex.blind == blind,
                distance <= 1 - MIN_SIMILARITY,
            )
            .order_by(distance, DocumentIndex.document_id, DocumentIndexChunk.ordinal)
        )
        selected: dict[UUID, int] = {}
        for index, chunk in rows:
            owner = index.application_id
            if selected.get(owner, 0) >= 3:
                continue
            selected[owner] = selected.get(owner, 0) + 1
            provenance = DocumentProvenance(
                index.company_id,
                index.recruitment_id,
                owner,
                index.document_id,
                index.revision,
                index.blind,
                chunk.block_id,
                tuple(chunk.pages),
                chunk.evidence,
            )
            sentence = DocumentSentence(
                sentence=chunk.evidence, source=DocumentType(index.document_type.upper()).label, provenance=provenance
            )
            entries = found.setdefault(owner, [])
            if sentence not in entries:
                entries.append(sentence)
        for owner in selected:
            hits[owner] = hits.get(owner, 0) + 1
    return sorted(
        (
            CandidateMatch(application_id=owner, sentences=found[owner], hits=hits[owner])
            for owner in order
            if owner in found
        ),
        key=lambda match: -match.hits,
    )


def document_embedding_search(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, *, model: str
) -> CandidateSearch:
    async def search(scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        try:
            async with sessions() as session:
                return await search_document_embeddings(session, embedder, scope, concepts, pool, model=model)
        except (NcsUnavailable, SQLAlchemyError, TimeoutError, ValueError):
            logger.warning("정제 문서 의미 검색을 완료하지 못했습니다", exc_info=True)
            return SearchResults(warnings=["정제 문서 검색을 완료하지 못해 다른 검색 결과를 보여 드려요."])

    return search
