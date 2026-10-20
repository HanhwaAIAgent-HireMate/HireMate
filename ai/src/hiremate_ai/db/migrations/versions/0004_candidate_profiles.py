"""지원자 프로필

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("recruitment_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("career_years", sa.Integer(), nullable=True),
        sa.Column("last_company", sa.String(length=200), nullable=True),
        sa.Column("document_score", sa.Integer(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_profiles")),
        sa.UniqueConstraint("application_id", name=op.f("uq_candidate_profiles_application_id")),
        schema="ai",
    )
    op.create_index(
        "ix_candidate_profiles_scope", "candidate_profiles", ["company_id", "recruitment_id"], unique=False, schema="ai"
    )
    op.create_table(
        "profile_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("agent", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("stage_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["ai.candidate_profiles.id"],
            name=op.f("fk_profile_items_profile_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_items")),
        schema="ai",
    )
    op.create_index("ix_profile_items_profile_id", "profile_items", ["profile_id"], unique=False, schema="ai")


def downgrade() -> None:
    op.drop_index("ix_profile_items_profile_id", table_name="profile_items", schema="ai")
    op.drop_table("profile_items", schema="ai")
    op.drop_index("ix_candidate_profiles_scope", table_name="candidate_profiles", schema="ai")
    op.drop_table("candidate_profiles", schema="ai")
