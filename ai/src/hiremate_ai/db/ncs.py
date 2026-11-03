"""NCS 정보기술 '책임 및 역할' 묶음과 BGE-M3 벡터. scripts/ncs_load.py가 통째로 바꿔 넣는다."""

from pgvector.sqlalchemy import SPARSEVEC, Vector
from sqlalchemy import String, Text
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
