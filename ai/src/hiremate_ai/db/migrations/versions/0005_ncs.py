"""NCS 자료 (직무 · 능력단위 · 능력단위요소 · 문장) 와 pgvector 확장

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 벡터 칸(embedding)을 쓰려면 DB에 pgvector 확장이 켜져 있어야 한다. compose · 테스트 이미지는 pgvector/pgvector다
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "ncs_duties",
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("major", sa.String(length=100), nullable=False),
        sa.Column("middle", sa.String(length=100), nullable=False),
        sa.Column("minor", sa.String(length=100), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.String(length=10), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_ncs_duties")),
        schema="ai",
    )
    op.create_table(
        "ncs_units",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("base_code", sa.String(length=10), nullable=False),
        sa.Column("duty_code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evaluation_points", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("basic_competencies", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("retrieved_at", sa.String(length=10), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["duty_code"],
            ["ai.ncs_duties.code"],
            name=op.f("fk_ncs_units_duty_code_ncs_duties"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_ncs_units")),
        schema="ai",
    )
    op.create_index("ix_ncs_units_base_code", "ncs_units", ["base_code"], unique=False, schema="ai")
    op.create_index("ix_ncs_units_duty_code", "ncs_units", ["duty_code"], unique=False, schema="ai")
    op.create_table(
        "ncs_elements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("unit_code", sa.String(length=20), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["unit_code"],
            ["ai.ncs_units.code"],
            name=op.f("fk_ncs_elements_unit_code_ncs_units"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ncs_elements")),
        sa.UniqueConstraint("unit_code", "number", name="uq_ncs_elements_unit_code_number"),
        schema="ai",
    )
    op.create_table(
        "ncs_statements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("element_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["ai.ncs_elements.id"],
            name=op.f("fk_ncs_statements_element_id_ncs_elements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ncs_statements")),
        schema="ai",
    )
    op.create_index("ix_ncs_statements_element_id", "ncs_statements", ["element_id"], unique=False, schema="ai")


def downgrade() -> None:
    op.drop_index("ix_ncs_statements_element_id", table_name="ncs_statements", schema="ai")
    op.drop_table("ncs_statements", schema="ai")
    op.drop_table("ncs_elements", schema="ai")
    op.drop_index("ix_ncs_units_duty_code", table_name="ncs_units", schema="ai")
    op.drop_index("ix_ncs_units_base_code", table_name="ncs_units", schema="ai")
    op.drop_table("ncs_units", schema="ai")
    op.drop_table("ncs_duties", schema="ai")
    # vector 확장은 다른 스키마도 쓸 수 있어 지우지 않는다
