"""ai 스키마의 테이블 기반. backend가 Flyway로 관리하는 public 스키마에는 테이블을 만들지 않는다."""

import importlib
import pkgutil

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "ai"


class Base(DeclarativeBase):
    """모든 ai 테이블의 기반. 테이블은 ai 스키마에 생기고 제약 이름은 아래 규칙으로 붙는다."""

    metadata = MetaData(
        schema=SCHEMA,
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    )


def load_models() -> None:
    """db/ 아래 모듈을 모두 불러 테이블을 Base.metadata에 등록한다. 마이그레이션과 테스트가 쓴다."""
    package = importlib.import_module(__package__ or "hiremate_ai.db")
    for module in pkgutil.iter_modules(package.__path__, f"{package.__name__}."):
        if module.name != f"{package.__name__}.migrations":
            importlib.import_module(module.name)
