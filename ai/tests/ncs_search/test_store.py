import gzip
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.ncs_search.store import load_units, read_export, replace_tasks
from hiremate_ai.ncs_search.types import DENSE_DIM, NcsTaskRecord, QueryVectors


def vectors(index: int = 0) -> QueryVectors:
    dense = [0.0] * DENSE_DIM
    dense[index] = 1.0
    return QueryVectors(dense=dense, sparse={7: 0.5})


def record(
    chunk_id: str = "chunk:1", unit: str = "2001020211_23v6", task: str = "서버 프로그램 구현하기"
) -> NcsTaskRecord:
    return NcsTaskRecord(
        chunk_id=chunk_id,
        duty_code=unit[:8],
        duty_name="응용SW엔지니어링",
        unit_code=unit,
        unit_name="서버프로그램 구현",
        task_name=task,
        sentences=["서버 프로그램을 구현 한다"],
        vectors=vectors(),
    )


def write_export(path: Path, rows: list[dict[str, Any]]) -> Path:
    with gzip.open(path, "wt", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def test_read_export_round_trips(tmp_path: Path) -> None:
    rows = [record("a"), record("b")]
    path = write_export(tmp_path / "ncs.jsonl.gz", [row.model_dump(mode="json") for row in rows])

    assert read_export(path) == rows


def test_read_export_rejects_wrong_dense_size(tmp_path: Path) -> None:
    row = record().model_dump(mode="json")
    row["vectors"]["dense"] = row["vectors"]["dense"][:-1]
    path = write_export(tmp_path / "ncs.jsonl.gz", [row])

    with pytest.raises(ValueError, match="1번 줄"):
        read_export(path)


def test_read_export_rejects_duplicate_chunk(tmp_path: Path) -> None:
    row = record().model_dump(mode="json")
    path = write_export(tmp_path / "ncs.jsonl.gz", [row, row])

    with pytest.raises(ValueError, match="2번 줄"):
        read_export(path)


def test_read_export_rejects_empty_sentence(tmp_path: Path) -> None:
    row = record().model_dump(mode="json")
    row["sentences"] = [" "]
    path = write_export(tmp_path / "ncs.jsonl.gz", [row])

    with pytest.raises(ValueError, match="1번 줄"):
        read_export(path)


async def test_replace_tasks_replaces_all_rows(db_session: AsyncSession) -> None:
    assert await replace_tasks(db_session, [record("a"), record("b")]) == 2
    assert await replace_tasks(db_session, [record("c")]) == 1

    ids = (await db_session.scalars(text("SELECT chunk_id FROM ai.ncs_tasks"))).all()
    assert ids == ["c"]


async def test_load_units_groups_tasks_by_unit(db_session: AsyncSession) -> None:
    await replace_tasks(
        db_session,
        [record("a", task="나 하기"), record("b", task="가 하기"), record("c", unit="2001010101_19v4")],
    )

    units = await load_units(db_session)

    assert [unit.code for unit in units] == ["2001010101_19v4", "2001020211_23v6"]
    assert units[1].task_names == ["가 하기", "나 하기"]
    assert units[1].duty_name == "응용SW엔지니어링"
