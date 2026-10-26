"""배치 작업의 고정 입력과 복원 식별자. 제출 문서 본문은 이 상태에 넣지 않는다."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class BatchJob:
    job_id: str
    started_at: float
    deadline: float
    today: date
    model: str
    provider: str
    max_tokens: int
    temperature: float | None
    reasoning_effort: str | None


@dataclass(frozen=True)
class BatchCall:
    state: Literal["reserved", "submitted", "failed", "unknown"]
    custom_id: str
    batch_id: str | None = None
    error: str | None = None


class BatchStore(Protocol):
    async def start_job(
        self,
        job_id: str,
        *,
        timeout_seconds: float,
        model: str,
        provider: str,
        max_tokens: int,
        temperature: float | None,
        reasoning_effort: str | None,
    ) -> BatchJob: ...

    async def reserve_call(self, job_id: str, fingerprint: str, custom_id: str) -> tuple[BatchCall, bool]: ...

    async def release_calls(self, calls: Sequence[tuple[str, str]]) -> None: ...

    async def save_submission(self, calls: Sequence[tuple[str, str]], batch_id: str) -> None: ...

    async def fail_submission(self, calls: Sequence[tuple[str, str]], error: str, *, unknown: bool) -> None: ...

    async def get_result(self, job_id: str) -> dict[str, Any] | None: ...

    async def save_result(self, job_id: str, result: dict[str, Any]) -> None: ...

    async def finish_job(self, job_id: str) -> None: ...

    async def batches(self) -> list[str]: ...

    async def batch_jobs(self, batch_id: str) -> set[str]: ...

    async def remove_batch(self, batch_id: str) -> None: ...


_JOB: ContextVar[BatchJob | None] = ContextVar("batch_job", default=None)
_CALLS: ContextVar[dict[str, int] | None] = ContextVar("batch_calls", default=None)


@contextmanager
def batch_job(job: BatchJob) -> Iterator[None]:
    token = _JOB.set(job)
    calls_token = _CALLS.set({})
    try:
        yield
    finally:
        _CALLS.reset(calls_token)
        _JOB.reset(token)


def current_batch_job() -> BatchJob | None:
    return _JOB.get()


def next_batch_call(fingerprint: str) -> int:
    """같은 요청의 형식 보완 재시도를 구분하고 작업 재개 때 같은 순서를 재현한다."""
    calls = _CALLS.get()
    if calls is None:
        raise RuntimeError("배치 작업 밖에서는 호출 순서를 만들 수 없다")
    occurrence = calls.get(fingerprint, 0) + 1
    calls[fingerprint] = occurrence
    return occurrence
