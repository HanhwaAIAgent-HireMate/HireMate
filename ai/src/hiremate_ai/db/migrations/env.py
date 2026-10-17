"""Alembic 실행 환경. ai 스키마만 다룬다. public 스키마는 backend가 Flyway로 관리하므로 비교 대상에서 뺀다."""

from alembic import context
from sqlalchemy import create_engine, pool, text

from hiremate_ai.config import settings
from hiremate_ai.db.base import SCHEMA, Base, load_models

load_models()

config = context.config
database_url: str = config.attributes.get("database_url", settings.database_url)


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    return name == SCHEMA if type_ == "schema" else True


def run_offline() -> None:
    context.configure(
        url=database_url,
        literal_binds=True,
        target_metadata=Base.metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        context.run_migrations()


def run_online() -> None:
    engine = create_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            version_table_schema=SCHEMA,
            include_schemas=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
