"""저장된 정제 문서의 검색 벡터를 버전별로 교체한다."""

from hashlib import sha256

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.chunks import document_chunks
from hiremate_ai.contract import DocumentIndexRequest, DocumentIndexResult
from hiremate_ai.db.document_index import DocumentIndex, DocumentIndexChunk
from hiremate_ai.tools.embedding import Embedder, valid_vector


async def index_document(
    session: AsyncSession, embedder: Embedder, request: DocumentIndexRequest, *, model: str
) -> DocumentIndexResult:
    document_id = request.document.document.id
    # 같은 문서의 최초 생성과 교체 작업도 직렬화해 늦은 과거 결과가 새 결과를 덮지 않게 한다.
    await session.execute(text("select pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": str(document_id)})
    existing = await session.scalar(select(DocumentIndex).where(DocumentIndex.document_id == document_id))
    if existing is not None and (
        existing.company_id != request.company_id
        or existing.recruitment_id != request.recruitment_id
        or existing.application_id != request.application_id
    ):
        raise ValueError("문서의 기업 또는 채용 범위가 다르다")
    if existing is not None and existing.revision > request.revision:
        return DocumentIndexResult(document_id=document_id, revision=request.revision, status="STALE")
    digest = sha256(request.model_dump_json(by_alias=True).encode()).hexdigest()
    if existing is not None and existing.revision == request.revision and existing.content_hash != digest:
        raise ValueError("동일한 문서 버전의 내용이 다르다")
    if existing is not None and existing.revision == request.revision and existing.model == model:
        return DocumentIndexResult(document_id=document_id, revision=request.revision, status="DONE")
    chunks = document_chunks(request.document, blind=request.blind, applicant_name=request.applicant_name)
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), 4):
        batch = chunks[start : start + 4]
        found = await embedder.embed([chunk.text for chunk in batch])
        if len(found) != len(batch) or any(not valid_vector(vector) for vector in found):
            raise ValueError("문서 임베딩이 올바르지 않다")
        vectors.extend(found)
    if existing is None:
        existing = DocumentIndex(
            document_id=document_id,
            company_id=request.company_id,
            recruitment_id=request.recruitment_id,
            application_id=request.application_id,
            revision=request.revision,
            blind=request.blind,
            content_hash=digest,
            document_type=request.document.document.type,
            model=model,
        )
        session.add(existing)
        await session.flush()
    else:
        await session.execute(delete(DocumentIndexChunk).where(DocumentIndexChunk.document_id == document_id))
        existing.revision = request.revision
        existing.blind = request.blind
        existing.content_hash = digest
        existing.document_type = request.document.document.type
        existing.model = model
    session.add_all(
        [
            DocumentIndexChunk(
                document_id=document_id,
                ordinal=i,
                block_id=chunk.block_id,
                pages=list(chunk.pages),
                text=chunk.text,
                evidence=chunk.evidence,
                embedding=vector,
            )
            for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
    )
    await session.flush()
    return DocumentIndexResult(document_id=document_id, revision=request.revision, status="DONE")
