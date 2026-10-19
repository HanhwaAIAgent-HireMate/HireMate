"""Root Agent의 Chat 대화방 저장소 (LangGraph 체크포인터, 아키텍처 규칙 3의 대화방). 전형이 끝나면 지운다.

테이블 구조는 langgraph-checkpoint-postgres 3.1.x가 만드는 것과 같다. 라이브러리의 setup()을 쓰지 않고
Alembic으로 만든다. 대화방 상태에는 지원자 문서 본문을 넣지 않는다.
"""

from sqlalchemy import Column, Index, Integer, LargeBinary, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from hiremate_ai.db.base import Base

checkpoint_migrations = Table(
    "checkpoint_migrations",
    Base.metadata,
    Column("v", Integer, primary_key=True, autoincrement=False),
)

checkpoints = Table(
    "checkpoints",
    Base.metadata,
    Column("thread_id", Text, primary_key=True),
    Column("checkpoint_ns", Text, primary_key=True, server_default=""),
    Column("checkpoint_id", Text, primary_key=True),
    Column("parent_checkpoint_id", Text),
    Column("type", Text),
    Column("checkpoint", JSONB, nullable=False),
    Column("metadata", JSONB, nullable=False, server_default=text("'{}'")),
    Index("checkpoints_thread_id_idx", "thread_id"),
)

checkpoint_blobs = Table(
    "checkpoint_blobs",
    Base.metadata,
    Column("thread_id", Text, primary_key=True),
    Column("checkpoint_ns", Text, primary_key=True, server_default=""),
    Column("channel", Text, primary_key=True),
    Column("version", Text, primary_key=True),
    Column("type", Text, nullable=False),
    Column("blob", LargeBinary),
    Index("checkpoint_blobs_thread_id_idx", "thread_id"),
)

checkpoint_writes = Table(
    "checkpoint_writes",
    Base.metadata,
    Column("thread_id", Text, primary_key=True),
    Column("checkpoint_ns", Text, primary_key=True, server_default=""),
    Column("checkpoint_id", Text, primary_key=True),
    Column("task_id", Text, primary_key=True),
    Column("idx", Integer, primary_key=True, autoincrement=False),
    Column("channel", Text, nullable=False),
    Column("type", Text),
    Column("blob", LargeBinary, nullable=False),
    Column("task_path", Text, nullable=False, server_default=""),
    Index("checkpoint_writes_thread_id_idx", "thread_id"),
)
