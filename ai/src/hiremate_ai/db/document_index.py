"""정제 문서의 검색 단위와 임베딩."""

from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hiremate_ai.db.base import SCHEMA, Base


class DocumentIndex(Base):
    __tablename__ = "normalized_document_indexes"
    __table_args__ = (Index("ix_normalized_document_indexes_scope", "company_id", "recruitment_id", "application_id"),)

    document_id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID]
    recruitment_id: Mapped[UUID]
    application_id: Mapped[UUID]
    revision: Mapped[int] = mapped_column(Integer)
    blind: Mapped[bool]
    content_hash: Mapped[str] = mapped_column(String(64))
    document_type: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(200))


class DocumentIndexChunk(Base):
    __tablename__ = "normalized_document_chunks"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.normalized_document_indexes.document_id", ondelete="CASCADE"), primary_key=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    block_id: Mapped[str] = mapped_column(String(200))
    pages: Mapped[list[int]] = mapped_column(JSONB)
    text: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))
