import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from hiremate_ai.contract import Job, JobResult, JobStatus
from hiremate_ai.worker.batch import ApplicationBatchJobs
from hiremate_ai.worker.batch_store import RedisBatchStore
from hiremate_ai.worker.handlers import INDEX_JOB, Handler, PermanentError
from hiremate_ai.worker.runner import Worker, WorkerOptions, connect

OPTIONS = WorkerOptions(
    job_stream="jobs",
    result_stream="results",
    group="ai-worker",
    consumer="worker-1",
    attempts=2,
    claim_idle_seconds=0.4,
    retry_delay_seconds=0,
    block_seconds=0.05,
)


def make_job(job_type: str = "echo/run", value: str = "지원서") -> Job:
    return Job(job_id=uuid4(), type=job_type, target=str(uuid4()), payload={"value": value})


async def put(redis: Redis, job: Job) -> str:
    return str(await redis.xadd(OPTIONS.job_stream, {"job": job.model_dump_json()}))


async def results(redis: Redis) -> list[JobResult]:
    entries: Any = await redis.xrange(OPTIONS.result_stream)
    return [JobResult.model_validate_json(fields["result"]) for _, fields in entries]


async def run_until(redis: Redis, *workers: Worker, count: int = 1, seconds: float = 10) -> list[JobResult]:
    """결과가 count개 쌓일 때까지 워커를 돌리고 멈춘다."""
    stop = asyncio.Event()
    tasks = [asyncio.create_task(worker.run(stop)) for worker in workers]
    try:
        async with asyncio.timeout(seconds):
            while True:
                found = await results(redis)
                if len(found) >= count:
                    break
                await asyncio.sleep(0.05)
    finally:
        stop.set()
        await asyncio.gather(*tasks)
    return found


def counting(handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]) -> tuple[Handler, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    async def wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return await handler(payload)

    return wrapped, calls


async def echo(payload: dict[str, Any]) -> dict[str, Any]:
    return {"echo": payload["value"]}


async def deliver_to(redis: Redis, consumer: str) -> None:
    """다른 워커가 작업을 가져간 채 멈춘 상태를 만든다."""
    await redis.xgroup_create(OPTIONS.job_stream, OPTIONS.group, id="0", mkstream=True)
    await redis.xreadgroup(OPTIONS.group, consumer, {OPTIONS.job_stream: ">"}, count=1)


async def test_job_result_goes_to_result_stream_and_job_is_removed(redis: Redis) -> None:
    job = make_job()
    await put(redis, job)

    [result] = await run_until(redis, Worker(redis, {"echo/run": echo}, OPTIONS))

    assert result == JobResult(
        job_id=job.job_id,
        type="echo/run",
        target=job.target,
        status=JobStatus.DONE,
        result={"echo": "지원서"},
        error=None,
    )
    assert await redis.xlen(OPTIONS.job_stream) == 0
    assert (await redis.xpending(OPTIONS.job_stream, OPTIONS.group))["pending"] == 0


async def test_failing_handler_is_retried_then_reported_failed(redis: Redis) -> None:
    async def broken(payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("모델 서버가 응답하지 않는다")

    handler, calls = counting(broken)
    await put(redis, make_job())

    [result] = await run_until(redis, Worker(redis, {"echo/run": handler}, OPTIONS))

    assert len(calls) == 2
    assert result.status is JobStatus.FAILED and result.result is None
    assert result.error == "RuntimeError: 모델 서버가 응답하지 않는다"


async def test_permanent_error_is_not_retried(redis: Redis) -> None:
    async def rejected(payload: dict[str, Any]) -> dict[str, Any]:
        raise PermanentError("평가 기준과 지원서의 채용이 다르다")

    handler, calls = counting(rejected)
    await put(redis, make_job())

    [result] = await run_until(redis, Worker(redis, {"echo/run": handler}, OPTIONS))

    assert len(calls) == 1
    assert result.status is JobStatus.FAILED and result.error == "평가 기준과 지원서의 채용이 다르다"


async def test_unknown_job_type_fails(redis: Redis) -> None:
    await put(redis, make_job("unknown/run"))

    [result] = await run_until(redis, Worker(redis, {"echo/run": echo}, OPTIONS))

    assert result.status is JobStatus.FAILED and result.error == "모르는 작업 유형: unknown/run"


async def test_unreadable_job_is_dropped_without_result(redis: Redis) -> None:
    await redis.xadd(OPTIONS.job_stream, {"job": "{not json"})
    job = make_job()
    await put(redis, job)

    [result] = await run_until(redis, Worker(redis, {"echo/run": echo}, OPTIONS))

    assert result.job_id == job.job_id
    assert await redis.xlen(OPTIONS.job_stream) == 0


async def test_job_left_by_stopped_worker_is_taken_over(redis: Redis) -> None:
    await put(redis, make_job())
    await deliver_to(redis, "stopped-worker")

    [result] = await run_until(redis, Worker(redis, {"echo/run": echo}, OPTIONS))

    assert result.status is JobStatus.DONE
    assert (await redis.xpending(OPTIONS.job_stream, OPTIONS.group))["pending"] == 0


async def test_job_that_stopped_workers_too_often_fails_without_running(redis: Redis) -> None:
    handler, calls = counting(echo)
    message_id = await put(redis, make_job())
    await deliver_to(redis, "stopped-worker")
    await redis.xclaim(OPTIONS.job_stream, OPTIONS.group, "another-stopped-worker", 0, [message_id])

    [result] = await run_until(redis, Worker(redis, {"echo/run": handler}, OPTIONS))

    assert calls == []
    assert result.status is JobStatus.FAILED


async def test_running_job_is_not_taken_by_another_worker(redis: Redis) -> None:
    async def slow(payload: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(1.2)
        return await echo(payload)

    handler, calls = counting(slow)
    await put(redis, make_job())
    first = Worker(redis, {"echo/run": handler}, OPTIONS)
    second = Worker(redis, {"echo/run": handler}, replace(OPTIONS, consumer="worker-2"))

    found = await run_until(redis, first, second)

    assert len(calls) == 1
    assert len(found) == 1 and len(await results(redis)) == 1


async def test_waiting_for_new_jobs_does_not_hit_the_read_timeout(redis: Redis, redis_url: str) -> None:
    """빈 대기열을 5초 기다려도 읽기 시간 한도에 걸리지 않는다. redis-py 비동기 클라이언트의 기본 한도가 5초다."""
    options = replace(OPTIONS, block_seconds=5)
    client = connect(redis_url, options)
    await client.xgroup_create(options.job_stream, options.group, id="0", mkstream=True)
    try:
        found = await client.xreadgroup(
            options.group, options.consumer, {options.job_stream: ">"}, count=1, block=int(options.block_seconds * 1000)
        )
    finally:
        await client.aclose()

    assert not found


def batch_jobs(redis: Redis) -> ApplicationBatchJobs:
    return ApplicationBatchJobs(
        RedisBatchStore(redis, "runner:batch"),
        timeout_seconds=259200,
        model="deepseek/deepseek-v4.1-flash",
        provider="sail-research",
        max_tokens=2048,
        temperature=0,
        reasoning_effort="none",
        retry_delay_seconds=0,
    )


async def test_batch_job_is_resumed_after_multiple_worker_restarts(redis: Redis) -> None:
    handler, calls = counting(echo)
    job = make_job("application/analyze")
    message_id = await put(redis, job)
    await deliver_to(redis, "stopped-worker")
    await redis.xclaim(OPTIONS.job_stream, OPTIONS.group, "another-stopped-worker", 0, [message_id])

    [result] = await run_until(redis, Worker(redis, {job.type: handler}, OPTIONS, batch=batch_jobs(redis)))

    assert result.status is JobStatus.DONE
    assert len(calls) == 1


async def test_stop_leaves_waiting_batch_job_for_the_next_worker(redis: Redis) -> None:
    entered = asyncio.Event()

    async def waiting(payload: dict[str, Any]) -> dict[str, Any]:
        entered.set()
        await asyncio.Event().wait()
        return {}

    job = make_job("application/analyze")
    await put(redis, job)
    stop = asyncio.Event()
    worker = Worker(redis, {job.type: waiting}, OPTIONS, batch=batch_jobs(redis))
    task = asyncio.create_task(worker.run(stop))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        stop.set()
        await asyncio.wait_for(task, timeout=2)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert await results(redis) == []
    assert (await redis.xpending(OPTIONS.job_stream, OPTIONS.group))["pending"] == 1
    [result] = await run_until(
        redis,
        Worker(redis, {job.type: echo}, replace(OPTIONS, consumer="resumed"), batch=batch_jobs(redis)),
    )
    assert result.status is JobStatus.DONE


async def test_batch_result_delivery_failure_reuses_the_saved_result(
    redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, calls = counting(echo)
    job = make_job("application/analyze")
    await put(redis, job)
    original = redis.xadd
    failed = False

    async def xadd(name: str, fields: dict[Any, Any], **kwargs: Any) -> Any:
        nonlocal failed
        if name == OPTIONS.result_stream and not failed:
            failed = True
            raise RedisError("결과 전달이 잠시 끊겼다")
        return await original(name, fields, **kwargs)

    monkeypatch.setattr(redis, "xadd", xadd)

    [result] = await run_until(redis, Worker(redis, {job.type: handler}, OPTIONS, batch=batch_jobs(redis)))

    assert result.status is JobStatus.DONE
    assert failed and len(calls) == 1
    assert await redis.xlen(OPTIONS.job_stream) == 0


async def test_waiting_applications_do_not_block_other_job_types(redis: Redis) -> None:
    entered = asyncio.Event()

    async def waiting(payload: dict[str, Any]) -> dict[str, Any]:
        entered.set()
        await asyncio.Event().wait()
        return {}

    application = make_job("application/analyze")
    ordinary = make_job()
    await put(redis, application)
    batch_options = replace(OPTIONS, job_stream="applications", group="batch-workers", consumer="batch-worker")
    router = Worker(redis, {"echo/run": echo}, OPTIONS, forward={"application/analyze": batch_options.job_stream})
    batch_worker = Worker(redis, {application.type: waiting}, batch_options, batch=batch_jobs(redis))

    async def submit_ordinary() -> None:
        await entered.wait()
        await put(redis, ordinary)

    producer = asyncio.create_task(submit_ordinary())
    try:
        [result] = await run_until(redis, router, batch_worker)
    finally:
        producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)

    assert result.job_id == ordinary.job_id
    assert result.status is JobStatus.DONE
    assert (await redis.xpending(batch_options.job_stream, batch_options.group))["pending"] == 1


async def test_forwarded_application_returns_the_existing_backend_contract(redis: Redis) -> None:
    job = make_job("application/analyze")
    await put(redis, job)
    batch_options = replace(OPTIONS, job_stream="applications", group="batch-workers", consumer="batch-worker")

    [result] = await run_until(
        redis,
        Worker(redis, {}, OPTIONS, forward={"application/analyze": batch_options.job_stream}),
        Worker(redis, {job.type: echo}, batch_options, batch=batch_jobs(redis)),
    )

    assert result.job_id == job.job_id and result.target == job.target
    assert result.type == job.type and result.result == {"echo": "지원서"}
    assert await redis.xlen(OPTIONS.job_stream) == 0
    assert await redis.xlen(batch_options.job_stream) == 0


async def test_index_jobs_run_one_at_a_time_while_other_jobs_keep_going(redis: Redis) -> None:
    running = 0
    peak = 0

    async def index(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.1)
        running -= 1
        return {}

    indexes = [make_job(INDEX_JOB) for _ in range(3)]
    ordinary = make_job()
    for job in [*indexes, ordinary]:
        await put(redis, job)
    index_options = replace(OPTIONS, job_stream="indexes", group="index-workers", consumer="index-worker")
    handlers: dict[str, Handler] = {INDEX_JOB: index, "echo/run": echo}
    router = Worker(redis, handlers, replace(OPTIONS, concurrency=8), forward={INDEX_JOB: index_options.job_stream})

    found = await run_until(redis, router, Worker(redis, handlers, index_options), count=4)

    assert {result.job_id for result in found} == {job.job_id for job in [*indexes, ordinary]}
    assert all(result.status is JobStatus.DONE for result in found)
    assert found[0].job_id == ordinary.job_id
    assert peak == 1
    assert await redis.xlen(OPTIONS.job_stream) == 0
    assert await redis.xlen(index_options.job_stream) == 0
