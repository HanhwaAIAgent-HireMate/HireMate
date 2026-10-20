from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.db.base import SCHEMA, Base, load_models
from hiremate_ai.db.session import session_factory


def test_migrations_have_single_head(alembic_config: Config) -> None:
    heads = ScriptDirectory.from_config(alembic_config).get_heads()

    assert len(heads) == 1, f"Alembic 헤드가 여러 개다. 최신 리비전에 이어 붙인다: {heads}"


def test_every_table_is_in_ai_schema() -> None:
    load_models()

    assert all(table.schema == SCHEMA for table in Base.metadata.tables.values())


async def test_migrations_use_only_ai_schema(db_session: AsyncSession) -> None:
    version = await db_session.scalar(text("SELECT version_num FROM ai.alembic_version"))
    public_version = await db_session.scalar(text("SELECT to_regclass('public.alembic_version')"))

    assert version is not None
    assert public_version is None


async def test_session_factory_connects(database_url: str) -> None:
    async with session_factory(database_url)() as session:
        assert await session.scalar(text("SELECT 1")) == 1
    await session_factory(database_url).kw["bind"].dispose()


def test_models_match_migrations(database_url: str) -> None:
    load_models()
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={"include_schemas": True, "include_name": include_ai_schema, "version_table_schema": SCHEMA},
            )
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert differences == [], "모델과 마이그레이션이 다르다. uv run alembic revision --autogenerate로 리비전을 만든다"


def include_ai_schema(name: str | None, type_: str, parent_names: object) -> bool:
    return name == SCHEMA if type_ == "schema" else True
