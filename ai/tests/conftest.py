import asyncio
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from langsmith import tracing_context
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent
from hiremate_ai.llm.tracing import traced

AI_DIR = Path(__file__).resolve().parents[1]
SAMPLES_DIR = AI_DIR / "tests" / "samples"

# compose.yaml과 같은 이미지
POSTGRES_IMAGE = "pgvector/pgvector:pg17"


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]]:
    """async 테스트를 SelectorEventLoop에서 돌린다.

    Windows 기본 루프(ProactorEventLoop)에서는 psycopg가 async로 DB에 붙지 못한다.
    Linux · macOS는 원래 SelectorEventLoop라 동작이 같다.
    """
    return {"selector": asyncio.SelectorEventLoop}


@pytest.fixture(autouse=True)
def langsmith_tracing(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """LangSmith 추적은 실제 모델 평가(tests/eval)만 LANGSMITH_TRACING을 따른다.

    다른 테스트는 ai/.env나 환경 변수로 추적을 켜 두어도 기록을 보내지 않는다.
    """
    if request.path.parent.name == "eval":
        with traced():
            yield
        return
    monkeypatch.setattr(settings, "langsmith_tracing", False)
    with tracing_context(enabled=False):
        yield


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


@pytest.fixture(scope="session")
def sample_posting() -> PostingContent:
    """가상 공고: 결제 플랫폼 백엔드 개발자 (tests/samples/README.md)."""
    return PostingContent.model_validate_json((SAMPLES_DIR / "posting.json").read_bytes())


@pytest.fixture(scope="session")
def sample_company() -> CompanyProfile:
    return CompanyProfile.model_validate_json((SAMPLES_DIR / "company.json").read_bytes())


@pytest.fixture(scope="session")
def sample_applicants() -> dict[str, ApplicantDetail]:
    """가상 지원자 8명. 이름으로 찾는다. 지원자별 정답은 tests/samples/README.md에 있다."""
    applicants = TypeAdapter(list[ApplicantDetail]).validate_json((SAMPLES_DIR / "applicants.json").read_bytes())
    return {applicant.info.name: applicant for applicant in applicants}
