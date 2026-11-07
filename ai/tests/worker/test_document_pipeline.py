"""Exercise document jobs through Redis, the worker, indexing, and scoped search."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from eval.document_quality_baseline import _request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.analysis.application.normalize import DocumentLayout
from hiremate_ai.agents.analysis.application.store import DbReviewStore
from hiremate_ai.config import settings
from hiremate_ai.contract import DocumentIndexRequest, DocumentSource, Job, JobResult, JobStatus, NormalizedDocument
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.tools.document_search import DocumentSentence, search_document_embeddings
from hiremate_ai.tools.scope import ToolScope
from hiremate_ai.worker.handlers import job_handlers
from hiremate_ai.worker.runner import Worker, WorkerOptions


def _layout_blocks(value: Any) -> Any:
    if isinstance(value, list):
        return [_layout_blocks(item) for item in value]
    if isinstance(value, dict):
        return {key: _layout_blocks(item) for key, item in value.items() if key not in {"id", "notice"}}
    return value


@pytest.fixture
def fixture_data(case: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = Path(__file__).resolve().parents[1]
    sources = json.loads((root / "samples" / "document_quality_sources.json").read_text())[case]
    document = json.loads((root / "eval" / "document_quality_luna_documents.json").read_text())[case]
    return sources, document


@pytest.mark.parametrize(
    ("case", "kind", "query", "source_id"),
    [
        ("resume", "RESUME", "Python", "s3"),
        ("cover_letter", "COVER_LETTER", "I verified", "s5"),
        ("portfolio", "PORTFOLIO", "Latency", "s6"),
    ],
)
async def test_fixture_jobs_reach_scoped_search(
    redis: Redis,
    db_session: AsyncSession,
    fixture_data: tuple[list[dict[str, Any]], dict[str, Any]],
    case: str,
    kind: str,
    query: str,
    source_id: str,
) -> None:
    sources, document = fixture_data
    request = _request(case, kind, [DocumentSource.model_validate(source) for source in sources]).model_copy(
        update={"company_id": uuid4(), "recruitment_id": uuid4(), "application_id": uuid4(), "document_id": uuid4()}
    )
    layout = DocumentLayout.model_validate({"blocks": _layout_blocks(document["blocks"])})
    llm = FakeLlm(layout)

    class FixtureEmbedder:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] + [0.0] * 1022 if query in text else [0.0, 1.0] + [0.0] * 1022 for text in texts]

    embedder = FixtureEmbedder()
    sessions = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    options = WorkerOptions(
        job_stream="jobs",
        result_stream="results",
        group="document-worker",
        consumer="fixture",
        attempts=1,
        block_seconds=0.05,
    )
    worker = Worker(redis, job_handlers(llm, DbReviewStore(sessions), sessions, document_embedder=embedder), options)
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))

    async def run_job(kind: str, payload: dict[str, Any]) -> JobResult:
        job = Job(job_id=uuid4(), type=kind, target=str(request.document_id), payload=payload)
        await redis.xadd(options.job_stream, {"job": job.model_dump_json()})
        async with asyncio.timeout(15):
            while True:
                entries: Any = await redis.xrange(options.result_stream)
                for _, fields in entries:
                    result = JobResult.model_validate_json(fields["result"])
                    if result.job_id == job.job_id:
                        return result
                await asyncio.sleep(0.05)

    try:
        normalized_result = await run_job("application/normalize", request.model_dump(mode="json", by_alias=True))
        assert normalized_result.status == JobStatus.DONE
        normalized = NormalizedDocument.model_validate(normalized_result.result)
        normalized.validate_sources(request.sources)
        assert normalized.model_dump(mode="json", by_alias=True)["blocks"] == document["blocks"]
        assert len(llm.calls) == 1

        index_request = DocumentIndexRequest(request=request, document=normalized)
        indexed = await run_job("application/index-document", index_request.model_dump(mode="json", by_alias=True))
        assert indexed.status == JobStatus.DONE
        assert indexed.result is not None and indexed.result["revision"] == request.revision

        scope = ToolScope(request.company_id, request.recruitment_id, uuid4(), frozenset({request.application_id}))
        found = await search_document_embeddings(
            db_session, embedder, scope, [query], [request.application_id], model=settings.ncs_model
        )
        assert len(found) == 1
        sentence = next(
            value
            for value in found[0].sentences
            if isinstance(value, DocumentSentence) and value.provenance.source_id == source_id
        )
        assert query in sentence.sentence
        assert sentence.provenance.page == 1
        assert sentence.provenance.revision == request.revision
        assert sentence.provenance.block_ids
        assert not await search_document_embeddings(
            db_session,
            embedder,
            replace(scope, company_id=uuid4()),
            [query],
            [request.application_id],
            model=settings.ncs_model,
        )
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=10)
