"""지원서 분석 결과

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("recruitment_id", sa.Uuid(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("review_version", sa.String(length=20), nullable=False),
        sa.Column("review", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_reviews")),
        sa.UniqueConstraint("application_id", "input_hash", name=op.f("uq_application_reviews_application_id")),
        schema="ai",
    )
    op.create_index(
        "ix_application_reviews_scope",
        "application_reviews",
        ["company_id", "recruitment_id"],
        unique=False,
        schema="ai",
    )


def downgrade() -> None:
    op.drop_index("ix_application_reviews_scope", table_name="application_reviews", schema="ai")
    op.drop_table("application_reviews", schema="ai")
