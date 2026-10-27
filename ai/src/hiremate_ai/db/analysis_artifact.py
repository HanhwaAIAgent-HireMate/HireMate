"""독립 분석이 저장한 추출 및 면접 산출물. Root 검토 결과는 저장하지 않는다."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hiremate_ai.db.base import Base


class AnalysisArtifactRecord(Base):
    __tablename__ = "analysis_artifacts"
    __table_args__ = (
        UniqueConstraint("company_id", "recruitment_id", "application_id", "kind", "input_hash"),
        Index("ix_analysis_artifacts_scope", "company_id", "recruitment_id", "application_id", "stage_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID]
    recruitment_id: Mapped[UUID]
    application_id: Mapped[UUID]
    stage_id: Mapped[UUID | None]
    kind: Mapped[str] = mapped_column(String(30))
    input_hash: Mapped[str] = mapped_column(String(64))
    recipe_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
