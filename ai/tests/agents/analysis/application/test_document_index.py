from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.index import index_document
from hiremate_ai.contract import CompanyProfile, DocumentIndexRequest, PostingContent
from hiremate_ai.db.document_index import DocumentIndex, DocumentIndexChunk
from hiremate_ai.tools.document_search import DocumentSentence, search_document_embeddings
from hiremate_ai.tools.scope import ToolScope


class FakeEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [([1.0, 0.0] if "결제" in text or "금융" in text else [0.0, 1.0]) + [0.0] * 1022 for text in texts]


def request(
    company_id: object, recruitment_id: object, application_id: object, document_id: object, *, revision: int = 1
) -> DocumentIndexRequest:
    return DocumentIndexRequest.model_validate(
        {
            "companyId": str(company_id),
            "recruitmentId": str(recruitment_id),
            "applicationId": str(application_id),
            "revision": revision,
            "blind": False,
            "applicantName": "홍길동",
            "document": {
                "schemaVersion": "1.0",
                "document": {"id": str(document_id), "type": "resume", "title": None, "pageCount": 1},
                "blocks": [{"id": "p1", "type": "paragraph", "pages": [1], "text": "결제 승인 서버를 개발했다."}],
            },
        }
    )


async def test_indexes_normalized_document_and_searches_only_authorized_scope(db_session: AsyncSession) -> None:
    company, recruitment, candidate, document = uuid4(), uuid4(), uuid4(), uuid4()
    other_company, other_candidate, other_document = uuid4(), uuid4(), uuid4()
    embedder = FakeEmbedder()
    await index_document(db_session, embedder, request(company, recruitment, candidate, document), model="BAAI/bge-m3")
    await index_document(
        db_session, embedder, request(other_company, recruitment, other_candidate, other_document), model="BAAI/bge-m3"
    )
    scope = ToolScope(company, recruitment, uuid4(), frozenset({candidate, other_candidate}))
    found = await search_document_embeddings(
        db_session, embedder, scope, ["금융 개발"], [candidate, other_candidate], model="BAAI/bge-m3"
    )
    assert [match.application_id for match in found] == [candidate]
    assert found[0].sentences[0].sentence == "결제 승인 서버를 개발했다."
    assert found[0].sentences[0].source == "이력서"
    assert isinstance(found[0].sentences[0], DocumentSentence)
    assert found[0].sentences[0].provenance.pages == (1,)
    chunks = (await db_session.scalars(select(DocumentIndexChunk))).all()
    assert len(chunks) == 2


async def test_rejects_older_revision_without_replacing_newer_content(db_session: AsyncSession) -> None:
    company, recruitment, candidate, document = uuid4(), uuid4(), uuid4(), uuid4()
    embedder = FakeEmbedder()
    newer = request(company, recruitment, candidate, document, revision=2)
    await index_document(db_session, embedder, newer, model="BAAI/bge-m3")
    result = await index_document(
        db_session, embedder, request(company, recruitment, candidate, document), model="BAAI/bge-m3"
    )
    assert result.status == "STALE"
    stored = await db_session.get(DocumentIndex, document)
    assert stored is not None and stored.revision == 2


async def test_worker_persists_index_for_saved_normalized_document(db_session: AsyncSession) -> None:
    from typing import cast

    from root_context import sessions_of

    from hiremate_ai.agents.analysis.application.store import ReviewStore
    from hiremate_ai.llm.fake import FakeLlm
    from hiremate_ai.worker.handlers import job_handlers

    company, recruitment, candidate, document = uuid4(), uuid4(), uuid4(), uuid4()
    body = request(company, recruitment, candidate, document).model_dump(mode="json", by_alias=True)
    handle = job_handlers(
        FakeLlm(), cast(ReviewStore, object()), sessions_of(db_session), document_embedder=FakeEmbedder()
    )["application/index-document"]
    result = await handle(body)
    assert result == {"documentId": str(document), "revision": 1, "status": "DONE"}
    assert await db_session.get(DocumentIndex, document) is not None


async def test_index_route_returns_document_id_and_revision(db_session: AsyncSession) -> None:
    from hiremate_ai.agents.analysis.application.router import index_saved_document

    company, recruitment, candidate, document = uuid4(), uuid4(), uuid4(), uuid4()
    result = await index_saved_document(request(company, recruitment, candidate, document), db_session, FakeEmbedder())
    assert result.document_id == document
    assert result.revision == 1
    assert result.status == "DONE"


async def test_root_toolkit_uses_normalized_document_vectors(
    db_session: AsyncSession, sample_applicants: dict, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    from root_context import make_context, sessions_of

    from hiremate_ai.agents.root.toolkit import profile_toolkit, scope_of

    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험")
    candidate = context.candidates[0].application_id
    body = request(context.company.company_id, context.recruitment_id, candidate, uuid4())
    embedder = FakeEmbedder()
    await index_document(db_session, embedder, body, model="BAAI/bge-m3")
    await db_session.commit()
    found = await profile_toolkit(sessions_of(db_session), embedder=embedder).search(
        scope_of(context), ["금융 경험"], [candidate]
    )
    assert any(isinstance(source, DocumentSentence) for match in found for source in match.sentences)


def test_profile_embeddings_are_no_longer_part_of_runtime() -> None:
    import inspect

    from hiremate_ai.agents.analysis.application import router
    from hiremate_ai.db.profile import ProfileItem
    from hiremate_ai.worker.handlers import job_handlers

    assert "profile_indexer" not in inspect.signature(job_handlers).parameters
    assert "indexer" not in inspect.signature(router.analyze).parameters
    assert "embedding" not in ProfileItem.__table__.columns
    assert "embedding_model" not in ProfileItem.__table__.columns
