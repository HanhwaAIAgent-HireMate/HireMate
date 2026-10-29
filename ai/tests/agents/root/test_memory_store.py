"""Root 대화방 저장소(LangGraph 체크포인터)를 실제 PostgreSQL에서 확인한다. Docker가 필요하다."""

from collections.abc import AsyncIterator
from typing import cast

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import CheckpointMetadata, empty_checkpoint
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import create_engine, text

from hiremate_ai.agents.root.memory import forget_thread, open_saver


@pytest.fixture
async def saver(database_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    async with open_saver(database_url) as opened:
        yield opened


def test_migration_creates_checkpoint_tables_in_ai_schema(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            tables = set(
                connection.scalars(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'ai'"))
            )
            versions = list(connection.scalars(text("SELECT v FROM ai.checkpoint_migrations ORDER BY v")))
    finally:
        engine.dispose()

    assert {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"} <= tables
    assert versions == list(range(10))


async def put(saver: AsyncPostgresSaver, thread_id: str, stage_id: str) -> None:
    """대화방 하나를 만든다. 그래프는 실행 config의 metadata(stage_id)를 체크포인트 metadata에 남긴다."""
    config: RunnableConfig = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    metadata = cast(CheckpointMetadata, {"stage_id": stage_id})
    await saver.aput(config, empty_checkpoint(), metadata, {})


async def test_saver_round_trip_and_forget(saver: AsyncPostgresSaver) -> None:
    await put(saver, "c:s1:t1", "s1")

    assert await saver.aget_tuple({"configurable": {"thread_id": "c:s1:t1"}}) is not None
    await forget_thread(saver, "c:s1:t1")
    assert await saver.aget_tuple({"configurable": {"thread_id": "c:s1:t1"}}) is None


async def test_forget_removes_only_that_tab_thread(saver: AsyncPostgresSaver) -> None:
    await put(saver, "c:s1:t1", "s1")
    await put(saver, "c:s1:t2", "s1")

    await forget_thread(saver, "c:s1:t1")

    assert await saver.aget_tuple({"configurable": {"thread_id": "c:s1:t1"}}) is None
    assert await saver.aget_tuple({"configurable": {"thread_id": "c:s1:t2"}}) is not None
