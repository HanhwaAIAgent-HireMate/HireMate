from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer

AI_DIR = Path(__file__).resolve().parents[1]

# compose.yaml과 같은 이미지
POSTGRES_IMAGE = "pgvector/pgvector:pg17"


def _alembic_config(database_url: str | None = None) -> Config:
    config = Config(toml_file=AI_DIR / "pyproject.toml")
    if database_url is not None:
        config.attributes["database_url"] = database_url
    return config


@pytest.fixture
def alembic_config() -> Config:
    """DB 주소 없이 리비전 파일만 볼 때 쓰는 Alembic 설정."""
    return _alembic_config()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """테스트용 PostgreSQL을 띄우고 ai 마이그레이션을 끝까지 적용한 주소. Docker가 필요하다."""
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as postgres:
        url = postgres.get_connection_url()
        command.upgrade(_alembic_config(url), "head")
        yield url


@pytest.fixture
async def db_session(database_url: str) -> AsyncIterator[AsyncSession]:
    """테스트마다 트랜잭션 안에서 쓰는 세션. 커밋해도 테스트가 끝나면 모두 되돌린다."""
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
