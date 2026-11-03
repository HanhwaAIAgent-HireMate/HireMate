"""NCS 정보기술 '책임 및 역할' 묶음과 BGE-M3 벡터

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import SPARSEVEC, Vector
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "ncs_tasks",
        sa.Column("chunk_id", sa.String(length=80), nullable=False),
        sa.Column("duty_code", sa.String(length=8), nullable=False),
        sa.Column("duty_name", sa.String(length=100), nullable=False),
        sa.Column("unit_code", sa.String(length=20), nullable=False),
        sa.Column("unit_name", sa.String(length=200), nullable=False),
        sa.Column("task_name", sa.String(length=200), nullable=False),
        sa.Column("sentences", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("dense", Vector(1024), nullable=False),
        sa.Column("sparse", SPARSEVEC(250002), nullable=False),
        sa.PrimaryKeyConstraint("chunk_id", name=op.f("pk_ncs_tasks")),
        schema="ai",
    )
    op.create_index(op.f("ix_ai_ncs_tasks_unit_code"), "ncs_tasks", ["unit_code"], unique=False, schema="ai")


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_ncs_tasks_unit_code"), table_name="ncs_tasks", schema="ai")
    op.drop_table("ncs_tasks", schema="ai")
    # vector 확장은 다른 스키마도 쓸 수 있어 지우지 않는다 (0005와 같다)
