"""Active normalized-document vectors. Replacement is atomic per document."""

from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hiremate_ai.db.base import SCHEMA, Base


class DocumentIndex(Base):
    __tablename__ = "document_indexes"
    __table_args__ = (Index("ix_document_indexes_scope", "company_id", "recruitment_id", "application_id"),)

    document_id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID]
    recruitment_id: Mapped[UUID]
    application_id: Mapped[UUID]
    revision: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    document_type: Mapped[str] = mapped_column(String(20))
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(String(200))


class DocumentIndexChunk(Base):
    __tablename__ = "document_index_chunks"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.document_indexes.document_id", ondelete="CASCADE"), primary_key=True
    )
    ordinal: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int]
    model: Mapped[str] = mapped_column(String(200))
    block_ids: Mapped[list[str]] = mapped_column(JSONB)
    source_ids: Mapped[list[str]] = mapped_column(JSONB)
    section_path: Mapped[list[str]] = mapped_column(JSONB)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))
