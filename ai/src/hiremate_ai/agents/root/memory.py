"""Root Agent의 Chat 대화방 저장소. LangGraph 체크포인터(AsyncPostgresSaver)를 ai 스키마에 둔다 (기획 15절).

대화방(thread)은 담당자별 · 전형별이고 id는 backend가 정한다. 전형이 끝나면 그 전형의 대화방을 모두 지운다.
테이블은 Alembic 리비전(0003)이 만든다. 라이브러리의 setup()은 부르지 않는다.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from hiremate_ai.config import settings
from hiremate_ai.db.base import SCHEMA


def _conninfo(database_url: str) -> str:
    """SQLAlchemy 주소(postgresql+psycopg://)를 psycopg 주소로 바꾼다."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _pool(database_url: str) -> AsyncConnectionPool[Any]:
    return AsyncConnectionPool(
        conninfo=_conninfo(database_url),
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "options": f"-c search_path={SCHEMA}",
        },
        open=False,
    )


@asynccontextmanager
async def open_saver(database_url: str | None = None) -> AsyncIterator[AsyncPostgresSaver]:
    """연결 풀을 열고 닫는 저장소. 테스트와 일회성 작업이 쓴다. 앱은 get_saver를 쓴다."""
    pool = _pool(database_url or settings.database_url)
    await pool.open()
    try:
        yield AsyncPostgresSaver(pool)
    finally:
        await pool.close()


_saver: AsyncPostgresSaver | None = None


async def get_saver() -> BaseCheckpointSaver[Any]:
    """FastAPI 의존성. 처음 부를 때 연결 풀을 열어 재사용한다. 테스트는 InMemorySaver로 바꿔 넣는다."""
    global _saver
    if _saver is None:
        pool = _pool(settings.database_url)
        await pool.open(wait=False)
        _saver = AsyncPostgresSaver(pool)
    return _saver


SaverDep = Annotated[BaseCheckpointSaver[Any], Depends(get_saver)]


async def forget_thread(saver: BaseCheckpointSaver[Any], thread_id: str) -> None:
    await saver.adelete_thread(thread_id)


async def forget_stage(saver: BaseCheckpointSaver[Any], stage_id: str) -> int:
    """전형의 대화방을 모두 지운다. 대화방 metadata의 stage_id로 찾는다. 지운 대화방 수를 돌려준다."""
    threads = {
        str(saved.config["configurable"]["thread_id"])
        async for saved in saver.alist(None, filter={"stage_id": stage_id})
    }
    for thread_id in threads:
        await saver.adelete_thread(thread_id)
    return len(threads)
