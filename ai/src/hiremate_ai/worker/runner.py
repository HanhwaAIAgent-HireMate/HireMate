"""AI 워커 실행부. Redis 작업 스트림에서 작업을 꺼내 처리 함수를 부르고, 결과를 결과 스트림에 넣는다.

- 소비자 그룹으로 읽어 두 워커가 같은 작업을 동시에 맡지 않는다. 결과를 넣은 작업은 확인(XACK)하고 지운다.
- 처리 중인 작업은 주기적으로 다시 차지해(XCLAIM JUSTID) 살아 있음을 알린다. 소식이 끊긴 작업은 다른 워커가 가져가고,
  여러 번 맡겨도 끝나지 않은 작업은 FAILED로 끝낸다.
- 처리 함수가 실패하면 정해진 횟수만큼 다시 하고, 그래도 안 되면 FAILED 결과를 보낸다. 결과는 backend가 기록한다.
- 같은 입력의 분석은 Agent가 저장해 둔 결과를 다시 쓰므로, 같은 작업이 두 번 와도 모델을 다시 부르지 않는다.
"""

import asyncio
import contextlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError
from redis.typing import StreamIdT

from hiremate_ai.contract import Job, JobResult, JobStatus
from hiremate_ai.worker.handlers import Handler, PermanentError

log = logging.getLogger(__name__)

# 스트림 항목의 필드 이름. 값은 contract/Job.json, contract/JobResult.json 형식의 JSON이다
JOB_FIELD = "job"
RESULT_FIELD = "result"

Entry = tuple[str, dict[str, str]]


@dataclass(frozen=True)
class WorkerOptions:
    job_stream: str
    result_stream: str
    group: str
    consumer: str
    concurrency: int = 1
    attempts: int = 2
    claim_idle_seconds: float = 120
    retry_delay_seconds: float = 5
    block_seconds: float = 5


class Worker:
    """작업 스트림의 소비자 하나. run으로 돌리고 stop을 켜면 처리 중인 작업을 마치고 멈춘다."""

    def __init__(self, redis: Redis, handlers: Mapping[str, Handler], options: WorkerOptions) -> None:
        self._redis = redis
        self._handlers = handlers
        self._options = options
        self._slots = asyncio.Semaphore(options.concurrency)
        self._running: dict[str, asyncio.Task[None]] = {}

    async def run(self, stop: asyncio.Event) -> None:
        await self._ensure_group()
        heartbeat = asyncio.create_task(self._heartbeat())
        try:
            while not stop.is_set():
                await self._slots.acquire()
                entry = None
                try:
                    if not stop.is_set():
                        entry = await self._next()
                except RedisError:
                    log.warning("작업 대기열을 읽지 못했다. 잠시 뒤 다시 읽는다", exc_info=True)
                    await asyncio.sleep(self._options.block_seconds)
                if entry is None:
                    self._slots.release()
                    continue
                message_id, fields = entry
                self._running[message_id] = asyncio.create_task(self._process(message_id, fields))
        finally:
            await asyncio.gather(*self._running.values(), return_exceptions=True)
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

    async def _ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(self._options.job_stream, self._options.group, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def _next(self) -> Entry | None:
        """소식이 끊긴 작업이 있으면 먼저 가져오고, 없으면 새 작업을 기다린다."""
        stale = await self._claim_stale()
        if stale is not None:
            return stale
        response: Any = await self._redis.xreadgroup(
            self._options.group,
            self._options.consumer,
            {self._options.job_stream: ">"},
            count=1,
            block=int(self._options.block_seconds * 1000),
        )
        streams = response.items() if isinstance(response, dict) else response or []
        for _stream, entries in streams:
            for message_id, fields in entries:
                return message_id, fields
        return None

    async def _claim_stale(self) -> Entry | None:
        idle = int(self._options.claim_idle_seconds * 1000)
        pending: Any = await self._redis.xpending_range(
            self._options.job_stream, self._options.group, "-", "+", count=1, idle=idle
        )
        for entry in pending:
            claimed: Any = await self._redis.xclaim(
                self._options.job_stream, self._options.group, self._options.consumer, idle, [entry["message_id"]]
            )
            for message_id, fields in claimed:
                if entry["times_delivered"] >= self._options.attempts:
                    log.error("여러 워커가 맡았지만 끝나지 않은 작업을 실패로 끝낸다: %s", message_id)
                    await self._finish(message_id, _failed(fields, "작업을 맡은 워커가 끝내지 못하고 여러 번 멈췄다"))
                    return None
                log.warning("소식이 끊긴 작업을 가져온다: %s", message_id)
                return message_id, fields
        return None

    async def _heartbeat(self) -> None:
        """처리 중인 작업을 다시 차지해 유휴 시간을 0으로 돌린다. JUSTID라 전달 횟수는 늘지 않는다."""
        while True:
            await asyncio.sleep(self._options.claim_idle_seconds / 4)
            running: list[StreamIdT] = [*self._running]
            if not running:
                continue
            try:
                await self._redis.xclaim(
                    self._options.job_stream,
                    self._options.group,
                    self._options.consumer,
                    0,
                    running,
                    justid=True,
                )
            except RedisError:
                log.warning("처리 중인 작업을 알리지 못했다", exc_info=True)

    async def _process(self, message_id: str, fields: dict[str, str]) -> None:
        try:
            await self._finish(message_id, await self._run(fields))
        except Exception:
            # 결과를 넣지 못했다. 확인하지 않고 두면 소식이 끊긴 작업으로 다시 처리된다
            log.exception("작업을 마치지 못했다: %s", message_id)
        finally:
            self._running.pop(message_id, None)
            self._slots.release()

    async def _run(self, fields: dict[str, str]) -> JobResult | None:
        """처리 함수를 부른 결과. 작업을 읽을 수 없으면 None이다."""
        job = _job(fields)
        if job is None:
            return None
        handler = self._handlers.get(job.type)
        if handler is None:
            return _result(job, JobStatus.FAILED, error=f"모르는 작업 유형: {job.type}")
        attempt = 1
        while True:
            try:
                return _result(job, JobStatus.DONE, result=await handler(dict(job.payload)))
            except (PermanentError, ValidationError) as error:
                return _result(job, JobStatus.FAILED, error=str(error))
            except Exception as error:
                log.warning("작업 %s (%s) %d번째 시도 실패", job.type, job.target, attempt, exc_info=True)
                if attempt >= self._options.attempts:
                    return _result(job, JobStatus.FAILED, error=f"{type(error).__name__}: {error}")
            attempt += 1
            await asyncio.sleep(self._options.retry_delay_seconds)

    async def _finish(self, message_id: str, result: JobResult | None) -> None:
        """결과를 결과 스트림에 넣고 작업을 지운다. 읽을 수 없는 작업은 결과 없이 지운다."""
        if result is None:
            log.error("읽을 수 없는 작업을 버린다: %s", message_id)
        else:
            await self._redis.xadd(self._options.result_stream, {RESULT_FIELD: result.model_dump_json()})
        await self._redis.xack(self._options.job_stream, self._options.group, message_id)
        await self._redis.xdel(self._options.job_stream, message_id)


def _job(fields: dict[str, str]) -> Job | None:
    try:
        return Job.model_validate_json(fields[JOB_FIELD])
    except (KeyError, ValidationError):
        return None


def _failed(fields: dict[str, str], error: str) -> JobResult | None:
    job = _job(fields)
    return None if job is None else _result(job, JobStatus.FAILED, error=error)


def _result(
    job: Job, status: JobStatus, *, result: dict[str, Any] | None = None, error: str | None = None
) -> JobResult:
    return JobResult(job_id=job.job_id, type=job.type, target=job.target, status=status, result=result, error=error)
