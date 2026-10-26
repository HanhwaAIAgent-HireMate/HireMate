import asyncio
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from hiremate_ai.config import settings
from hiremate_ai.contract import Job, JobResult, JobStatus
from hiremate_ai.llm.batch_state import current_batch_job
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.worker import __main__ as entrypoint
from hiremate_ai.worker.batch import ApplicationBatchJobs
from hiremate_ai.worker.batch_store import RedisBatchStore
from hiremate_ai.worker.runner import WorkerOptions


def application_job() -> Job:
    return Job(job_id=uuid4(), type="application/analyze", target=str(uuid4()), payload={})


def lifecycle(redis: Redis, *, timeout_seconds: float = 259200) -> ApplicationBatchJobs:
    return ApplicationBatchJobs(
        RedisBatchStore(redis, "test:batch"),
        timeout_seconds=timeout_seconds,
        model="deepseek/deepseek-v4.1-flash",
        provider="sail-research",
        max_tokens=2048,
        temperature=0,
        reasoning_effort="none",
        retry_delay_seconds=0,
    )


async def test_application_context_has_its_own_budget_and_is_cleared(redis: Redis) -> None:
    job = application_job()
    batch = lifecycle(redis)

    async def analyze(payload: dict[str, object]) -> dict[str, object]:
        context = current_batch_job()
        assert context is not None
        assert context.job_id == str(job.job_id)
        assert context.model == "deepseek/deepseek-v4.1-flash"
        assert context.provider == "sail-research"
        assert context.deadline - context.started_at == 259200
        assert context.deadline - time.time() > 259190
        return {"analyzed": True}

    result = await batch.run(job, analyze)

    assert result.status is JobStatus.DONE
    assert result.result == {"analyzed": True}
    assert current_batch_job() is None
    assert not batch.handles(job.model_copy(update={"type": "assessment/analyze"}))


async def test_completed_result_survives_delivery_retry_without_running_handler(redis: Redis) -> None:
    job = application_job()

    async def analyze(payload: dict[str, object]) -> dict[str, object]:
        return {"score": 80}

    result = await lifecycle(redis).run(job, analyze)

    async def must_not_run(payload: dict[str, object]) -> dict[str, object]:
        pytest.fail("완료된 작업은 모델이나 분석 함수를 다시 실행하면 안 된다")

    replay = await lifecycle(redis).run(job, must_not_run)

    assert replay == result


async def test_cancelled_job_keeps_frozen_context_for_restart(redis: Redis) -> None:
    job = application_job()
    entered = asyncio.Event()
    snapshots: list[tuple[float, float, str]] = []

    async def waiting(payload: dict[str, object]) -> dict[str, object]:
        context = current_batch_job()
        assert context is not None
        snapshots.append((context.started_at, context.deadline, context.today.isoformat()))
        entered.set()
        await asyncio.Event().wait()
        return {}

    task = asyncio.create_task(lifecycle(redis).run(job, waiting))
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    async def resumed(payload: dict[str, object]) -> dict[str, object]:
        context = current_batch_job()
        assert context is not None
        assert (context.started_at, context.deadline, context.today.isoformat()) == snapshots[0]
        return {"resumed": True}

    result = await lifecycle(redis, timeout_seconds=10).run(job, resumed)

    assert result.status is JobStatus.DONE and result.result == {"resumed": True}


async def test_analysis_deadline_is_permanent_and_result_is_saved(redis: Redis) -> None:
    job = application_job()

    async def waiting(payload: dict[str, object]) -> dict[str, object]:
        await asyncio.Event().wait()
        return {}

    result = await lifecycle(redis, timeout_seconds=0.03).run(job, waiting)

    assert result.status is JobStatus.FAILED
    assert result.error is not None and "시간 한도" in result.error
    assert await RedisBatchStore(redis, "test:batch").get_result(str(job.job_id)) is not None


async def test_concurrent_completion_returns_the_first_durable_result(redis: Redis) -> None:
    job = application_job()
    winner = JobResult(
        job_id=job.job_id,
        type=job.type,
        target=job.target,
        status=JobStatus.DONE,
        result={"score": 75},
        error=None,
    )

    async def analyze(payload: dict[str, object]) -> dict[str, object]:
        await RedisBatchStore(redis, "test:batch").save_result(str(job.job_id), winner.model_dump(mode="json"))
        return {"score": 80}

    result = await lifecycle(redis).run(job, analyze)

    assert result == winner


async def test_disabling_new_batches_still_drains_the_existing_application_queue(
    redis: Redis, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = application_job()
    instant_job = application_job()
    await redis.xadd("jobs:application-batch", {"job": job.model_dump_json()})
    await redis.xadd("jobs", {"job": instant_job.model_dump_json()})
    monkeypatch.setattr(settings, "application_batch_enabled", False)
    monkeypatch.setattr(settings, "worker_job_stream", "jobs")
    monkeypatch.setattr(settings, "worker_result_stream", "results")
    monkeypatch.setattr(settings, "worker_group", "workers")
    monkeypatch.setattr(entrypoint, "get_llm", FakeLlm)
    monkeypatch.setattr(entrypoint, "session_factory", async_sessionmaker)
    monkeypatch.setattr(entrypoint, "connect", lambda url, options: Redis.from_url(redis_url, decode_responses=True))

    def options(**kwargs: Any) -> WorkerOptions:
        return WorkerOptions(**kwargs, block_seconds=0.05)

    def handlers(*args: Any, application_llm: object = None, **kwargs: Any) -> dict[str, Any]:
        async def analyze(payload: dict[str, Any]) -> dict[str, Any]:
            assert (current_batch_job() is not None) == (application_llm is not None)
            return {"resumed": application_llm is not None}

        return {job.type: analyze}

    monkeypatch.setattr(entrypoint, "WorkerOptions", options)
    monkeypatch.setattr(entrypoint, "job_handlers", handlers)
    stops: list[Callable[[], None]] = []
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", lambda signum, callback: stops.append(callback))
    running = asyncio.create_task(entrypoint.main())
    found: list[Any] = []
    try:
        deadline = loop.time() + 2
        while loop.time() < deadline:
            found = await redis.xrange("results") or []
            if len(found) == 2:
                break
            await asyncio.sleep(0.02)
    finally:
        for stop in stops:
            stop()
        try:
            await asyncio.wait_for(running, timeout=2)
        finally:
            running.cancel()
            await asyncio.gather(running, return_exceptions=True)

    assert len(found) == 2
    results = [JobResult.model_validate_json(fields["result"]) for _, fields in found]
    assert {result.job_id: result.result for result in results} == {
        job.job_id: {"resumed": True},
        instant_job.job_id: {"resumed": False},
    }
    assert await redis.xlen("jobs:application-batch") == 0
