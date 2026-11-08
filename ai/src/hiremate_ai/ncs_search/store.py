"""NCS 벡터 원본의 표 적재와 능력단위 목록."""

import gzip
import json
import sqlite3
import struct
from collections.abc import Iterator, Sequence
from contextlib import closing
from itertools import groupby, islice
from pathlib import Path

from pgvector import SparseVector
from pydantic import ValidationError
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.db.ncs import NcsReferenceRow, NcsTaskRow
from hiremate_ai.ncs_search.types import DENSE_DIM, SPARSE_DIM, NcsReferenceRecord, NcsTaskRecord, NcsUnit

_BATCH = 200
"""한 번에 넣는 행 수. 행마다 1024차원 벡터가 있어 너무 크게 묶지 않는다."""
_MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"


def read_reference_source(path: Path) -> Iterator[NcsReferenceRecord]:
    """완료된 로컬 BGE-M3 원본을 한 묶음씩 읽는다."""
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
        metadata = dict(db.execute("SELECT key, value FROM metadata"))
        if (
            json.loads(metadata.get("format", "null")) != "ncs-bge-m3-v1"
            or json.loads(metadata.get("dimension", "null")) != DENSE_DIM
        ):
            raise ValueError("지원하지 않는 NCS 벡터 형식입니다.")
        if json.loads(metadata.get("model_revision", "null")) != _MODEL_REVISION:
            raise ValueError("NCS 임베딩 모델 버전이 다릅니다.")
        status = db.execute("SELECT status, expected_count FROM run_state").fetchone()
        if status is None or status[0] != "completed":
            raise ValueError("NCS 임베딩이 완료되지 않았습니다.")
        count = 0
        for chunk_id, text, raw_context, dense, sparse in db.execute(
            "SELECT chunk_id, embedding_text, context_json, dense_f32_le, sparse_json FROM embeddings ORDER BY chunk_id"
        ):
            context = json.loads(raw_context)
            _, separator, body = text.partition("\n\n")
            if not separator:
                raise ValueError(f"본문 구분이 없는 NCS 묶음: {chunk_id}")
            yield NcsReferenceRecord(
                chunk_id=chunk_id,
                duty_code=context["duty_code"],
                duty_name=context["duty_name"],
                unit_code=context["unit_code"],
                unit_name=context["unit_name"],
                kind_code=context["kind_code"],
                kind_name=context["kind_name"],
                task_name=context.get("group_label") or "",
                sentences=[line.strip() for line in body.splitlines() if line.strip()],
                vectors={"dense": list(struct.unpack(f"<{DENSE_DIM}f", dense)), "sparse": json.loads(sparse)},
            )
            count += 1
        if count != status[1]:
            raise ValueError(f"NCS 벡터 건수 불일치: {count} / {status[1]}")


async def replace_reference_chunks(session: AsyncSession, records: Iterator[NcsReferenceRecord]) -> int:
    """호출자가 관리하는 트랜잭션에서 전체 자료를 교체한다."""
    await session.execute(delete(NcsReferenceRow))
    count = 0
    while batch := list(islice(records, _BATCH)):
        await session.execute(
            insert(NcsReferenceRow),
            [
                {
                    **item.model_dump(exclude={"vectors"}),
                    "dense": item.vectors.dense,
                    "sparse": SparseVector(item.vectors.sparse, SPARSE_DIM),
                }
                for item in batch
            ],
        )
        count += len(batch)
    return count


def read_export(path: Path) -> list[NcsTaskRecord]:
    """적재 파일을 읽어 검증한다. 형식이 틀리거나 같은 묶음이 두 번 나오면 줄 번호와 함께 ValueError를 낸다."""
    records: list[NcsTaskRecord] = []
    seen: set[str] = set()
    with gzip.open(path, "rt", encoding="utf-8") as file:
        for number, line in enumerate(file, 1):
            try:
                record = NcsTaskRecord.model_validate_json(line)
            except ValidationError as error:
                raise ValueError(f"{number}번 줄: {error}") from error
            if record.chunk_id in seen:
                raise ValueError(f"{number}번 줄: 같은 묶음({record.chunk_id})이 이미 있습니다.")
            seen.add(record.chunk_id)
            records.append(record)
    return records


async def replace_tasks(session: AsyncSession, records: Sequence[NcsTaskRecord]) -> int:
    """표를 비우고 records를 모두 넣는다. 커밋은 부르는 쪽이 한다."""
    await session.execute(delete(NcsTaskRow))
    for start in range(0, len(records), _BATCH):
        await session.execute(
            insert(NcsTaskRow),
            [
                {
                    "chunk_id": record.chunk_id,
                    "duty_code": record.duty_code,
                    "duty_name": record.duty_name,
                    "unit_code": record.unit_code,
                    "unit_name": record.unit_name,
                    "task_name": record.task_name,
                    "sentences": record.sentences,
                    "dense": record.vectors.dense,
                    "sparse": SparseVector(record.vectors.sparse, SPARSE_DIM),
                }
                for record in records[start : start + _BATCH]
            ],
        )
    return len(records)


async def load_units(session: AsyncSession) -> list[NcsUnit]:
    """능력단위 코드 순의 목록. 단위 안의 주요 업무 이름은 이름순이다."""
    rows = await session.execute(
        select(NcsTaskRow.unit_code, NcsTaskRow.unit_name, NcsTaskRow.duty_name, NcsTaskRow.task_name).order_by(
            NcsTaskRow.unit_code, NcsTaskRow.task_name
        )
    )
    units = []
    for code, group in groupby(rows.all(), key=lambda row: row.unit_code):
        tasks = list(group)
        units.append(
            NcsUnit(
                code=code,
                name=tasks[0].unit_name,
                duty_name=tasks[0].duty_name,
                task_names=[task.task_name for task in tasks],
            )
        )
    return units
