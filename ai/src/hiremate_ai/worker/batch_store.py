"""Redis에 배치 복원 식별자와 최종 결과를 보관한다. 새 상태에 문서를 복사하지 않는다."""

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from time import time
from typing import Any

from redis.asyncio import Redis

from hiremate_ai.llm.batch_state import BatchCall, BatchJob

RETENTION_SECONDS = 30 * 24 * 60 * 60

_RELEASE_CALLS = """
for index = 1, #ARGV, 2 do
    local raw = redis.call('HGET', ARGV[index], ARGV[index + 1])
    if raw and cjson.decode(raw).state == 'reserved' then
        redis.call('HDEL', ARGV[index], ARGV[index + 1])
    end
end
return 1
"""

_SUBMISSION = """
local batch_id = ARGV[1]
for index = 3, #ARGV, 4 do
    local raw = redis.call('HGET', ARGV[index + 1], ARGV[index + 2])
    if not raw then return redis.error_reply('batch call was not reserved') end
    local call = cjson.decode(raw)
    if call.batch_id ~= cjson.null and call.batch_id ~= batch_id then
        return redis.error_reply('batch reference conflict')
    end
end
for index = 3, #ARGV, 4 do
    local job_key = ARGV[index]
    local calls_key = ARGV[index + 1]
    local fingerprint = ARGV[index + 2]
    local job_id = ARGV[index + 3]
    local call = cjson.decode(redis.call('HGET', calls_key, fingerprint))
    call.state = 'submitted'
    call.batch_id = batch_id
    call.error = cjson.null
    redis.call('HSET', calls_key, fingerprint, cjson.encode(call))
    if redis.call('HEXISTS', job_key, 'finished') == 0 then
        redis.call('SADD', KEYS[2], job_id)
    end
end
redis.call('SADD', KEYS[1], batch_id)
return 1
"""

_FAIL_SUBMISSION = """
for index = 3, #ARGV, 2 do
    local raw = redis.call('HGET', ARGV[index], ARGV[index + 1])
    if raw then
        local call = cjson.decode(raw)
        if call.state ~= 'submitted' then
            call.state = ARGV[1]
            call.error = ARGV[2]
            redis.call('HSET', ARGV[index], ARGV[index + 1], cjson.encode(call))
        end
    end
end
return 1
"""

_FINISH = """
local calls = redis.call('HVALS', KEYS[2])
for _, raw in ipairs(calls) do
    local call = cjson.decode(raw)
    if call.batch_id ~= cjson.null then
        redis.call('SREM', ARGV[1] .. ':batch:' .. call.batch_id .. ':jobs', ARGV[2])
    end
end
if redis.call('HSETNX', KEYS[1], 'finished', ARGV[3]) == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[4])
    redis.call('EXPIRE', KEYS[2], ARGV[4])
end
return 1
"""

_REMOVE_BATCH = """
if redis.call('SCARD', KEYS[2]) == 0 then
    redis.call('SREM', KEYS[1], ARGV[1])
    redis.call('DEL', KEYS[2])
end
return 1
"""


class RedisBatchStore:
    def __init__(self, redis: Redis, prefix: str) -> None:
        self._redis = redis
        self._prefix = prefix

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
    ) -> BatchJob:
        started_at = time()
        snapshot = BatchJob(
            job_id=job_id,
            started_at=started_at,
            deadline=started_at + timeout_seconds,
            today=date.today(),
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )
        payload = {**asdict(snapshot), "today": snapshot.today.isoformat()}
        key = self._job(job_id)
        await self._redis.hsetnx(key, "snapshot", json.dumps(payload))
        raw = await self._redis.hget(key, "snapshot")
        if raw is None:
            raise RuntimeError("배치 작업 상태를 읽지 못했다")
        saved = json.loads(raw)
        return BatchJob(**{**saved, "today": date.fromisoformat(saved["today"])})

    async def reserve_call(self, job_id: str, fingerprint: str, custom_id: str) -> tuple[BatchCall, bool]:
        key = self._calls(job_id)
        owned = await self._redis.hsetnx(key, fingerprint, json.dumps(asdict(BatchCall("reserved", custom_id))))
        raw = await self._redis.hget(key, fingerprint)
        if raw is None:
            raise RuntimeError("배치 호출 상태를 읽지 못했다")
        return BatchCall(**json.loads(raw)), bool(owned)

    async def release_calls(self, calls: Sequence[tuple[str, str]]) -> None:
        if not calls:
            return
        arguments: list[str] = []
        for job_id, fingerprint in calls:
            arguments.extend((self._calls(job_id), fingerprint))
        await self._redis.eval(_RELEASE_CALLS, 0, *arguments)

    async def save_submission(self, calls: Sequence[tuple[str, str]], batch_id: str) -> None:
        if not calls:
            return
        arguments: list[str] = [batch_id, self._prefix]
        for job_id, fingerprint in calls:
            arguments.extend((self._job(job_id), self._calls(job_id), fingerprint, job_id))
        await self._redis.eval(_SUBMISSION, 2, self._batches, self._batch_jobs(batch_id), *arguments)

    async def fail_submission(self, calls: Sequence[tuple[str, str]], error: str, *, unknown: bool) -> None:
        if not calls:
            return
        arguments = ["unknown" if unknown else "failed", error]
        for job_id, fingerprint in calls:
            arguments.extend((self._calls(job_id), fingerprint))
        await self._redis.eval(_FAIL_SUBMISSION, 0, *arguments)

    async def get_result(self, job_id: str) -> dict[str, Any] | None:
        raw = await self._redis.hget(self._job(job_id), "result")
        return json.loads(raw) if raw is not None else None

    async def save_result(self, job_id: str, result: dict[str, Any]) -> None:
        await self._redis.hsetnx(self._job(job_id), "result", json.dumps(result))

    async def finish_job(self, job_id: str) -> None:
        await self._redis.eval(
            _FINISH,
            2,
            self._job(job_id),
            self._calls(job_id),
            self._prefix,
            job_id,
            str(time()),
            str(RETENTION_SECONDS),
        )

    async def batches(self) -> list[str]:
        return sorted(_text(value) for value in await self._redis.smembers(self._batches))

    async def batch_jobs(self, batch_id: str) -> set[str]:
        return {_text(value) for value in await self._redis.smembers(self._batch_jobs(batch_id))}

    async def remove_batch(self, batch_id: str) -> None:
        await self._redis.eval(_REMOVE_BATCH, 2, self._batches, self._batch_jobs(batch_id), batch_id)

    @property
    def _batches(self) -> str:
        return f"{self._prefix}:batches"

    def _job(self, job_id: str) -> str:
        return f"{self._prefix}:job:{job_id}"

    def _calls(self, job_id: str) -> str:
        return f"{self._prefix}:job:{job_id}:calls"

    def _batch_jobs(self, batch_id: str) -> str:
        return f"{self._prefix}:batch:{batch_id}:jobs"


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value
