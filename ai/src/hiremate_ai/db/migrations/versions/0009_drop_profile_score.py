"""지원자 프로필에서 서류 점수와 AI 기준 통과 여부를 뺀다 (서류는 점수를 매기지 않는다)

Revision ID: 0009
Revises: 5f1249530489
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "5f1249530489"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("candidate_profiles", "document_score", schema="ai")
    op.drop_column("candidate_profiles", "passed", schema="ai")


def downgrade() -> None:
    op.add_column("candidate_profiles", sa.Column("passed", sa.Boolean(), nullable=True), schema="ai")
    op.add_column("candidate_profiles", sa.Column("document_score", sa.Numeric(4, 1), nullable=True), schema="ai")
