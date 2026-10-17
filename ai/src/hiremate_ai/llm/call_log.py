import logging
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.db.llm_call import LlmCallLog

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CallRecord:
    """LLM 호출 한 번의 결과."""

    agent: str
    model: str
    status: Literal["OK", "ERROR"]
    system: str
    user: str
    output: dict[str, Any] | None
    error: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


class CallLog(Protocol):
    async def record(self, record: CallRecord) -> None: ...


class DbCallLog:
    """호출 기록을 ai.llm_calls에 저장한다. 저장에 실패해도 Agent 호출은 실패시키지 않는다."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, record: CallRecord) -> None:
        try:
            async with self._sessions() as session:
                session.add(
                    LlmCallLog(
                        agent=record.agent,
                        model=record.model,
                        status=record.status,
                        system_prompt=record.system,
                        user_prompt=record.user,
                        output=record.output,
                        error=record.error,
                        input_tokens=record.input_tokens,
                        output_tokens=record.output_tokens,
                        latency_ms=record.latency_ms,
                    )
                )
                await session.commit()
        except Exception:
            log.warning("LLM 호출 로그를 저장하지 못했다 (%s)", record.agent, exc_info=True)
