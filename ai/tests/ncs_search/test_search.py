from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.ncs_search.search import fuse, search_tasks
from hiremate_ai.ncs_search.store import replace_tasks
from hiremate_ai.ncs_search.types import DENSE_DIM, NcsTaskRecord, QueryVectors

U1 = "2001020211_23v6"
U2 = "2001020212_23v6"


def vectors(dense: dict[int, float], sparse: dict[int, float] | None = None) -> QueryVectors:
    values = [0.0] * DENSE_DIM
    for index, value in dense.items():
        values[index] = value
    return QueryVectors(dense=values, sparse=sparse or {9999: 1.0})


def record(chunk_id: str, unit: str, dense: dict[int, float], sparse: dict[int, float] | None = None) -> NcsTaskRecord:
    return NcsTaskRecord(
        chunk_id=chunk_id,
        duty_code=unit[:8],
        duty_name="응용SW엔지니어링",
        unit_code=unit,
        unit_name=f"{unit} 단위",
        task_name=f"{chunk_id} 업무",
        sentences=[f"{chunk_id} 문장을 수행 한다"],
        vectors=vectors(dense, sparse),
    )


def test_fuse_orders_by_reciprocal_rank_then_id() -> None:
    assert fuse([["a", "b"], ["b", "c"]], k=60) == ["b", "a", "c"]


def test_fuse_ignores_items_past_depth() -> None:
    assert fuse([["a", "b", "c"]], depth=2) == ["a", "b"]


async def seed(session: AsyncSession) -> None:
    # 질의(0번 칸)에 x가 가장 가깝고 y, z 순이다
    await replace_tasks(
        session,
        [
            record("x", U1, {0: 1.0}),
            record("y", U2, {0: 0.8, 1: 0.6}),
            record("z", U2, {0: 0.6, 1: 0.8}),
        ],
    )


async def test_search_without_units_uses_base_order(db_session: AsyncSession) -> None:
    await seed(db_session)
    query = vectors({0: 1.0})

    found = await search_tasks(db_session, query, query, [])

    assert [task.chunk_id for task in found] == ["x", "y", "z"]
    assert found[0].sentences == ["x 문장을 수행 한다"]
    assert found[0].unit_name == f"{U1} 단위"


async def test_search_prefers_selected_unit(db_session: AsyncSession) -> None:
    await seed(db_session)
    query = vectors({0: 1.0})

    found = await search_tasks(db_session, query, query, [U2])

    assert [task.chunk_id for task in found][:2] == ["y", "z"]


async def test_sparse_only_counts_overlapping_tokens(db_session: AsyncSession) -> None:
    # dense로는 x가 가깝지만 질의와 겹치는 토큰은 z에만 있다. sparse 목록에는 z만 올라 두 목록 점수를 받은 z가 1위다
    await replace_tasks(
        db_session,
        [
            record("x", U1, {0: 1.0}, {1: 1.0}),
            record("y", U2, {0: 0.8, 1: 0.6}, {2: 1.0}),
            record("z", U2, {0: 0.6, 1: 0.8}, {5: 1.0}),
        ],
    )
    query = vectors({0: 1.0}, {5: 1.0})

    found = await search_tasks(db_session, query, query, [])

    assert [task.chunk_id for task in found] == ["z", "x", "y"]


async def test_same_input_same_result(db_session: AsyncSession) -> None:
    await seed(db_session)
    original, converted = vectors({0: 1.0}), vectors({1: 1.0})

    first = await search_tasks(db_session, original, converted, [U1])
    second = await search_tasks(db_session, original, converted, [U1])

    assert first == second


async def test_search_respects_top_k(db_session: AsyncSession) -> None:
    await seed(db_session)
    query = vectors({0: 1.0})

    assert len(await search_tasks(db_session, query, query, [], top_k=2)) == 2


async def test_search_on_empty_table_returns_empty(db_session: AsyncSession) -> None:
    await replace_tasks(db_session, [])
    query = vectors({0: 1.0})

    assert await search_tasks(db_session, query, query, [U1]) == []
