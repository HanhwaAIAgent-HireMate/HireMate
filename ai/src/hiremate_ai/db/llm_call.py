from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hiremate_ai.db.base import Base


class LlmCallLog(Base):
    """LLM 호출 한 번의 기록 (아키텍처 규칙 3의 AI 호출 로그).

    프롬프트에 지원자 자료가 들어 있으므로 ai 스키마 밖으로 내보내지 않는다.
    """

    __tablename__ = "llm_calls"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10))
    system_prompt: Mapped[str] = mapped_column(Text)
    user_prompt: Mapped[str] = mapped_column(Text)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    latency_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
