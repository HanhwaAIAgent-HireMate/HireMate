"""NCS 정보기술 '책임 및 역할' 묶음과 BGE-M3 벡터. scripts/ncs_load.py가 통째로 바꿔 넣는다."""

from pgvector.sqlalchemy import SPARSEVEC, Vector
from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from hiremate_ai.db.base import Base
from hiremate_ai.ncs_search.types import DENSE_DIM, SPARSE_DIM


class NcsTaskRow(Base):
    __tablename__ = "ncs_tasks"

    chunk_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    duty_code: Mapped[str] = mapped_column(String(8))
    duty_name: Mapped[str] = mapped_column(String(100))
    unit_code: Mapped[str] = mapped_column(String(20), index=True)
    unit_name: Mapped[str] = mapped_column(String(200))
    task_name: Mapped[str] = mapped_column(String(200))
    sentences: Mapped[list[str]] = mapped_column(ARRAY(Text))
    dense: Mapped[list[float]] = mapped_column(Vector(DENSE_DIM))
    sparse: Mapped[object] = mapped_column(SPARSEVEC(SPARSE_DIM))


class NcsReferenceRow(Base):
    """NCS 전체 직무기술서에서 만든 기존 벡터와 출처."""

    __tablename__ = "ncs_reference_chunks"
    __table_args__ = (
        Index(
            "ix_ncs_reference_chunks_dense",
            "dense",
            postgresql_using="hnsw",
            postgresql_ops={"dense": "vector_cosine_ops"},
        ),
        Index(
            "ix_ncs_reference_chunks_sparse",
            "sparse",
            postgresql_using="hnsw",
            postgresql_ops={"sparse": "sparsevec_ip_ops"},
        ),
    )

    chunk_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    duty_code: Mapped[str] = mapped_column(String(8))
    duty_name: Mapped[str] = mapped_column(String(100))
    unit_code: Mapped[str] = mapped_column(String(20), index=True)
    unit_name: Mapped[str] = mapped_column(String(200))
    kind_code: Mapped[str] = mapped_column(String(60))
    kind_name: Mapped[str] = mapped_column(String(100))
    task_name: Mapped[str] = mapped_column(String(200))
    sentences: Mapped[list[str]] = mapped_column(ARRAY(Text))
    dense: Mapped[list[float]] = mapped_column(Vector(DENSE_DIM))
    sparse: Mapped[object] = mapped_column(SPARSEVEC(SPARSE_DIM))
