"""지원서 분석 결과 원본 (Application Agent).

판정 전체(자격요건 · 우대사항 평가 조건별 판정, 근거, 보류 이유)를 입력 해시와 함께 남긴다.
같은 입력이면 모델을 다시 부르지 않고 이 결과를 쓴다. 지원자 프로필(db.profile)에는 요약 값과 항목을 따로 넣는다.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hiremate_ai.db.base import Base


class ApplicationReviewRecord(Base):
    """지원서 한 건의 분석 한 번. (지원서, 입력 해시)마다 하나다."""

    __tablename__ = "application_reviews"
    __table_args__ = (
        UniqueConstraint("application_id", "input_hash"),
        Index("ix_application_reviews_scope", "company_id", "recruitment_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # backend의 지원서 · 기업 · 채용 ID. 다른 스키마라 외래 키는 걸지 않는다
    application_id: Mapped[UUID]
    company_id: Mapped[UUID]
    recruitment_id: Mapped[UUID]
    input_hash: Mapped[str] = mapped_column(String(64))  # 공고 · 서류 · 평가 기준 · 분석 버전의 해시
    review_version: Mapped[str] = mapped_column(String(20))
    review: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
