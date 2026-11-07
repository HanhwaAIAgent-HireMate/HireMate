"""Opt-in retrieval evaluation against an existing local embedding service.

Run explicitly with pytest. Only synthetic PDF fixture data is sent to the
local service; the test database is isolated and rolled back afterward.
"""

import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from eval.document_quality_baseline import _request
from eval.document_quality_gold import PDF_CASES
from hiremate_ai.agents.analysis.application.index import index_document
from hiremate_ai.agents.analysis.application.normalize import verbatim_document
from hiremate_ai.contract import DocumentIndexRequest, DocumentSource, NormalizedDocument
from hiremate_ai.ncs_search.reference import EmbedClient
from hiremate_ai.tools.document_search import DocumentSentence, search_document_embeddings
from hiremate_ai.tools.profile_search import DenseProfileEmbedder
from hiremate_ai.tools.scope import ToolScope

# The HTTP health endpoint does not identify the encoder revision. The database
# label is deliberately not a claim about the service's actual model.
MODEL_LABEL = "local-service-unverified"
QUERIES = [
    ("Python", {"resume"}),
    ("booking process", {"cover_letter"}),
    ("Latency", {"portfolio"}),
    ("quantum cryptography", set()),
]


def _fixtures() -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(__file__).resolve().parents[1]
    sources = json.loads((root / "samples" / "document_quality_sources.json").read_text())
    documents = json.loads((root / "eval" / "document_quality_luna_documents.json").read_text())
    return sources, documents


async def test_real_local_embedding_retrieval(db_session: AsyncSession) -> None:
    source_data, documents = _fixtures()
    selected = [case for case in PDF_CASES if case.name in {"resume", "cover_letter", "portfolio"}]
    modes = ("structured", "verbatim")
    results_by_mode = {}
    async with httpx.AsyncClient(timeout=60) as http:
        embedder = DenseProfileEmbedder(EmbedClient(http, "http://127.0.0.1:8002"))
        for mode in modes:
            company, recruitment, stage = uuid4(), uuid4(), uuid4()
            applicants = {case.name: uuid4() for case in selected}
            names = {value: key for key, value in applicants.items()}
            scope = ToolScope(company, recruitment, stage, frozenset(applicants.values()))
            started = time.monotonic()
            for case in selected:
                sources = [DocumentSource.model_validate(item) for item in source_data[case.name]]
                request = _request(case.name, case.document_type, sources).model_copy(
                    update={
                        "company_id": company,
                        "recruitment_id": recruitment,
                        "application_id": applicants[case.name],
                        "document_id": uuid4(),
                    }
                )
                document = (
                    NormalizedDocument.model_validate(documents[case.name]).model_copy(
                        update={"document_id": request.document_id}
                    )
                    if mode == "structured"
                    else verbatim_document(request)
                )
                await index_document(
                    db_session, embedder, DocumentIndexRequest(request=request, document=document), model=MODEL_LABEL
                )
            index_seconds = round(time.monotonic() - started, 2)
            results = []
            for query, expected in QUERIES:
                started = time.monotonic()
                matches = await search_document_embeddings(
                    db_session, embedder, scope, [query], list(applicants.values()), model=MODEL_LABEL
                )
                found = [names[match.application_id] for match in matches]
                for match in matches:
                    assert all(
                        isinstance(item, DocumentSentence) and item.belongs_to(scope, match.application_id)
                        for item in match.sentences
                    )
                results.append(
                    {
                        "query": query,
                        "expected": sorted(expected),
                        "found": found,
                        "missed": sorted(expected - set(found)),
                        "unexpected": sorted(set(found) - expected),
                        "seconds": round(time.monotonic() - started, 2),
                    }
                )
            results_by_mode[mode] = {"index_seconds": index_seconds, "queries": results}
    print(
        "DOCUMENT_RETRIEVAL_EVAL "
        + json.dumps(
            {"encoder_revision": "unverified", "stage": "before_recheck", "modes": results_by_mode},
            ensure_ascii=False,
        )
    )
