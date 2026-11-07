"""Test-only Redis worker for the opt-in backend-to-AI document pipeline test.

The backend test supplies disposable PostgreSQL and Redis URLs. The worker uses
recorded fictional Luna responses and deterministic embeddings, never a model API.
"""

import asyncio
import json
import signal
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from hiremate_ai.agents.analysis.application.normalize import DocumentLayout
from hiremate_ai.agents.analysis.application.store import DbReviewStore
from hiremate_ai.config import settings
from hiremate_ai.contract import DocumentIndexRequest
from hiremate_ai.llm.fake import FakeLlm, LlmCall
from hiremate_ai.tools.document_search import DocumentSentence, search_document_embeddings
from hiremate_ai.tools.scope import ToolScope
from hiremate_ai.worker.handlers import job_handlers
from hiremate_ai.worker.runner import Worker, WorkerOptions, connect

FIXTURES = Path(__file__).resolve().parents[1] / "eval" / "document_quality_luna_documents.json"
QUERIES = {"RESUME": ("Python", "s3"), "COVER_LETTER": ("I verified", "s5"), "PORTFOLIO": ("Latency", "s6")}


def _layout(value: Any) -> Any:
    if isinstance(value, list):
        return [_layout(item) for item in value]
    if isinstance(value, dict):
        return {key: _layout(item) for key, item in value.items() if key not in {"id", "notice"}}
    if isinstance(value, str):
        return value.replace("SAMPLE", "○○○")
    return value


def _reply(call: LlmCall) -> DocumentLayout:
    # The backend test applicant is named SAMPLE. Every fixture contains that
    # string, so the model must see the masked form rather than the name.
    if "SAMPLE" in call.user or "○○○" not in call.user:
        raise AssertionError("The fictional applicant name was not masked")
    case = "resume" if "Python" in call.user else "portfolio" if "Latency" in call.user else "cover_letter"
    documents = json.loads(FIXTURES.read_text())
    return DocumentLayout.model_validate({"blocks": _layout(documents[case]["blocks"])})


class FixtureEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            index = next((i for i, (query, _) in enumerate(QUERIES.values()) if query in text), 3)
            vectors.append([1.0 if i == index else 0.0 for i in range(1024)])
        return vectors


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    embedder = FixtureEmbedder()
    available = job_handlers(FakeLlm(*([_reply] * 12)), DbReviewStore(sessions), sessions, document_embedder=embedder)
    handlers = {name: available[name] for name in ("application/normalize", "application/index-document")}
    index_document = handlers["application/index-document"]

    async def index_and_check(payload: dict[str, Any]) -> dict[str, Any]:
        result = await index_document(payload)
        request = DocumentIndexRequest.model_validate(payload).request
        query, source_id = QUERIES[request.document_type.value]
        scope = ToolScope(request.company_id, request.recruitment_id, uuid4(), frozenset({request.application_id}))
        async with sessions() as session:
            found = await search_document_embeddings(
                session, embedder, scope, [query], [request.application_id], model=settings.ncs_model
            )
            if len(found) != 1:
                raise AssertionError("The fictional document was not found")
            sentence = next(
                value
                for value in found[0].sentences
                if isinstance(value, DocumentSentence) and value.provenance.source_id == source_id
            )
            if (
                query not in sentence.sentence
                or sentence.provenance.page != 1
                or sentence.provenance.revision != request.revision
                or not sentence.provenance.block_ids
            ):
                raise AssertionError("Search provenance did not match the fictional PDF")
            if await search_document_embeddings(
                session,
                embedder,
                replace(scope, company_id=uuid4()),
                [query],
                [request.application_id],
                model=settings.ncs_model,
            ):
                raise AssertionError("Search crossed the company boundary")
            if await search_document_embeddings(
                session,
                embedder,
                replace(scope, recruitment_id=uuid4()),
                [query],
                [request.application_id],
                model=settings.ncs_model,
            ):
                raise AssertionError("Search crossed the recruitment boundary")
        return result

    handlers["application/index-document"] = index_and_check
    options = WorkerOptions(
        job_stream=settings.worker_job_stream,
        result_stream=settings.worker_result_stream,
        group=settings.worker_group,
        consumer="document-e2e",
        concurrency=1,
        attempts=1,
        block_seconds=0.1,
    )
    redis = connect(settings.redis_url, options)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, stop.set)
    try:
        await Worker(redis, handlers, options).run(stop)
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    command.upgrade(Config(toml_file="pyproject.toml"), "head")
    asyncio.run(main())
