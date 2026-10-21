"""NCS(국가직무능력표준) 자료 테이블. 공고 작성 · 서류 평가 · 면접이 같은 자료를 DB에서 읽는다.

tools/ncs.py의 NcsData(ncs_units.json) 구조를 그대로 표로 옮겼다. 계층은 코드로 이어진다.

    ncs_duties (직무 = 세분류, 8자리 코드)
      └ ncs_units (능력단위, 버전까지 붙은 코드 예: 2001020211_23v6)   ← embedding: bge-m3 1024차원
          └ ncs_elements (능력단위요소)
              └ ncs_statements (수행준거 · 지식 · 기술 · 태도 문장)

규칙
- 공개 자료라 기업과 상관없이 같이 쓴다. 기업 · 채용 칸이 없다.
- 직무가 늘어도 표는 그대로이고 행만 늘어난다.
- 같은 능력단위의 새 버전이 들어오면 옛 버전은 active=False로 남긴다 (지운 자료를 근거로 든 공고를 추적할 수 있게).
- embedding은 임베딩 담당이 채운다. 비어 있어도 다른 기능은 동작한다.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hiremate_ai.db.base import SCHEMA, Base

EMBEDDING_DIM = 1024
"""bge-m3 임베딩 차원."""


class StatementKind(StrEnum):
    """능력단위요소 아래 문장의 종류."""

    CRITERION = "CRITERION"  # 수행준거 ('~할 수 있다')
    KNOWLEDGE = "KNOWLEDGE"  # 지식
    SKILL = "SKILL"  # 기술
    ATTITUDE = "ATTITUDE"  # 태도


class NcsDutyRow(Base):
    """NCS 직무(세분류) 하나. 대 · 중 · 소분류 이름도 함께 둔다."""

    __tablename__ = "ncs_duties"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)  # 세분류 코드 (예: 20010202)
    name: Mapped[str] = mapped_column(String(100))  # 세분류 이름 (예: 응용SW엔지니어링)
    definition: Mapped[str] = mapped_column(Text)
    major: Mapped[str] = mapped_column(String(100))  # 대분류
    middle: Mapped[str] = mapped_column(String(100))  # 중분류
    minor: Mapped[str] = mapped_column(String(100))  # 소분류
    source: Mapped[str] = mapped_column(Text)  # 자료 출처 (공공데이터포털 데이터셋 이름)
    retrieved_at: Mapped[str] = mapped_column(String(10))  # 자료를 받은 날짜 (YYYY-MM-DD)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NcsUnitRow(Base):
    """NCS 능력단위 하나."""

    __tablename__ = "ncs_units"
    __table_args__ = (
        Index("ix_ncs_units_duty_code", "duty_code"),
        Index("ix_ncs_units_base_code", "base_code"),
    )

    code: Mapped[str] = mapped_column(String(20), primary_key=True)  # 버전까지 (예: 2001020211_23v6)
    base_code: Mapped[str] = mapped_column(String(10))  # 버전을 뗀 코드 (예: 2001020211). 버전끼리 묶을 때 쓴다
    duty_code: Mapped[str] = mapped_column(ForeignKey(f"{SCHEMA}.ncs_duties.code", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    level: Mapped[int] = mapped_column(Integer)  # 능력단위 수준 1~8
    definition: Mapped[str] = mapped_column(Text)
    # 공고에는 덜 쓰는 자료라 표로 나누지 않고 JSON 그대로 둔다
    scope: Mapped[dict[str, list[str]]] = mapped_column(JSONB)  # 적용범위 및 작업상황
    evaluation_points: Mapped[list[str]] = mapped_column(JSONB)  # 평가 시 고려사항
    basic_competencies: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # 직업기초능력
    active: Mapped[bool] = mapped_column(Boolean)  # 같은 능력단위의 최신 버전만 True
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))  # 이름 + 정의의 bge-m3 임베딩
    retrieved_at: Mapped[str] = mapped_column(String(10))
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    elements: Mapped[list["NcsElementRow"]] = relationship(
        back_populates="unit", cascade="all, delete-orphan", lazy="selectin", order_by="NcsElementRow.number"
    )


class NcsElementRow(Base):
    """능력단위요소 하나. 같은 능력단위 안에서 number가 겹치지 않는다."""

    __tablename__ = "ncs_elements"
    __table_args__ = (UniqueConstraint("unit_code", "number", name="uq_ncs_elements_unit_code_number"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    unit_code: Mapped[str] = mapped_column(ForeignKey(f"{SCHEMA}.ncs_units.code", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)  # 능력단위 안의 요소 번호 (1, 2, 3 …)
    name: Mapped[str] = mapped_column(String(200))

    unit: Mapped[NcsUnitRow] = relationship(back_populates="elements")
    statements: Mapped[list["NcsStatementRow"]] = relationship(
        back_populates="element",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="NcsStatementRow.position",  # 종류별로 나누는 일은 읽는 쪽(ncs_store)이 한다
    )


class NcsStatementRow(Base):
    """수행준거 · 지식 · 기술 · 태도 문장 하나. position은 같은 종류 안에서의 순서다."""

    __tablename__ = "ncs_statements"
    __table_args__ = (Index("ix_ncs_statements_element_id", "element_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    element_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.ncs_elements.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))  # StatementKind 값
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    element: Mapped[NcsElementRow] = relationship(back_populates="statements")
