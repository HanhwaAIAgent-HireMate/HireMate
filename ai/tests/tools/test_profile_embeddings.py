from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.db.profile import ItemAgent, ItemCategory
from hiremate_ai.db.profile_store import NewItem, save_profile
from hiremate_ai.tools import profile_search
from hiremate_ai.tools.scope import ToolScope


class FakeEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [([1.0, 0.0] if "승인" in text or "금융" in text else [0.0, 1.0]) + [0.0] * 1022 for text in texts]


async def test_semantic_search_finds_related_profile_within_scope(db_session: AsyncSession) -> None:
    company_id, recruitment_id, application_id = uuid4(), uuid4(), uuid4()
    other_company, other_application = uuid4(), uuid4()
    for company, candidate in ((company_id, application_id), (other_company, other_application)):
        await save_profile(
            db_session,
            company_id=company,
            recruitment_id=recruitment_id,
            application_id=candidate,
            agent=ItemAgent.APPLICATION,
            items=[
                NewItem(
                    category=ItemCategory.EXPERIENCE,
                    content="승인 서버 개발",
                    evidence="승인 서버 개발",
                    source="이력서",
                )
            ],
        )
    assert hasattr(profile_search, "index_profile_embeddings")
    embedder = FakeEmbedder()
    await profile_search.index_profile_embeddings(db_session, embedder, company_id, recruitment_id, application_id)
    await profile_search.index_profile_embeddings(
        db_session, embedder, other_company, recruitment_id, other_application
    )
    scope = ToolScope(company_id, recruitment_id, uuid4(), frozenset({application_id, other_application}))

    found = await profile_search.search_profile_embeddings(
        db_session, embedder, scope, ["금융 개발"], [application_id, other_application]
    )

    assert [match.application_id for match in found] == [application_id]
    assert found[0].sentences[0].sentence == "승인 서버 개발"


async def test_semantic_search_reports_unindexed_profiles(db_session: AsyncSession) -> None:
    from root_context import sessions_of

    from hiremate_ai.tools.candidates import SearchResults
    from hiremate_ai.tools.profile_search import profile_embedding_search

    company_id, recruitment_id, application_id = uuid4(), uuid4(), uuid4()
    scope = ToolScope(company_id, recruitment_id, uuid4(), frozenset({application_id}))
    search = profile_embedding_search(sessions_of(db_session), FakeEmbedder(), model="BAAI/bge-m3")

    found = await search(scope, ["금융 개발"], [application_id])

    assert isinstance(found, SearchResults)
    assert not found
    assert found.warnings and "불완전" in found.warnings[0]


async def test_backfill_indexes_only_requested_recruitment(db_session: AsyncSession) -> None:
    from root_context import sessions_of

    from hiremate_ai.db.profile import CandidateProfile

    company_id, recruitment_id, other_recruitment = uuid4(), uuid4(), uuid4()
    candidates = [uuid4(), uuid4()]
    for recruitment, candidate in zip((recruitment_id, other_recruitment), candidates, strict=True):
        await save_profile(
            db_session,
            company_id=company_id,
            recruitment_id=recruitment,
            application_id=candidate,
            agent=ItemAgent.APPLICATION,
            items=[
                NewItem(
                    category=ItemCategory.EXPERIENCE, content="승인 서버", evidence="승인 서버 개발", source="이력서"
                )
            ],
        )
    assert hasattr(profile_search, "backfill_profile_embeddings")

    await db_session.commit()
    count = await profile_search.backfill_profile_embeddings(
        sessions_of(db_session), FakeEmbedder(), company_id, recruitment_id
    )
    db_session.expire_all()

    profiles = (await db_session.scalars(select(CandidateProfile).order_by(CandidateProfile.recruitment_id))).all()
    by_id = {profile.application_id: profile for profile in profiles}
    assert count == 1
    assert by_id[candidates[0]].items[0].embedding is not None
    assert by_id[candidates[1]].items[0].embedding is None


async def test_semantic_search_failure_is_reported(db_session: AsyncSession) -> None:
    from root_context import sessions_of

    from hiremate_ai.ncs_search.reference import NcsUnavailable
    from hiremate_ai.tools.candidates import SearchResults
    from hiremate_ai.tools.profile_search import profile_embedding_search

    company_id, recruitment_id, application_id = uuid4(), uuid4(), uuid4()
    await save_profile(
        db_session,
        company_id=company_id,
        recruitment_id=recruitment_id,
        application_id=application_id,
        agent=ItemAgent.APPLICATION,
        items=[
            NewItem(category=ItemCategory.EXPERIENCE, content="승인 서버", evidence="승인 서버 개발", source="이력서")
        ],
    )
    await profile_search.index_profile_embeddings(
        db_session, FakeEmbedder(), company_id, recruitment_id, application_id
    )

    class Offline:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise NcsUnavailable("offline")

    scope = ToolScope(company_id, recruitment_id, uuid4(), frozenset({application_id}))
    search = profile_embedding_search(sessions_of(db_session), Offline(), model="BAAI/bge-m3")

    found = await search(scope, ["금융 개발"], [application_id])

    assert isinstance(found, SearchResults)
    assert not found
    assert found.warnings and "실패" in found.warnings[0]


async def test_reanalyzed_profile_does_not_reuse_old_vectors(db_session: AsyncSession) -> None:
    company_id, recruitment_id, application_id = uuid4(), uuid4(), uuid4()
    first = NewItem(category=ItemCategory.EXPERIENCE, content="승인 서버", evidence="승인 서버 개발", source="이력서")
    await save_profile(
        db_session,
        company_id=company_id,
        recruitment_id=recruitment_id,
        application_id=application_id,
        agent=ItemAgent.APPLICATION,
        items=[first],
    )
    embedder = FakeEmbedder()
    await profile_search.index_profile_embeddings(db_session, embedder, company_id, recruitment_id, application_id)
    replacement = NewItem(category=ItemCategory.EXPERIENCE, content="화면 개발", evidence="화면 개발", source="이력서")
    await save_profile(
        db_session,
        company_id=company_id,
        recruitment_id=recruitment_id,
        application_id=application_id,
        agent=ItemAgent.APPLICATION,
        items=[replacement],
    )
    await profile_search.index_profile_embeddings(db_session, embedder, company_id, recruitment_id, application_id)
    scope = ToolScope(company_id, recruitment_id, uuid4(), frozenset({application_id}))

    found = await profile_search.search_profile_embeddings(db_session, embedder, scope, ["금융 개발"], [application_id])

    assert not found


async def test_index_timeout_does_not_fail_application_analysis() -> None:
    from uuid import UUID

    from hiremate_ai.tools.profile_search import index_profile_safely

    async def slow(company: UUID, recruitment: UUID, application: UUID) -> None:
        raise TimeoutError("timeout")

    await index_profile_safely(slow, uuid4(), uuid4(), uuid4())


async def test_backfill_keeps_completed_profiles_when_embedding_fails(db_session: AsyncSession) -> None:
    from root_context import sessions_of

    from hiremate_ai.db.profile import CandidateProfile
    from hiremate_ai.ncs_search.reference import NcsUnavailable

    company_id, recruitment_id = uuid4(), uuid4()
    for application_id in (uuid4(), uuid4()):
        await save_profile(
            db_session,
            company_id=company_id,
            recruitment_id=recruitment_id,
            application_id=application_id,
            agent=ItemAgent.APPLICATION,
            items=[
                NewItem(
                    category=ItemCategory.EXPERIENCE, content="승인 서버", evidence="승인 서버 개발", source="이력서"
                )
            ],
        )
    await db_session.commit()

    class FailsOnSecond(FakeEmbedder):
        calls = 0

        async def embed(self, texts: list[str]) -> list[list[float]]:
            self.calls += 1
            if self.calls == 2:
                raise NcsUnavailable("offline")
            return await super().embed(texts)

    with pytest.raises(NcsUnavailable):
        await profile_search.backfill_profile_embeddings(
            sessions_of(db_session), FailsOnSecond(), company_id, recruitment_id
        )
    db_session.expire_all()
    profiles = (await db_session.scalars(select(CandidateProfile))).all()

    assert sum(profile.items[0].embedding is not None for profile in profiles) == 1


async def test_index_keeps_finished_batches_when_embedding_fails(db_session: AsyncSession) -> None:
    from root_context import sessions_of

    from hiremate_ai.db.profile import CandidateProfile
    from hiremate_ai.ncs_search.reference import NcsUnavailable

    company_id, recruitment_id, application_id = uuid4(), uuid4(), uuid4()
    await save_profile(
        db_session,
        company_id=company_id,
        recruitment_id=recruitment_id,
        application_id=application_id,
        agent=ItemAgent.APPLICATION,
        items=[
            NewItem(
                category=ItemCategory.EXPERIENCE, content=f"승인 서버 {n}", evidence=f"승인 서버 {n}", source="이력서"
            )
            for n in range(5)
        ],
    )
    await db_session.commit()

    class FailsOnSecond(FakeEmbedder):
        calls = 0

        async def embed(self, texts: list[str]) -> list[list[float]]:
            self.calls += 1
            if self.calls == 2:
                raise NcsUnavailable("offline")
            return await super().embed(texts)

    index = profile_search.profile_indexer(sessions_of(db_session), FailsOnSecond())

    with pytest.raises(NcsUnavailable):
        await index(company_id, recruitment_id, application_id)
    db_session.expire_all()
    profile = await db_session.scalar(select(CandidateProfile).where(CandidateProfile.application_id == application_id))

    assert profile is not None
    assert sum(item.embedding is not None for item in profile.items) == 4


async def test_search_retries_missing_index_and_uses_it_next_time(db_session: AsyncSession) -> None:
    from root_context import sessions_of

    from hiremate_ai.tools.candidates import SearchResults
    from hiremate_ai.tools.profile_search import profile_embedding_search

    company_id, recruitment_id, application_id = uuid4(), uuid4(), uuid4()
    await save_profile(
        db_session,
        company_id=company_id,
        recruitment_id=recruitment_id,
        application_id=application_id,
        agent=ItemAgent.APPLICATION,
        items=[
            NewItem(category=ItemCategory.EXPERIENCE, content="승인 서버", evidence="승인 서버 개발", source="이력서")
        ],
    )
    await db_session.commit()
    scope = ToolScope(company_id, recruitment_id, uuid4(), frozenset({application_id}))
    search = profile_embedding_search(sessions_of(db_session), FakeEmbedder(), model="BAAI/bge-m3")

    first = await search(scope, ["금융 개발"], [application_id])
    assert isinstance(first, SearchResults) and first.warnings
    await search.wait_pending()
    second = await search(scope, ["금융 개발"], [application_id])

    assert [match.application_id for match in second] == [application_id]
    assert isinstance(second, SearchResults) and not second.warnings


async def test_search_retries_after_embedding_service_recovers(db_session: AsyncSession) -> None:
    from root_context import sessions_of

    from hiremate_ai.ncs_search.reference import NcsUnavailable
    from hiremate_ai.tools.profile_search import profile_embedding_search

    company_id, recruitment_id, application_id = uuid4(), uuid4(), uuid4()
    await save_profile(
        db_session,
        company_id=company_id,
        recruitment_id=recruitment_id,
        application_id=application_id,
        agent=ItemAgent.APPLICATION,
        items=[
            NewItem(category=ItemCategory.EXPERIENCE, content="승인 서버", evidence="승인 서버 개발", source="이력서")
        ],
    )
    await db_session.commit()

    class UnavailableOnce(FakeEmbedder):
        calls = 0

        async def embed(self, texts: list[str]) -> list[list[float]]:
            self.calls += 1
            if self.calls == 1:
                raise NcsUnavailable("offline")
            return await super().embed(texts)

    scope = ToolScope(company_id, recruitment_id, uuid4(), frozenset({application_id}))
    search = profile_embedding_search(sessions_of(db_session), UnavailableOnce(), model="BAAI/bge-m3")
    await search(scope, ["금융 개발"], [application_id])
    await search.wait_pending()
    await search(scope, ["금융 개발"], [application_id])
    await search.wait_pending()

    found = await search(scope, ["금융 개발"], [application_id])

    assert [match.application_id for match in found] == [application_id]


async def test_embedding_does_not_index_protected_attributes(db_session: AsyncSession) -> None:
    company_id, recruitment_id, application_id = uuid4(), uuid4(), uuid4()
    await save_profile(
        db_session,
        company_id=company_id,
        recruitment_id=recruitment_id,
        application_id=application_id,
        agent=ItemAgent.APPLICATION,
        items=[
            NewItem(
                category=ItemCategory.EXPERIENCE,
                content="나이 50세에 승인 서버를 개발했다",
                evidence="나이 50세에 승인 서버를 개발했습니다.",
                source="이력서",
            )
        ],
    )

    class RecordingEmbedder(FakeEmbedder):
        calls = 0

        async def embed(self, texts: list[str]) -> list[list[float]]:
            self.calls += 1
            return await super().embed(texts)

    embedder = RecordingEmbedder()
    await profile_search.index_profile_embeddings(db_session, embedder, company_id, recruitment_id, application_id)

    assert embedder.calls == 0


async def test_embedding_indexes_experiences_without_posting_verdicts(db_session: AsyncSession) -> None:
    company_id, recruitment_id, application_id = uuid4(), uuid4(), uuid4()
    await save_profile(
        db_session,
        company_id=company_id,
        recruitment_id=recruitment_id,
        application_id=application_id,
        agent=ItemAgent.APPLICATION,
        items=[
            NewItem(category=ItemCategory.QUALIFICATION, content="요건 충족", evidence="서버 개발자", source="이력서"),
            NewItem(
                category=ItemCategory.EXPERIENCE, content="승인 서버 개발", evidence="승인 서버 개발", source="이력서"
            ),
        ],
    )

    class RecordingEmbedder(FakeEmbedder):
        texts: list[str] = []

        async def embed(self, texts: list[str]) -> list[list[float]]:
            self.texts.extend(texts)
            return await super().embed(texts)

    embedder = RecordingEmbedder()
    await profile_search.index_profile_embeddings(db_session, embedder, company_id, recruitment_id, application_id)

    assert len(embedder.texts) == 1
    assert "승인 서버" in embedder.texts[0]
