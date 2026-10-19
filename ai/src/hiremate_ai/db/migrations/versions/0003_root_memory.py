"""Root Agent Chat 대화방 (LangGraph 체크포인터)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# langgraph-checkpoint-postgres 3.1.x의 setup()이 적용하는 마이그레이션 0~9와 같은 구조다
CHECKPOINT_MIGRATIONS = 10


def upgrade() -> None:
    migrations = op.create_table(
        "checkpoint_migrations",
        sa.Column("v", sa.Integer(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("v", name=op.f("pk_checkpoint_migrations")),
        schema="ai",
    )
    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), server_default="", nullable=False),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("parent_checkpoint_id", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("checkpoint", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id", name=op.f("pk_checkpoints")),
        schema="ai",
    )
    op.create_index("checkpoints_thread_id_idx", "checkpoints", ["thread_id"], unique=False, schema="ai")
    op.create_table(
        "checkpoint_blobs",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), server_default="", nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "channel", "version", name=op.f("pk_checkpoint_blobs")),
        schema="ai",
    )
    op.create_index("checkpoint_blobs_thread_id_idx", "checkpoint_blobs", ["thread_id"], unique=False, schema="ai")
    op.create_table(
        "checkpoint_writes",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), server_default="", nullable=False),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("idx", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        sa.Column("task_path", sa.Text(), server_default="", nullable=False),
        sa.PrimaryKeyConstraint(
            "thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx", name=op.f("pk_checkpoint_writes")
        ),
        schema="ai",
    )
    op.create_index("checkpoint_writes_thread_id_idx", "checkpoint_writes", ["thread_id"], unique=False, schema="ai")
    op.bulk_insert(migrations, [{"v": version} for version in range(CHECKPOINT_MIGRATIONS)])


def downgrade() -> None:
    op.drop_index("checkpoint_writes_thread_id_idx", table_name="checkpoint_writes", schema="ai")
    op.drop_table("checkpoint_writes", schema="ai")
    op.drop_index("checkpoint_blobs_thread_id_idx", table_name="checkpoint_blobs", schema="ai")
    op.drop_table("checkpoint_blobs", schema="ai")
    op.drop_index("checkpoints_thread_id_idx", table_name="checkpoints", schema="ai")
    op.drop_table("checkpoints", schema="ai")
    op.drop_table("checkpoint_migrations", schema="ai")
