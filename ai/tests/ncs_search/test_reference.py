import json
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text

from hiremate_ai.db.session import session_factory
from hiremate_ai.ncs_search.reference import DbNcsReference, EmbedClient, NcsUnavailable
from hiremate_ai.ncs_search.store import replace_reference_chunks, replace_tasks
from hiremate_ai.ncs_search.types import DENSE_DIM, NcsReferenceRecord, NcsTaskRecord, QueryVectors

URL = "http://ncs-embed.test"


def vectors(index: int = 0) -> QueryVectors:
    dense = [0.0] * DENSE_DIM
    dense[index] = 1.0
    return QueryVectors(dense=dense, sparse={7: 0.5})


def embed_client(handler: httpx.MockTransport) -> EmbedClient:
    return EmbedClient(httpx.AsyncClient(transport=handler), URL)


def answering(requests: list[dict[str, list[str]]]) -> httpx.MockTransport:
    """받은 본문을 기록하고 글마다 벡터를 돌려주는 임베딩 서비스."""

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={"vectors": [vectors().model_dump(mode="json") for _ in body["texts"]]})

    return httpx.MockTransport(handle)


async def test_embed_parses_vectors() -> None:
    requests: list[dict[str, list[str]]] = []

    result = await embed_client(answering(requests)).embed(["가", "나"])

    assert result == [vectors(), vectors()]
    assert requests == [{"texts": ["가", "나"]}]


async def test_rejected_text_raises_unavailable() -> None:
    client = embed_client(httpx.MockTransport(lambda request: httpx.Response(422, json={"detail": "too long"})))

    with pytest.raises(NcsUnavailable):
        await client.embed(["가" * 2001])


async def test_connection_error_raises_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(NcsUnavailable):
        await embed_client(httpx.MockTransport(refuse)).embed(["가"])


async def test_malformed_response_raises_unavailable() -> None:
    client = embed_client(httpx.MockTransport(lambda request: httpx.Response(200, json={"vectors": [{"dense": []}]})))

    with pytest.raises(NcsUnavailable):
        await client.embed(["가"])


def record(chunk_id: str, unit: str = "2001020211_23v6") -> NcsTaskRecord:
    return NcsTaskRecord(
        chunk_id=chunk_id,
        duty_code=unit[:8],
        duty_name="응용SW엔지니어링",
        unit_code=unit,
        unit_name="서버프로그램 구현",
        task_name=f"{chunk_id} 업무",
        sentences=[f"{chunk_id} 문장을 수행 한다"],
        vectors=vectors(),
    )


@pytest.fixture
async def loaded(database_url: str) -> AsyncIterator[str]:
    """DbNcsReference가 자기 세션을 열므로 커밋해 넣고 끝나면 지운다."""
    async with session_factory(database_url)() as session:
        await replace_tasks(session, [record("a"), record("b", unit="2001010101_19v4")])
        await session.commit()
    yield database_url
    async with session_factory(database_url)() as session:
        await session.execute(text("DELETE FROM ai.ncs_tasks"))
        await session.commit()


async def test_search_embeds_request_and_joined_tasks_once(loaded: str) -> None:
    requests: list[dict[str, list[str]]] = []
    reference = DbNcsReference(session_factory(loaded), embed_client(answering(requests)))

    found = await reference.search("주문 API 개발자 공고", ["업무 하나", "업무 둘"], ["2001020211_23v6"])

    assert requests == [{"texts": ["주문 API 개발자 공고", "업무 하나 업무 둘"]}]
    assert [task.chunk_id for task in found][0] == "a"
    assert {task.chunk_id for task in found} == {"a", "b"}


async def test_search_without_tasks_embeds_request_once(loaded: str) -> None:
    requests: list[dict[str, list[str]]] = []
    reference = DbNcsReference(session_factory(loaded), embed_client(answering(requests)))

    await reference.search("주문 API", [], [])

    assert requests == [{"texts": ["주문 API"]}]


async def test_search_and_unit_shortlist_use_full_reference(loaded: str) -> None:
    item = NcsReferenceRecord(**{**record("full").model_dump(), "kind_code": "knowledge", "kind_name": "지식"})
    sessions = session_factory(loaded)
    async with sessions() as session:
        await replace_reference_chunks(session, iter([item]))
        await session.commit()
    try:
        reference = DbNcsReference(sessions, embed_client(answering([])))
        units = await reference.units_for("배치", "개발자")
        found = await reference.search("배치", [], [item.unit_code])
        assert [unit.code for unit in units] == [item.unit_code]
        assert [result.kind_name for result in found] == ["지식"]
    finally:
        async with sessions() as session:
            await session.execute(text("DELETE FROM ai.ncs_reference_chunks"))
            await session.commit()


async def test_units_cached_after_first_nonempty_load(loaded: str) -> None:
    reference = DbNcsReference(session_factory(loaded), embed_client(answering([])))

    first = await reference.units()
    async with session_factory(loaded)() as session:
        await session.execute(text("DELETE FROM ai.ncs_tasks"))
        await session.commit()

    assert [unit.code for unit in first] == ["2001010101_19v4", "2001020211_23v6"]
    assert await reference.units() == first


async def test_unreachable_db_raises_unavailable() -> None:
    sessions = session_factory("postgresql+psycopg://nobody:nobody@127.0.0.1:1/none")
    reference = DbNcsReference(sessions, embed_client(answering([])))

    with pytest.raises(NcsUnavailable):
        await reference.units()
    with pytest.raises(NcsUnavailable):
        await reference.search("주문 API", ["업무"], [])
