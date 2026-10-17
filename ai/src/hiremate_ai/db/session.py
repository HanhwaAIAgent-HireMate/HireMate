"""ai 스키마 DB 세션. 엔진은 처음 쓸 때 만든다."""

from collections.abc import AsyncIterator
from functools import cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hiremate_ai.config import settings


@cache
def session_factory(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    """database_url이 없으면 settings.database_url을 쓴다. 주소마다 엔진을 하나만 만든다."""
    engine = create_async_engine(database_url or settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 의존성. 요청마다 세션을 열고 닫는다. 커밋은 쓰는 쪽이 한다."""
    async with session_factory()() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
"""라우터 매개변수 타입. 예: async def analyze(request: AnalyzeRequest, session: SessionDep) -> CandidateAnalysis"""
