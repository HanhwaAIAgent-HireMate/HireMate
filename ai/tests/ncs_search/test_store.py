import gzip
import json
import sqlite3
import struct
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.ncs_search.store import load_units, read_export, replace_tasks
from hiremate_ai.ncs_search.types import DENSE_DIM, NcsTaskRecord, QueryVectors


def test_reference_record_preserves_ncs_kind_and_original_sentences() -> None:
    from hiremate_ai.ncs_search.types import NcsReferenceRecord

    value = NcsReferenceRecord(
        chunk_id="knowledge:1",
        duty_code="20010202",
        duty_name="응용SW엔지니어링",
        unit_code="2001020211_23v6",
        unit_name="서버프로그램 구현",
        kind_code="report_knowledge",
        kind_name="지식",
        task_name="",
        sentences=["자료구조 특성", "SQL 작성 방법"],
        vectors=vectors(),
    )
    assert value.kind_code == "report_knowledge"
    assert value.sentences == ["자료구조 특성", "SQL 작성 방법"]


def test_read_reference_source_preserves_vectors_and_kind(tmp_path: Path) -> None:
    from hiremate_ai.ncs_search.store import read_reference_source

    path = tmp_path / "source.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            "CREATE TABLE run_state (status TEXT, expected_count INTEGER);"
            "CREATE TABLE embeddings (chunk_id TEXT, embedding_text TEXT, context_json TEXT, "
            "dense_f32_le BLOB, sparse_json TEXT);"
        )
        db.executemany(
            "INSERT INTO metadata VALUES (?, ?)",
            [
                ("format", '"ncs-bge-m3-v1"'),
                ("dimension", "1024"),
                ("model_revision", '"5617a9f61b028005a4858fdac845db406aefb181"'),
            ],
        )
        db.execute("INSERT INTO run_state VALUES ('completed', 1)")
        context = {
            "duty_code": "20010202",
            "duty_name": "응용SW",
            "unit_code": "2001020211_23v6",
            "unit_name": "서버 구현",
            "kind_code": "report_knowledge",
            "kind_name": "지식",
        }
        dense = [1.0] + [0.0] * (DENSE_DIM - 1)
        db.execute(
            "INSERT INTO embeddings VALUES (?, ?, ?, ?, ?)",
            (
                "one",
                "제목\n\n자료구조 특성\nSQL 작성 방법",
                json.dumps(context, ensure_ascii=False),
                struct.pack("<1024f", *dense),
                '{"7": 0.5}',
            ),
        )

    rows = list(read_reference_source(path))
    assert len(rows) == 1
    assert rows[0].kind_name == "지식"
    assert rows[0].sentences == ["자료구조 특성", "SQL 작성 방법"]
    assert rows[0].vectors.dense == dense
    assert rows[0].vectors.sparse == {7: 0.5}

    with sqlite3.connect(path) as db:
        db.execute("UPDATE metadata SET value = ? WHERE key = 'model_revision'", ('"different"',))
    with pytest.raises(ValueError, match="모델 버전"):
        list(read_reference_source(path))


async def test_reference_import_stores_original_kind_and_vectors(db_session: AsyncSession) -> None:
    from hiremate_ai.ncs_search.store import replace_reference_chunks
    from hiremate_ai.ncs_search.types import NcsReferenceRecord

    item = NcsReferenceRecord(**{**record().model_dump(), "kind_code": "report_knowledge", "kind_name": "지식"})
    assert await replace_reference_chunks(db_session, iter([item])) == 1
    row = (
        await db_session.execute(
            text("SELECT chunk_id, kind_code, kind_name, sentences, vector_dims(dense) FROM ai.ncs_reference_chunks")
        )
    ).one()
    assert row == ("chunk:1", "report_knowledge", "지식", ["서버 프로그램을 구현 한다"], 1024)


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
