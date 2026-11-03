"""NCS 표 적재와 능력단위 목록. 적재 파일은 scripts/ncs_export.py가 만든 gzip JSON Lines다."""

import gzip
from collections.abc import Sequence
from itertools import groupby
from pathlib import Path

from pgvector import SparseVector
from pydantic import ValidationError
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.db.ncs import NcsTaskRow
from hiremate_ai.ncs_search.types import SPARSE_DIM, NcsTaskRecord, NcsUnit

_BATCH = 200
"""한 번에 넣는 행 수. 행마다 1024차원 벡터가 있어 너무 크게 묶지 않는다."""


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
