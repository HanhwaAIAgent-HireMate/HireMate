"""NCS 묶음 검색. T08에서 가장 잘 동작한 설정(원문과 변환 문장의 Dense+Sparse RRF, 고른 능력단위 결합)이다.

기존 업무 자료는 전체를 비교한다. 전체 직무 자료는 Dense와 Sparse 인덱스로 각각 후보를 찾아 결합한다.
"""

from collections.abc import Collection, Sequence

from pgvector import SparseVector
from pgvector.sqlalchemy import SPARSEVEC, Vector
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.db.ncs import NcsReferenceRow, NcsTaskRow
from hiremate_ai.ncs_search.types import DENSE_DIM, SPARSE_DIM, NcsTask, QueryVectors

RRF_K = 60
CANDIDATE_DEPTH = 50
"""목록마다 결합에 넣는 앞쪽 후보 수."""
TOP_K = 5

_DISTANCES = text(
    "SELECT chunk_id, unit_code, dense <=> :dense AS dense_distance, sparse <#> :sparse AS sparse_score "
    "FROM ai.ncs_tasks"
).bindparams(bindparam("dense", type_=Vector(DENSE_DIM)), bindparam("sparse", type_=SPARSEVEC(SPARSE_DIM)))


def fuse(lists: Sequence[Sequence[str]], *, k: int = RRF_K, depth: int = CANDIDATE_DEPTH) -> list[str]:
    """목록마다 앞 depth개에 1 / (k + 순위)를 더해 점수 순으로 합친다. 점수가 같으면 id 순이다."""
    scores: dict[str, float] = {}
    for ranked in lists:
        for rank, chunk in enumerate(ranked[:depth], 1):
            scores[chunk] = scores.get(chunk, 0.0) + 1 / (k + rank)
    return [chunk for chunk, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]


async def search_reference(
    session: AsyncSession,
    query: QueryVectors,
    converted: QueryVectors | None = None,
    units: Collection[str] = (),
    *,
    top_k: int = TOP_K,
) -> list[NcsTask]:
    """전체 자료에서 벡터 후보를 찾고 원문, 변환문, 능력단위와 희소 점수를 결합한다."""
    # pgvector 기본 탐색 폭은 40이라 limit 100을 요청해도 후보가 그보다 적을 수 있다.
    await session.execute(text("SET LOCAL hnsw.ef_search = 100"))
    rankings: list[list[str]] = []
    candidates: dict[str, NcsReferenceRow] = {}
    queries = (query,) if converted is None or converted == query else (query, converted)
    for vector in queries:
        distance = NcsReferenceRow.dense.cosine_distance(vector.dense)
        statement = select(NcsReferenceRow)
        if units:
            # 능력단위를 먼저 제한한 뒤 정확히 정렬한다. HNSW의 사후 필터로 후보를 잃지 않는다.
            statement = statement.where(NcsReferenceRow.unit_code.in_(units)).order_by(
                distance + 0.0, NcsReferenceRow.chunk_id
            )
        else:
            statement = statement.order_by(distance)
        rows = (await session.scalars(statement.limit(100))).all()
        rankings.append([row.chunk_id for row in rows])
        candidates.update((row.chunk_id, row) for row in rows)
        sparse = SparseVector(vector.sparse, SPARSE_DIM)
        score = NcsReferenceRow.sparse.max_inner_product(sparse).label("score")
        sparse_statement = select(NcsReferenceRow, score)
        if units:
            sparse_statement = sparse_statement.where(NcsReferenceRow.unit_code.in_(units)).order_by(
                score + 0.0, NcsReferenceRow.chunk_id
            )
        else:
            sparse_statement = sparse_statement.order_by(score)
        sparse_rows = (await session.execute(sparse_statement.limit(100))).all()
        rankings.append([row.chunk_id for row, value in sparse_rows if value < 0])
        candidates.update((row.chunk_id, row) for row, value in sparse_rows if value < 0)
    chosen = fuse(rankings)[:top_k]
    return [
        NcsTask(
            chunk_id=row.chunk_id,
            duty_name=row.duty_name,
            unit_code=row.unit_code,
            unit_name=row.unit_name,
            task_name=row.task_name,
            kind_code=row.kind_code,
            kind_name=row.kind_name,
            sentences=list(row.sentences),
        )
        for row in (candidates[chunk] for chunk in chosen)
    ]


async def search_tasks(
    session: AsyncSession,
    original: QueryVectors,
    converted: QueryVectors,
    units: Collection[str],
    *,
    top_k: int = TOP_K,
) -> list[NcsTask]:
    """원문 요청과 NCS식으로 바꾼 문장으로 묶음을 찾는다. units가 있으면 그 단위 안의 결과를 한 번 더 합친다."""
    base, inside = [], []
    for query in (original, converted):
        dense, sparse, unit_of = await _ranked(session, query)
        base.append(fuse([dense, sparse]))
        inside.append(fuse([[c for c in dense if unit_of[c] in units], [c for c in sparse if unit_of[c] in units]]))
    ranked = fuse(base)
    if restricted := fuse(inside):
        ranked = fuse([ranked, restricted])
    chosen = ranked[:top_k]
    rows = (await session.scalars(select(NcsTaskRow).where(NcsTaskRow.chunk_id.in_(chosen)))).all()
    by_id = {row.chunk_id: row for row in rows}
    return [
        NcsTask(
            chunk_id=chunk,
            duty_name=by_id[chunk].duty_name,
            unit_code=by_id[chunk].unit_code,
            unit_name=by_id[chunk].unit_name,
            task_name=by_id[chunk].task_name,
            sentences=list(by_id[chunk].sentences),
        )
        for chunk in chosen
    ]


async def _ranked(session: AsyncSession, query: QueryVectors) -> tuple[list[str], list[str], dict[str, str]]:
    """Dense 거리 순, 겹치는 토큰이 있는 행만의 Sparse 점수 순, 묶음 → 능력단위."""
    rows = (
        await session.execute(_DISTANCES, {"dense": query.dense, "sparse": SparseVector(query.sparse, SPARSE_DIM)})
    ).all()
    dense = [row.chunk_id for row in sorted(rows, key=lambda row: (row.dense_distance, row.chunk_id))]
    # <#>은 음의 내적이다. 겹치는 토큰이 없으면 0이라 목록에 넣지 않는다
    overlapping = [row for row in rows if row.sparse_score < 0]
    sparse = [row.chunk_id for row in sorted(overlapping, key=lambda row: (row.sparse_score, row.chunk_id))]
    return dense, sparse, {row.chunk_id: row.unit_code for row in rows}
