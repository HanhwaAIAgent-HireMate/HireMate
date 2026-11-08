"""Remove the old document index while preserving migration history.

Revision ID: b2459a16e218
Revises: 918c3c2bd417
"""

from collections.abc import Sequence
from importlib import import_module

from alembic import op

revision: str = "b2459a16e218"
down_revision: str | Sequence[str] | None = "918c3c2bd417"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("document_index_chunks", schema="ai")
    op.drop_index("ix_document_indexes_scope", table_name="document_indexes", schema="ai")
    op.drop_table("document_indexes", schema="ai")


def downgrade() -> None:
    previous = import_module("hiremate_ai.db.migrations.versions.918c3c2bd417_normalized_document_index")
    previous.upgrade()
