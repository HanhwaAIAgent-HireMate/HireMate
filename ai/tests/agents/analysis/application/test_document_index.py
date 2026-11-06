import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hiremate_ai.agents.analysis.application.index import DocumentIndexScopeError, index_document
from hiremate_ai.contract import DocumentIndexRequest, NormalizedDocument
from hiremate_ai.db.document_index import DocumentIndex, DocumentIndexChunk


class Embedder:
    def __init__(self) -> None:
        self.calls = 0
        self.invalid = False
        self.inputs: list[str] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        self.inputs.extend(texts)
        return [[float("nan") if self.invalid else 0.1] * 1024 for _ in texts]


def payload() -> DocumentIndexRequest:
    return DocumentIndexRequest.model_validate_json(
        (Path(__file__).resolve().parents[5] / "contract" / "DocumentIndexRequest.json").read_bytes()
    )


@pytest.mark.asyncio
async def test_index_batches_embedding_inputs_with_heading_context(db_session: AsyncSession) -> None:
    accepted = payload()
    source_id = accepted.request.sources[0].id
    document = accepted.document.model_dump(mode="json")
    document["blocks"] = [
        {
            "id": "section",
            "type": "section",
            "title": "결제 경험",
            "sourceIds": [source_id],
            "blocks": [
                {"id": f"p{i}", "type": "paragraph", "role": "body", "text": f"운영 사례 {i}", "sourceIds": [source_id]}
                for i in range(7)
            ],
        }
    ]
    accepted = DocumentIndexRequest(request=accepted.request, document=NormalizedDocument.model_validate(document))

    class LimitedEmbedder(Embedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            assert len(texts) <= 4, "Embedding service accepts at most four texts"
            return await super().embed(texts)

    embedder = LimitedEmbedder()
    await index_document(db_session, embedder, accepted, model="bge")
    assert embedder.calls == 2
    assert "결제 경험\n운영 사례 6" in embedder.inputs
    chunks = (await db_session.scalars(select(DocumentIndexChunk).order_by(DocumentIndexChunk.ordinal))).all()
    assert chunks[-1].text == "결제 경험\n운영 사례 6"


@pytest.mark.asyncio
async def test_atomic_index_retries_stale_scope_and_model(db_session: AsyncSession) -> None:
    accepted = payload()
    embedder = Embedder()
    assert (await index_document(db_session, embedder, accepted, model="bge")).status == "INDEXED"
    assert (await index_document(db_session, embedder, accepted, model="bge")).status == "UNCHANGED"
    assert embedder.calls == 2
    assert (await index_document(db_session, embedder, accepted, model="bge2")).status == "INDEXED"
    assert embedder.calls == 4
    newer = DocumentIndexRequest(
        request=accepted.request.model_copy(update={"revision": 2}),
        document=accepted.document.model_copy(update={"revision": 2}),
    )
    embedder.invalid = True
    with pytest.raises(ValueError, match="embedding"):
        await index_document(db_session, embedder, newer, model="bge2")
    active = await db_session.scalar(select(DocumentIndex))
    assert active is not None and active.revision == 1
    assert active.document_type == accepted.request.document_type.value
    assert active.sources == [source.model_dump(mode="json") for source in accepted.request.sources]
    embedder.invalid = False
    assert (await index_document(db_session, embedder, newer, model="bge2")).status == "INDEXED"
    assert (await index_document(db_session, embedder, accepted, model="bge3")).status == "STALE"
    chunks = (await db_session.scalars(select(DocumentIndexChunk))).all()
    assert chunks and all(chunk.revision == 2 and chunk.model == "bge2" for chunk in chunks)
    foreign = accepted.model_copy(
        update={
            "request": accepted.request.model_copy(
                update={
                    "application_id": uuid4(),
                }
            )
        }
    )
    with pytest.raises(DocumentIndexScopeError):
        await index_document(db_session, embedder, foreign, model="bge2")


@pytest.mark.asyncio
async def test_concurrent_stale_job_cannot_replace_newer_index(database_url: str) -> None:
    original = payload()
    document_id = uuid4()
    accepted = DocumentIndexRequest(
        request=original.request.model_copy(update={"document_id": document_id}),
        document=original.document.model_copy(update={"document_id": document_id}),
    )
    newer = DocumentIndexRequest(
        request=accepted.request.model_copy(update={"revision": 2}),
        document=accepted.document.model_copy(update={"revision": 2}),
    )
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine)
    entered = asyncio.Event()
    release = asyncio.Event()

    class PausedEmbedder(Embedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            entered.set()
            await release.wait()
            return await super().embed(texts)

    async def run(request: DocumentIndexRequest, embedder: Embedder) -> str:
        async with sessions() as session, session.begin():
            return (await index_document(session, embedder, request, model="bge")).status

    try:
        first = asyncio.create_task(run(newer, PausedEmbedder()))
        await asyncio.wait_for(entered.wait(), timeout=5)
        old_embedder = Embedder()
        second = asyncio.create_task(run(accepted, old_embedder))
        await asyncio.sleep(0.05)
        assert not second.done()
        release.set()
        assert await asyncio.wait_for(first, timeout=5) == "INDEXED"
        assert await asyncio.wait_for(second, timeout=5) == "STALE"
        assert old_embedder.calls == 0
        async with sessions() as session:
            active = await session.get(DocumentIndex, document_id)
            assert active is not None and active.revision == 2
    finally:
        release.set()
        async with sessions() as session, session.begin():
            active = await session.get(DocumentIndex, document_id)
            if active is not None:
                await session.delete(active)
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [[], [[0.1]], [[float("inf")] * 1024]])
async def test_invalid_vectors_preserve_previous_index(db_session: AsyncSession, invalid: list[list[float]]) -> None:
    accepted = payload()
    await index_document(db_session, Embedder(), accepted, model="old")

    class InvalidEmbedder:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return invalid

    with pytest.raises(ValueError, match="embedding"):
        await index_document(db_session, InvalidEmbedder(), accepted, model="new")
    active = await db_session.get(DocumentIndex, accepted.request.document_id)
    assert active is not None and active.model == "old"
    chunks = (await db_session.scalars(select(DocumentIndexChunk))).all()
    assert chunks and all(chunk.model == "old" for chunk in chunks)


@pytest.mark.asyncio
async def test_same_revision_changed_content_is_rejected(db_session: AsyncSession) -> None:
    accepted = payload()
    embedder = Embedder()
    await index_document(db_session, embedder, accepted, model="bge")
    changed = accepted.model_copy(update={"document": accepted.document.model_copy(update={"blocks": []})})
    with pytest.raises(ValueError, match="revision change"):
        await index_document(db_session, embedder, changed, model="bge")
    assert embedder.calls == 2


@pytest.mark.asyncio
async def test_long_unicode_embedding_input_keeps_the_entire_text(db_session: AsyncSession) -> None:
    accepted = payload()
    document = accepted.document.model_dump(mode="json")
    title = "긴 제목" * 600
    body = "한글 원문과 이모지 😀 " * 600
    document["blocks"] = [
        {
            "id": "s",
            "type": "section",
            "sourceIds": [accepted.request.sources[0].id],
            "title": title,
            "blocks": [
                {
                    "id": "p",
                    "type": "paragraph",
                    "role": "body",
                    "text": body,
                    "sourceIds": [accepted.request.sources[0].id],
                }
            ],
        }
    ]
    accepted = DocumentIndexRequest(request=accepted.request, document=NormalizedDocument.model_validate(document))
    embedder = Embedder()
    await index_document(db_session, embedder, accepted, model="bge")
    # A UTF-8 byte budget also bounds byte-fallback tokens below the service's 512-token limit.
    assert all(len(text.encode("utf-8")) <= 500 for text in embedder.inputs)
    chunks = (await db_session.scalars(select(DocumentIndexChunk).order_by(DocumentIndexChunk.ordinal))).all()
    original_body = "".join(chunk.text for chunk in chunks if chunk.block_ids == ["p"])
    assert body.replace(" ", "") in original_body.replace(title, "").replace("\n", "").replace(" ", "")


@pytest.mark.asyncio
async def test_embedding_service_failure_keeps_previous_revision(db_session: AsyncSession) -> None:
    accepted = payload()
    await index_document(db_session, Embedder(), accepted, model="old")

    class FailedEmbedder:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise TimeoutError("internal embedding service unavailable")

    with pytest.raises(TimeoutError):
        await index_document(db_session, FailedEmbedder(), accepted, model="new")
    active = await db_session.get(DocumentIndex, accepted.request.document_id)
    assert active is not None and active.model == "old"
    assert (await index_document(db_session, Embedder(), accepted, model="new")).status == "INDEXED"
