"""Search active document vectors and return exact stored parser sources."""

import asyncio
import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.analysis.application.index import reembed_document
from hiremate_ai.agents.guardrails import blocked_attribute, personal_fact
from hiremate_ai.contract import DocumentSource, DocumentType
from hiremate_ai.db.document_index import DocumentIndex, DocumentIndexChunk
from hiremate_ai.ncs_search.reference import NcsUnavailable
from hiremate_ai.tools.candidates import CandidateMatch, SearchResults, SourcedSentence
from hiremate_ai.tools.profile_search import ProfileEmbedder
from hiremate_ai.tools.scope import ToolScope

logger = logging.getLogger(__name__)
MIN_SIMILARITY = 0.35
CHUNKS_PER_CONCEPT = 3


@dataclass(frozen=True)
class DocumentProvenance:
    company_id: UUID
    recruitment_id: UUID
    application_id: UUID
    document_id: UUID
    revision: int
    block_ids: tuple[str, ...]
    source_id: str
    page: int | None
    original_text: str


@dataclass(frozen=True, kw_only=True)
class DocumentSentence(SourcedSentence):
    """Trusted search output. Metadata stays outside the model's editable output."""

    provenance: DocumentProvenance

    def belongs_to(self, scope: ToolScope, application_id: UUID) -> bool:
        original = self.provenance
        return (
            application_id in scope.application_ids
            and original.application_id == application_id
            and original.company_id == scope.company_id
            and original.recruitment_id == scope.recruitment_id
            and bool(self.sentence.strip())
            and self.sentence in original.original_text
            and bool(original.block_ids)
            and bool(original.source_id)
        )


def document_embedding_search(
    sessions: async_sessionmaker[AsyncSession], embedder: ProfileEmbedder, *, model: str
) -> "DocumentEmbeddingSearch":
    return DocumentEmbeddingSearch(sessions, embedder, model=model)


class DocumentEmbeddingSearch:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], embedder: ProfileEmbedder, *, model: str) -> None:
        self._sessions = sessions
        self._embedder = embedder
        self._model = model
        self._pending: dict[UUID, asyncio.Task[None]] = {}
        self._gate = asyncio.Semaphore(2)

    async def __call__(self, scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        order = [candidate for candidate in dict.fromkeys(pool) if candidate in scope.application_ids]
        if (
            not order
            or not any(concept.strip() for concept in concepts)
            or any(blocked_attribute(concept) for concept in concepts)
        ):
            return []
        repairs: list[tuple[UUID, int]] = []
        matches: list[CandidateMatch] = []
        warnings: list[str] = []
        try:
            async with self._sessions() as session:
                repairs = list(
                    (
                        await session.execute(
                            select(DocumentIndex.document_id, DocumentIndex.revision).where(
                                DocumentIndex.company_id == scope.company_id,
                                DocumentIndex.recruitment_id == scope.recruitment_id,
                                DocumentIndex.application_id.in_(order),
                                DocumentIndex.model != self._model,
                            )
                        )
                    ).all()
                )
                matches = await search_document_embeddings(
                    session, self._embedder, scope, concepts, order, model=self._model
                )
        except (NcsUnavailable, SQLAlchemyError, TimeoutError, ValueError):
            logger.warning("지원 문서 검색을 완료하지 못했습니다", exc_info=True)
            warnings.append("지원 문서 의미 검색을 완료하지 못해 다른 검색 결과를 보여 드려요.")
        if repairs:
            warnings.append("지원 문서 임베딩 모델을 갱신하고 있어 일부 의미 검색 결과가 준비되지 않았어요.")
        for document_id, revision in repairs:
            self._schedule(scope, document_id, revision)
        return SearchResults(matches, warnings=warnings)

    def _schedule(self, scope: ToolScope, document_id: UUID, revision: int) -> None:
        if document_id in self._pending:
            return
        task = asyncio.create_task(self._repair(scope, document_id, revision))
        self._pending[document_id] = task
        task.add_done_callback(lambda _: self._pending.pop(document_id, None))

    async def _repair(self, scope: ToolScope, document_id: UUID, revision: int) -> None:
        try:
            async with self._gate, self._sessions() as session, session.begin():
                await reembed_document(session, self._embedder, scope, document_id, revision, model=self._model)
        except (NcsUnavailable, SQLAlchemyError, TimeoutError, ValueError):
            logger.warning("지원 문서 임베딩 모델을 갱신하지 못했습니다", exc_info=True)

    async def wait_pending(self) -> None:
        if self._pending:
            await asyncio.gather(*list(self._pending.values()))


async def search_document_embeddings(
    session: AsyncSession,
    embedder: ProfileEmbedder,
    scope: ToolScope,
    concepts: Sequence[str],
    pool: Sequence[UUID],
    *,
    model: str,
) -> list[CandidateMatch]:
    """The backend's stage membership and candidate pool constrain every vector query.

    Only the active index revision/model can join its chunks. Original quotations
    come from that same document's stored sources, never from contextual chunk text.
    """
    criteria = [concept for concept in concepts if concept.strip()]
    order = [candidate for candidate in dict.fromkeys(pool) if candidate in scope.application_ids]
    if not criteria or not order or any(blocked_attribute(concept) for concept in criteria):
        return []
    vectors: list[list[float]] = []
    for start in range(0, len(criteria), 4):
        batch = criteria[start : start + 4]
        embedded = await embedder.embed(batch)
        if len(embedded) != len(batch) or any(
            len(vector) != 1024 or not all(math.isfinite(value) for value in vector) or not any(vector)
            for vector in embedded
        ):
            raise ValueError("Invalid document query embeddings")
        vectors.extend(embedded)
    sentences: dict[UUID, list[SourcedSentence]] = {}
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
                DocumentIndexChunk.model == DocumentIndex.model,
                DocumentIndexChunk.revision == DocumentIndex.revision,
                distance <= 1 - MIN_SIMILARITY,
            )
            .order_by(distance, DocumentIndex.document_id, DocumentIndexChunk.ordinal)
        )
        selected: dict[UUID, int] = {}
        for document, chunk in rows:
            candidate = document.application_id
            if selected.get(candidate, 0) >= CHUNKS_PER_CONCEPT:
                continue
            originals = _originals(document, chunk)
            if not originals:
                continue
            selected[candidate] = selected.get(candidate, 0) + 1
            kept = sentences.setdefault(candidate, [])
            kept.extend(original for original in originals if original not in kept)
        for candidate in selected:
            hits[candidate] = hits.get(candidate, 0) + 1
    return sorted(
        [CandidateMatch(candidate, sentences[candidate], hits[candidate]) for candidate in order if candidate in hits],
        key=lambda match: -match.hits,
    )


def _originals(document: DocumentIndex, chunk: DocumentIndexChunk) -> list[DocumentSentence]:
    sources = {source.id: source for source in (DocumentSource.model_validate(value) for value in document.sources)}
    if not chunk.block_ids or not chunk.source_ids or any(source_id not in sources for source_id in chunk.source_ids):
        return []
    found: list[DocumentSentence] = []
    body = chunk.text
    context = " > ".join(chunk.section_path) + "\n"
    if chunk.section_path and body.startswith(context):
        body = body[len(context) :]
    body = re.sub(r"^행 \d+ 열 \d+ .*?: ", "", body, count=1, flags=re.DOTALL)
    compact_body = "".join(body.split())

    def overlap(source_id: str) -> int:
        original = "".join(sources[source_id].text.split())
        return SequenceMatcher(None, compact_body, original, autojunk=False).find_longest_match().size

    # Ancestor headings and a table's other rows share the chunk's provenance.
    # Put the source for this matched body first before Root applies its bound.
    ranked_sources = sorted(dict.fromkeys(chunk.source_ids), key=overlap, reverse=True)
    for source_id in ranked_sources:
        source = sources[source_id]
        positions = [index for index, character in enumerate(source.text) if not character.isspace()]
        compact_source = "".join(source.text[index] for index in positions)
        match = SequenceMatcher(None, compact_body, compact_source, autojunk=False).find_longest_match()
        if not match.size:
            continue
        start, end = positions[match.b], positions[match.b + match.size - 1] + 1
        anchor = source.text[start:end]
        line_start = source.text.rfind("\n", 0, start) + 1
        line_end = source.text.find("\n", end)
        sentence = source.text[line_start : line_end if line_end >= 0 else len(source.text)].strip()
        if len(sentence) > 1800 or personal_fact(sentence):
            sentence = anchor
        if personal_fact(sentence):
            continue
        found.append(
            DocumentSentence(
                sentence=sentence,
                source=DocumentType(document.document_type).label,
                anchor=anchor if anchor != sentence else None,
                provenance=DocumentProvenance(
                    company_id=document.company_id,
                    recruitment_id=document.recruitment_id,
                    application_id=document.application_id,
                    document_id=document.document_id,
                    revision=document.revision,
                    block_ids=tuple(chunk.block_ids),
                    source_id=source.id,
                    page=source.page,
                    original_text=source.text,
                ),
            )
        )
    return found
