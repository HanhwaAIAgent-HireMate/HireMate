from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from root_context import make_context, sessions_of
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.index import index_document
from hiremate_ai.agents.analysis.application.normalize import DocumentLayout, LayoutBlock, normalize_document
from hiremate_ai.agents.root.find import RecheckItem, RecheckResult, recheck
from hiremate_ai.agents.root.toolkit import profile_toolkit, scope_of
from hiremate_ai.contract import (
    ApplicantDetail,
    CompanyProfile,
    DocumentIndexRequest,
    DocumentNormalizationRequest,
    DocumentParagraph,
    DocumentSource,
    DocumentType,
    NormalizedDocument,
    NormalizedDocumentType,
    PostingContent,
)
from hiremate_ai.db.document_index import DocumentIndexChunk
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.ncs_search.reference import NcsUnavailable
from hiremate_ai.tools import document_search as module
from hiremate_ai.tools.candidates import SearchResults
from hiremate_ai.tools.scope import ToolScope

MODEL = "BAAI/bge-m3"
ORIGINAL = "승인 서버의 동시 요청을 처리했습니다."


class Embedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 1023 for _ in texts]


def payload(
    scope: ToolScope, candidate: UUID, *, document_type: NormalizedDocumentType = DocumentType.RESUME
) -> DocumentIndexRequest:
    document_id = uuid4()
    source = DocumentSource(id="s1", page=2, text=ORIGINAL)
    request = DocumentNormalizationRequest(
        document_id=document_id,
        company_id=scope.company_id,
        recruitment_id=scope.recruitment_id,
        application_id=candidate,
        revision=1,
        document_type=document_type,
        sources=[source],
    )
    document = NormalizedDocument(
        document_id=document_id,
        revision=1,
        document_type=document_type,
        blocks=[DocumentParagraph(id="b1", source_ids=["s1"], type="paragraph", role="body", text=ORIGINAL)],
    )
    return DocumentIndexRequest(request=request, document=document)


async def test_document_vectors_find_actual_original_with_typed_provenance(db_session: AsyncSession) -> None:
    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))
    accepted = payload(scope, candidate)
    await index_document(db_session, Embedder(), accepted, model=MODEL)
    # A contextual chunk label must never become an original quote.
    chunk = await db_session.get(DocumentIndexChunk, (accepted.request.document_id, 0))
    assert chunk is not None
    chunk.text = "프로젝트 > 행 1 열 2: " + ORIGINAL
    await db_session.flush()

    found = await module.search_document_embeddings(
        db_session, Embedder(), scope, ["금융 승인"], [candidate], model=MODEL
    )

    assert [match.application_id for match in found] == [candidate]
    sentence = found[0].sentences[0]
    assert isinstance(sentence, module.DocumentSentence)
    assert sentence.sentence == ORIGINAL
    assert sentence.source == "이력서"
    assert sentence.provenance.document_id == accepted.request.document_id
    assert sentence.provenance.revision == 1
    assert sentence.provenance.block_ids == ("b1",)
    assert sentence.provenance.source_id == "s1"
    assert sentence.provenance.page == 2


async def test_search_intersects_tenant_recruitment_stage_and_pool(db_session: AsyncSession) -> None:
    allowed, other_tenant, other_recruitment, other_stage, outside_pool = [uuid4() for _ in range(5)]
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({allowed, other_tenant, other_recruitment, outside_pool}))
    for candidate in (allowed, other_tenant, other_recruitment, other_stage, outside_pool):
        own = replace(scope, company_id=uuid4()) if candidate == other_tenant else scope
        own = replace(own, recruitment_id=uuid4()) if candidate == other_recruitment else own
        await index_document(db_session, Embedder(), payload(own, candidate), model=MODEL)

    found = await module.search_document_embeddings(
        db_session,
        Embedder(),
        scope,
        ["승인"],
        [allowed, other_tenant, other_recruitment, other_stage],
        model=MODEL,
    )

    assert [match.application_id for match in found] == [allowed]


@pytest.mark.parametrize("mismatch", ["revision", "model", "source"])
async def test_stale_or_unresolvable_chunks_are_not_evidence(db_session: AsyncSession, mismatch: str) -> None:
    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))
    accepted = payload(scope, candidate)
    await index_document(db_session, Embedder(), accepted, model=MODEL)
    chunk = await db_session.get(DocumentIndexChunk, (accepted.request.document_id, 0))
    assert chunk is not None
    if mismatch == "revision":
        chunk.revision = 0
    elif mismatch == "model":
        chunk.model = "obsolete"
    else:
        chunk.source_ids = ["missing"]
    await db_session.flush()

    assert not await module.search_document_embeddings(
        db_session, Embedder(), scope, ["승인"], [candidate], model=MODEL
    )


@pytest.mark.parametrize("condition", ["30세 이하", "남성 지원자", "서울 출신", "기혼", "키 180cm 이상"])
async def test_discriminatory_conditions_do_not_reach_embedding(db_session: AsyncSession, condition: str) -> None:
    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))

    class ForbiddenEmbedder:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise AssertionError("Discriminatory criteria reached embedding")

    assert not await module.search_document_embeddings(
        db_session, ForbiddenEmbedder(), scope, ["승인", condition], [candidate], model=MODEL
    )


async def test_document_search_failure_preserves_other_search_results(db_session: AsyncSession) -> None:
    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))

    class Offline:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise NcsUnavailable("offline")

    search = module.document_embedding_search(sessions_of(db_session), Offline(), model=MODEL)
    found = await search(scope, ["승인"], [candidate])

    assert isinstance(found, SearchResults)
    assert not found and found.warnings


@pytest.mark.parametrize("document_type", [DocumentType.RESUME, DocumentType.COVER_LETTER, DocumentType.PORTFOLIO])
async def test_normalize_index_search_three_document_types(
    db_session: AsyncSession, document_type: NormalizedDocumentType
) -> None:
    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))
    request = payload(scope, candidate, document_type=document_type).request
    llm = FakeLlm(DocumentLayout(blocks=[LayoutBlock(type="paragraph", source_ids=["s1"], role="body", text=ORIGINAL)]))
    document = await normalize_document(llm, request)
    await index_document(db_session, Embedder(), DocumentIndexRequest(request=request, document=document), model=MODEL)

    found = await module.search_document_embeddings(db_session, Embedder(), scope, ["승인"], [candidate], model=MODEL)

    assert found[0].sentences[0].source == document_type.label
    assert found[0].sentences[0].sentence == request.sources[0].text


async def test_root_merge_and_recheck_keep_stored_original_without_chat_document(
    db_session: AsyncSession,
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 승인 경험")
    candidate = context.candidates[0].application_id
    context = context.model_copy(update={"documents": {}})
    scope = scope_of(context)
    accepted = payload(scope, candidate)
    await index_document(db_session, Embedder(), accepted, model=MODEL)
    toolkit = profile_toolkit(sessions_of(db_session), embedder=Embedder())
    found = await toolkit.search(scope, ["금융 승인"], [candidate])
    assert found and isinstance(found[0].sentences[0], module.DocumentSentence)
    llm = FakeLlm(RecheckResult(results=[RecheckItem(candidate_no=1, met=True, sentence_nos=[1])]))

    checked = await recheck(llm, context, found, conditions=["금융 승인"], talents=[], memo={}, candidate_memo={})

    assert checked[0][0] == candidate
    assert checked[0][1][0].sentence == ORIGINAL
    original = found[0].sentences[0]
    assert isinstance(original, module.DocumentSentence)
    other = replace(original, provenance=replace(original.provenance, application_id=uuid4()))
    forged = replace(found[0], sentences=[other])
    llm = FakeLlm(RecheckResult(results=[RecheckItem(candidate_no=1, met=True, sentence_nos=[1])]))
    assert not await recheck(llm, context, [forged], conditions=["금융 승인"], talents=[], memo={}, candidate_memo={})


async def test_cosine_similarity_filters_and_orders_real_vectors(db_session: AsyncSession) -> None:
    first, second, unrelated = [uuid4() for _ in range(3)]
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({first, second, unrelated}))
    for candidate in (first, second, unrelated):
        accepted = payload(scope, candidate)
        await index_document(db_session, Embedder(), accepted, model=MODEL)
        chunk = await db_session.get(DocumentIndexChunk, (accepted.request.document_id, 0))
        assert chunk is not None
        if candidate == unrelated:
            chunk.embedding = [0.0, 1.0] + [0.0] * 1022
    await db_session.flush()
    pool = [second, unrelated, first, second]

    one = await module.search_document_embeddings(db_session, Embedder(), scope, ["승인"], pool, model=MODEL)
    two = await module.search_document_embeddings(db_session, Embedder(), scope, ["승인"], pool, model=MODEL)

    assert one == two
    assert [match.application_id for match in one] == [second, first]


async def test_generated_reference_notice_is_never_quoted(db_session: AsyncSession) -> None:
    from hiremate_ai.contract import VISUAL_NOTICE, DocumentReference

    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))
    accepted = payload(scope, candidate, document_type=DocumentType.PORTFOLIO)
    original = "성능 변화 그래프"
    request = accepted.request.model_copy(update={"sources": [DocumentSource(id="s1", page=3, text=original)]})
    document = accepted.document.model_copy(
        update={
            "blocks": [
                DocumentReference(
                    id="b1",
                    type="reference",
                    source_ids=["s1"],
                    kind="possible_visual",
                    text=original,
                    notice=VISUAL_NOTICE,
                ),
            ]
        }
    )
    await index_document(db_session, Embedder(), DocumentIndexRequest(request=request, document=document), model=MODEL)

    found = await module.search_document_embeddings(db_session, Embedder(), scope, ["성능"], [candidate], model=MODEL)

    assert [sentence.sentence for sentence in found[0].sentences] == [original]
    assert all(VISUAL_NOTICE not in sentence.sentence for sentence in found[0].sentences)


async def test_failed_replacement_keeps_previously_searchable_original(db_session: AsyncSession) -> None:
    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))
    accepted = payload(scope, candidate)
    await index_document(db_session, Embedder(), accepted, model=MODEL)
    newer = DocumentIndexRequest(
        request=accepted.request.model_copy(update={"revision": 2}),
        document=accepted.document.model_copy(update={"revision": 2}),
    )

    class Offline:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise NcsUnavailable("offline")

    with pytest.raises(NcsUnavailable):
        await index_document(db_session, Offline(), newer, model=MODEL)

    found = await module.search_document_embeddings(db_session, Embedder(), scope, ["승인"], [candidate], model=MODEL)

    sentence = found[0].sentences[0]
    assert isinstance(sentence, module.DocumentSentence)
    assert sentence.provenance.revision == 1
    assert sentence.sentence == ORIGINAL


async def test_document_outage_keeps_root_keyword_matches(
    db_session: AsyncSession,
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="결제 경험")
    candidate = context.candidates[0].application_id

    class Offline:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise NcsUnavailable("offline")

    toolkit = profile_toolkit(sessions_of(db_session), embedder=Offline())
    found = await toolkit.search(scope_of(context), ["결제"], [candidate])

    assert [match.application_id for match in found] == [candidate]
    assert isinstance(found, SearchResults) and found.warnings
    assert found[0].sentences[0].sentence in context.documents[candidate][0].text


async def test_search_uses_previous_revision_while_replacement_is_embedding(db_session: AsyncSession) -> None:
    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))
    accepted = payload(scope, candidate)
    await index_document(db_session, Embedder(), accepted, model=MODEL)
    newer = DocumentIndexRequest(
        request=accepted.request.model_copy(update={"revision": 2}),
        document=accepted.document.model_copy(update={"revision": 2}),
    )
    observed: list[int] = []

    class PendingReplacement:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            found = await module.search_document_embeddings(
                db_session,
                Embedder(),
                scope,
                ["승인"],
                [candidate],
                model=MODEL,
            )
            sentence = found[0].sentences[0]
            assert isinstance(sentence, module.DocumentSentence)
            observed.append(sentence.provenance.revision)
            return await Embedder().embed(texts)

    await index_document(db_session, PendingReplacement(), newer, model=MODEL)
    current = await module.search_document_embeddings(db_session, Embedder(), scope, ["승인"], [candidate], model=MODEL)

    sentence = current[0].sentences[0]
    assert isinstance(sentence, module.DocumentSentence)
    assert observed and set(observed) == {1}
    assert sentence.provenance.revision == 2


async def test_search_repairs_model_upgrade_without_new_backend_job(db_session: AsyncSession) -> None:
    from hiremate_ai.db.document_index import DocumentIndex

    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))
    accepted = payload(scope, candidate)
    await index_document(db_session, Embedder(), accepted, model="previous-model")
    search = module.document_embedding_search(sessions_of(db_session), Embedder(), model=MODEL)

    preparing = await search(scope, ["승인"], [candidate])
    assert isinstance(preparing, SearchResults) and preparing.warnings
    assert not preparing
    await search.wait_pending()
    found = await search(scope, ["승인"], [candidate])

    assert [match.application_id for match in found] == [candidate]
    sentence = found[0].sentences[0]
    assert isinstance(sentence, module.DocumentSentence)
    assert sentence.sentence == ORIGINAL and sentence.provenance.revision == 1
    db_session.expire_all()
    current = await db_session.get(DocumentIndex, accepted.request.document_id)
    chunk = await db_session.get(DocumentIndexChunk, (accepted.request.document_id, 0))
    assert current is not None and current.model == MODEL and current.revision == 1
    assert chunk is not None and chunk.model == MODEL and chunk.revision == 1


async def test_failed_model_repair_preserves_previous_vectors(db_session: AsyncSession) -> None:
    from hiremate_ai.db.document_index import DocumentIndex

    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))
    accepted = payload(scope, candidate)
    await index_document(db_session, Embedder(), accepted, model="previous-model")

    class Offline:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise NcsUnavailable("offline")

    search = module.document_embedding_search(sessions_of(db_session), Offline(), model=MODEL)
    found = await search(scope, ["승인"], [candidate])
    assert isinstance(found, SearchResults) and found.warnings
    await search.wait_pending()
    db_session.expire_all()
    current = await db_session.get(DocumentIndex, accepted.request.document_id)
    chunk = await db_session.get(DocumentIndexChunk, (accepted.request.document_id, 0))

    assert current is not None and current.model == "previous-model" and current.revision == 1
    assert chunk is not None and chunk.model == "previous-model" and list(chunk.embedding) == [1.0] + [0.0] * 1023


@pytest.mark.parametrize("kind", ["table", "paragraph"])
async def test_root_merge_keeps_matching_original_after_multiple_ancestor_sources(
    db_session: AsyncSession,
    kind: str,
) -> None:
    from hiremate_ai.agents.root.toolkit import merged_search
    from hiremate_ai.contract import DocumentBlock, DocumentSection, DocumentTable

    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))
    accepted = payload(scope, candidate)
    originals = ["경력", "플랫폼", "프로젝트", "기간 내용", "2021 모니터링", "2022 배포", "2023 Kafka 파이프라인 구축"]
    sources = [DocumentSource(id=f"s{number}", page=number, text=text) for number, text in enumerate(originals, 1)]
    leaf: DocumentBlock = (
        DocumentTable(
            id="table",
            type="table",
            source_ids=["s4", "s5", "s6", "s7"],
            caption=None,
            headers=["기간", "내용"],
            rows=[["2021", "모니터링"], ["2022", "배포"], ["2023", "Kafka 파이프라인 구축"]],
        )
        if kind == "table"
        else DocumentParagraph(id="body", type="paragraph", source_ids=["s7"], role="body", text=originals[-1])
    )
    for number in (3, 2, 1):
        leaf = DocumentSection(
            id=f"heading{number}", type="section", source_ids=[f"s{number}"], title=originals[number - 1], blocks=[leaf]
        )
    request = accepted.request.model_copy(update={"sources": sources})
    document = accepted.document.model_copy(update={"blocks": [leaf]})

    class MatchingEmbedder:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [([1.0, 0.0] if "Kafka" in text else [0.0, 1.0]) + [0.0] * 1022 for text in texts]

    await index_document(
        db_session, MatchingEmbedder(), DocumentIndexRequest(request=request, document=document), model=MODEL
    )
    search = merged_search(module.document_embedding_search(sessions_of(db_session), MatchingEmbedder(), model=MODEL))

    found = await search(scope, ["Kafka"], [candidate])

    assert found and any(sentence.sentence == originals[-1] for sentence in found[0].sentences)
    assert all(sentence.sentence in originals for sentence in found[0].sentences)


@pytest.mark.parametrize("separator", ["\n", " "])
@pytest.mark.parametrize("tail", ["나이 30세", "직무 서버 개발"])
async def test_root_recheck_retains_safe_experience_quote_on_page_with_contact(
    db_session: AsyncSession,
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    separator: str,
    tail: str,
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="승인 경험")
    context = context.model_copy(update={"documents": {}})
    candidate = context.candidates[0]
    scope = scope_of(context)
    accepted = payload(scope, candidate.application_id)
    page = separator.join([candidate.name, "010-1234-5678", ORIGINAL, tail])
    request = accepted.request.model_copy(update={"sources": [DocumentSource(id="s1", page=1, text=page)]})
    await index_document(
        db_session, Embedder(), DocumentIndexRequest(request=request, document=accepted.document), model=MODEL
    )
    toolkit = profile_toolkit(sessions_of(db_session), embedder=Embedder())
    found = await toolkit.search(scope, ["승인"], [candidate.application_id])
    llm = FakeLlm(RecheckResult(results=[RecheckItem(candidate_no=1, met=True, sentence_nos=[1])]))

    checked = await recheck(llm, context, found, conditions=["승인"], talents=[], memo={}, candidate_memo={})

    assert checked and checked[0][0] == candidate.application_id
    quote = checked[0][1][0]
    assert quote.sentence == ORIGINAL
    assert isinstance(quote, module.DocumentSentence)
    assert quote.provenance.original_text == page
    assert quote.belongs_to(scope, candidate.application_id)
    assert candidate.name not in llm.calls[0].user and "010-1234-5678" not in llm.calls[0].user


@pytest.mark.parametrize("invalid", [[], [[0.0] * 1024], [[float("nan")] * 1024], [[1.0]]])
async def test_reembedding_collects_and_validates_all_batches_before_activation(
    db_session: AsyncSession,
    invalid: list[list[float]],
) -> None:
    from sqlalchemy import select

    from hiremate_ai.agents.analysis.application.index import reembed_document
    from hiremate_ai.db.document_index import DocumentIndex

    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))
    accepted = payload(scope, candidate)
    document = accepted.document.model_copy(
        update={
            "blocks": [
                DocumentParagraph(id=f"b{number}", type="paragraph", source_ids=["s1"], role="body", text=ORIGINAL)
                for number in range(5)
            ]
        }
    )
    await index_document(
        db_session, Embedder(), DocumentIndexRequest(request=accepted.request, document=document), model="old"
    )

    class InvalidLaterBatch:
        calls = 0

        async def embed(self, texts: list[str]) -> list[list[float]]:
            assert len(texts) <= 4 and all(text == ORIGINAL for text in texts)
            self.calls += 1
            return [[0.0, 1.0] + [0.0] * 1022 for _ in texts] if self.calls == 1 else invalid

    with pytest.raises(ValueError, match="embedding"):
        await reembed_document(db_session, InvalidLaterBatch(), scope, accepted.request.document_id, 1, model=MODEL)

    current = await db_session.get(DocumentIndex, accepted.request.document_id)
    chunks = list(
        await db_session.scalars(
            select(DocumentIndexChunk).where(DocumentIndexChunk.document_id == accepted.request.document_id)
        )
    )
    assert current is not None and current.model == "old" and current.revision == 1
    assert len(chunks) == 5
    assert all(chunk.model == "old" and list(chunk.embedding) == [1.0] + [0.0] * 1023 for chunk in chunks)


async def test_model_repair_does_not_expand_scope(db_session: AsyncSession) -> None:
    from hiremate_ai.db.document_index import DocumentIndex

    allowed, other_company, other_recruitment, other_stage, outside_pool = [uuid4() for _ in range(5)]
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({allowed, other_company, other_recruitment, outside_pool}))
    documents: dict[UUID, UUID] = {}
    for candidate in (allowed, other_company, other_recruitment, other_stage, outside_pool):
        own = replace(scope, company_id=uuid4()) if candidate == other_company else scope
        own = replace(own, recruitment_id=uuid4()) if candidate == other_recruitment else own
        accepted = payload(own, candidate)
        documents[candidate] = accepted.request.document_id
        await index_document(db_session, Embedder(), accepted, model="old")
    search = module.document_embedding_search(sessions_of(db_session), Embedder(), model=MODEL)

    await search(scope, ["승인"], [allowed, other_company, other_recruitment, other_stage])
    await search.wait_pending()
    db_session.expire_all()

    for candidate, document_id in documents.items():
        document = await db_session.get(DocumentIndex, document_id)
        assert document is not None and document.model == (MODEL if candidate == allowed else "old")


async def test_stale_model_repair_waits_for_new_revision_and_leaves_it_unchanged(database_url: str) -> None:
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from hiremate_ai.agents.analysis.application.index import reembed_document
    from hiremate_ai.db.document_index import DocumentIndex

    candidate = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset({candidate}))
    accepted = payload(scope, candidate)
    newer = DocumentIndexRequest(
        request=accepted.request.model_copy(update={"revision": 2}),
        document=accepted.document.model_copy(update={"revision": 2}),
    )
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine)
    entered, release = asyncio.Event(), asyncio.Event()

    class PendingReplacement:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            entered.set()
            await release.wait()
            return await Embedder().embed(texts)

    class ForbiddenEmbedder:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise AssertionError("Stale repair embedded newer revision")

    async def replace_document() -> None:
        async with sessions() as session, session.begin():
            await index_document(session, PendingReplacement(), newer, model="newest-model")

    async def repair() -> None:
        async with sessions() as session, session.begin():
            await reembed_document(session, ForbiddenEmbedder(), scope, accepted.request.document_id, 1, model=MODEL)

    replacement: asyncio.Task[None] | None = None
    stale: asyncio.Task[None] | None = None
    try:
        async with sessions() as session, session.begin():
            await index_document(session, Embedder(), accepted, model="old")
        replacement = asyncio.create_task(replace_document())
        await asyncio.wait_for(entered.wait(), timeout=5)
        stale = asyncio.create_task(repair())
        await asyncio.sleep(0.05)
        assert not stale.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(replacement, stale), timeout=5)
        async with sessions() as session:
            current = await session.get(DocumentIndex, accepted.request.document_id)
            assert current is not None and current.revision == 2 and current.model == "newest-model"
    finally:
        release.set()
        await asyncio.gather(*(task for task in (replacement, stale) if task is not None), return_exceptions=True)
        async with sessions() as session, session.begin():
            current = await session.get(DocumentIndex, accepted.request.document_id)
            if current is not None:
                await session.delete(current)
        await engine.dispose()
