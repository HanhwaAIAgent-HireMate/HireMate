"""Index an accepted scoped document using the internal BGE embedding service."""

import hashlib
import json
import math
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.chunks import embedding_chunks
from hiremate_ai.contract import DocumentIndexRequest, DocumentIndexResult
from hiremate_ai.db.document_index import DocumentIndex, DocumentIndexChunk
from hiremate_ai.tools.profile_search import ProfileEmbedder
from hiremate_ai.tools.scope import ToolScope


class DocumentIndexScopeError(ValueError):
    """A document cannot move between application or tenant scopes."""


async def index_document(
    session: AsyncSession, embedder: ProfileEmbedder, payload: DocumentIndexRequest, *, model: str
) -> DocumentIndexResult:
    """Serialize even first insertion and preserve the old index on any failure.

    Caller owns the transaction. No partial vectors or activation are committed here.
    """
    request = payload.request
    content_hash = hashlib.sha256(
        json.dumps(payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    await _lock_document(session, request.document_id)
    existing = await session.scalar(
        select(DocumentIndex)
        .where(DocumentIndex.document_id == request.document_id)
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if (existing.company_id, existing.recruitment_id, existing.application_id) != (
            request.company_id,
            request.recruitment_id,
            request.application_id,
        ):
            raise DocumentIndexScopeError("Document index scope mismatch")
        if existing.revision > request.revision:
            return DocumentIndexResult(document_id=request.document_id, revision=request.revision, status="STALE")
        if existing.revision == request.revision and existing.content_hash != content_hash:
            raise ValueError("Accepted document content changed without a revision change")
        if existing.revision == request.revision and existing.model == model:
            return DocumentIndexResult(document_id=request.document_id, revision=request.revision, status="UNCHANGED")
    chunks = embedding_chunks(payload.document)
    vectors = await _embed_texts(embedder, [chunk.text for chunk in chunks])
    if existing is None:
        existing = DocumentIndex(
            document_id=request.document_id,
            company_id=request.company_id,
            recruitment_id=request.recruitment_id,
            application_id=request.application_id,
            revision=request.revision,
            content_hash=content_hash,
            document_type=request.document_type.value,
            sources=[source.model_dump(mode="json") for source in request.sources],
            model=model,
        )
        session.add(existing)
        await session.flush()
    else:
        await session.execute(delete(DocumentIndexChunk).where(DocumentIndexChunk.document_id == request.document_id))
        existing.revision = request.revision
        existing.model = model
        existing.content_hash = content_hash
        existing.document_type = request.document_type.value
        existing.sources = [source.model_dump(mode="json") for source in request.sources]
    for ordinal, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        session.add(
            DocumentIndexChunk(
                document_id=request.document_id,
                ordinal=ordinal,
                revision=request.revision,
                model=model,
                block_ids=chunk.block_ids,
                source_ids=chunk.source_ids,
                section_path=chunk.section_path,
                text=chunk.text,
                embedding=vector,
            )
        )
    await session.flush()
    return DocumentIndexResult(document_id=request.document_id, revision=request.revision, status="INDEXED")


async def _lock_document(session: AsyncSession, document_id: UUID) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"document-index:{document_id}"},
    )


async def _embed_texts(embedder: ProfileEmbedder, values: Sequence[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(values), 4):
        batch = list(values[start : start + 4])
        found = await embedder.embed(batch)
        if len(found) != len(batch) or any(
            len(vector) != 1024 or not all(math.isfinite(value) for value in vector) or not any(vector)
            for vector in found
        ):
            raise ValueError("Invalid document embedding dimensions, count or values")
        vectors.extend(found)
    return vectors


async def reembed_document(
    session: AsyncSession,
    embedder: ProfileEmbedder,
    scope: ToolScope,
    document_id: UUID,
    expected_revision: int,
    *,
    model: str,
) -> None:
    """Reembed the same accepted revision without normalization or backend work.

    The caller owns the transaction. A replacement that won the shared document
    lock makes an old repair obsolete. All vectors validate before activation.
    """
    await _lock_document(session, document_id)
    current = await session.scalar(
        select(DocumentIndex)
        .where(
            DocumentIndex.document_id == document_id,
            DocumentIndex.company_id == scope.company_id,
            DocumentIndex.recruitment_id == scope.recruitment_id,
            DocumentIndex.application_id.in_(scope.application_ids),
        )
        .execution_options(populate_existing=True)
    )
    if current is None or current.revision != expected_revision or current.model == model:
        return
    chunks = list(
        await session.scalars(
            select(DocumentIndexChunk)
            .where(
                DocumentIndexChunk.document_id == document_id,
                DocumentIndexChunk.revision == current.revision,
                DocumentIndexChunk.model == current.model,
            )
            .order_by(DocumentIndexChunk.ordinal)
            .execution_options(populate_existing=True)
        )
    )
    vectors = await _embed_texts(embedder, [chunk.text for chunk in chunks])
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = vector
        chunk.model = model
    current.model = model
    await session.flush()
