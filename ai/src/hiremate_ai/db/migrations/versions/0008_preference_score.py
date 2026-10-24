"""지원자 프로필의 서류 점수를 소수 첫째 자리까지 (우대사항 충족 점수)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "candidate_profiles",
        "document_score",
        type_=sa.Numeric(4, 1),
        existing_type=sa.Integer(),
        existing_nullable=True,
        schema="ai",
    )


def downgrade() -> None:
    op.alter_column(
        "candidate_profiles",
        "document_score",
        type_=sa.Integer(),
        existing_type=sa.Numeric(4, 1),
        existing_nullable=True,
        postgresql_using="round(document_score)::integer",
        schema="ai",
    )
