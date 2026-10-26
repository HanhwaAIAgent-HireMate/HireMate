import asyncio
from datetime import date
from typing import Any

import pytest
from redis.asyncio import Redis

from hiremate_ai.llm import batch_state
from hiremate_ai.llm.batch_state import BatchCall, BatchJob, batch_job, current_batch_job
from hiremate_ai.worker.batch_store import RedisBatchStore

PREFIX = "test:batch"
OPTIONS: dict[str, Any] = {
    "timeout_seconds": 3600,
    "model": "deepseek/deepseek-v4.1-flash",
    "provider": "sail-research",
    "max_tokens": 2048,
    "temperature": 0.0,
    "reasoning_effort": "none",
}


async def test_start_job_freezes_time_date_and_generation_settings(redis: Redis) -> None:
    store = RedisBatchStore(redis, PREFIX)
    first = await store.start_job("job-1", **OPTIONS)

    resumed = await RedisBatchStore(redis, PREFIX).start_job(
        "job-1", **{**OPTIONS, "timeout_seconds": 999, "model": "changed", "max_tokens": 8192}
    )

    assert resumed == first
    assert first.job_id == "job-1"
    assert first.deadline - first.started_at == 3600
    assert first.today == date.today()
    assert first.model == "deepseek/deepseek-v4.1-flash"
    assert first.provider == "sail-research"
    assert first.max_tokens == 2048
    assert first.temperature == 0.0
    assert first.reasoning_effort == "none"


async def test_parallel_start_returns_one_frozen_snapshot(redis: Redis) -> None:
    store = RedisBatchStore(redis, PREFIX)

    jobs = await asyncio.gather(
        *(store.start_job("job-1", **{**OPTIONS, "model": f"model-{index}"}) for index in range(12))
    )

    assert all(job == jobs[0] for job in jobs)


async def test_batch_context_is_reset_and_isolated_between_tasks(redis: Redis) -> None:
    store = RedisBatchStore(redis, PREFIX)
    first = await store.start_job("job-1", **OPTIONS)
    second = await store.start_job("job-2", **OPTIONS)

    async def observe(job: BatchJob) -> BatchJob | None:
        with batch_job(job):
            await asyncio.sleep(0)
            return current_batch_job()

    assert current_batch_job() is None
    assert await asyncio.gather(observe(first), observe(second)) == [first, second]
    with batch_job(first):
        with pytest.raises(ValueError), batch_job(second):
            raise ValueError("stop")
        assert current_batch_job() == first
    assert current_batch_job() is None


async def test_call_occurrences_distinguish_retries_and_reset_when_job_resumes(redis: Redis) -> None:
    store = RedisBatchStore(redis, PREFIX)
    job = await store.start_job("job-1", **OPTIONS)

    async def next_call() -> int:
        await asyncio.sleep(0)
        return batch_state.next_batch_call("request-hash")

    with batch_job(job):
        assert await asyncio.gather(next_call(), next_call()) == [1, 2]
        assert batch_state.next_batch_call("other-hash") == 1
        assert batch_state.next_batch_call("request-hash") == 3
    with batch_job(job):
        assert batch_state.next_batch_call("request-hash") == 1
    with pytest.raises(RuntimeError):
        batch_state.next_batch_call("request-hash")


async def test_only_first_reservation_can_submit_and_restarts_keep_it(redis: Redis) -> None:
    store = RedisBatchStore(redis, PREFIX)
    await store.start_job("job-1", **OPTIONS)

    reservations = await asyncio.gather(
        *(store.reserve_call("job-1", "request-hash", f"call-{index}") for index in range(16))
    )

    winners = [call for call, owned in reservations if owned]
    assert len(winners) == 1
    assert winners[0].state == "reserved"
    assert all(call == winners[0] for call, _ in reservations)
    assert await RedisBatchStore(redis, PREFIX).reserve_call("job-1", "request-hash", "replacement") == (
        winners[0],
        False,
    )


async def test_clean_shutdown_releases_only_calls_that_have_not_started_submission(redis: Redis) -> None:
    store = RedisBatchStore(redis, PREFIX)
    await store.start_job("job-1", **OPTIONS)
    for state in ("reserved", "submitted", "unknown", "failed"):
        await store.reserve_call("job-1", state, f"call-{state}")
    await store.save_submission([("job-1", "submitted")], "provider-batch")
    await store.fail_submission([("job-1", "unknown")], "response_lost", unknown=True)
    await store.fail_submission([("job-1", "failed")], "rejected", unknown=False)
    calls = [("job-1", state) for state in ("reserved", "submitted", "unknown", "failed", "missing")]

    await store.release_calls(calls)
    await store.release_calls(calls)

    assert await store.reserve_call("job-1", "reserved", "replacement") == (BatchCall("reserved", "replacement"), True)
    assert await store.reserve_call("job-1", "submitted", "replacement") == (
        BatchCall("submitted", "call-submitted", batch_id="provider-batch"),
        False,
    )
    assert await store.reserve_call("job-1", "unknown", "replacement") == (
        BatchCall("unknown", "call-unknown", error="response_lost"),
        False,
    )
    assert await store.reserve_call("job-1", "failed", "replacement") == (
        BatchCall("failed", "call-failed", error="rejected"),
        False,
    )
    assert await store.batch_jobs("provider-batch") == {"job-1"}


async def test_submitted_calls_share_batch_until_all_jobs_finish(redis: Redis) -> None:
    store = RedisBatchStore(redis, PREFIX)
    calls = [("job-1", "hash-a"), ("job-1", "hash-b"), ("job-2", "hash-c")]
    for index, (job_id, fingerprint) in enumerate(calls):
        await store.start_job(job_id, **OPTIONS)
        await store.reserve_call(job_id, fingerprint, f"call-{index}")

    await store.save_submission(calls, "provider-batch")

    for index, (job_id, fingerprint) in enumerate(calls):
        assert await store.reserve_call(job_id, fingerprint, "replacement") == (
            BatchCall("submitted", f"call-{index}", batch_id="provider-batch"),
            False,
        )
    assert await store.batches() == ["provider-batch"]
    assert await store.batch_jobs("provider-batch") == {"job-1", "job-2"}

    await store.finish_job("job-1")
    await store.finish_job("job-1")
    await store.remove_batch("provider-batch")
    assert await store.batch_jobs("provider-batch") == {"job-2"}
    assert await store.batches() == ["provider-batch"]

    await store.finish_job("job-2")
    assert await store.batch_jobs("provider-batch") == set()
    assert await store.batches() == ["provider-batch"]
    await store.remove_batch("provider-batch")
    assert await store.batches() == []


@pytest.mark.parametrize(("unknown", "state"), [(True, "unknown"), (False, "failed")])
async def test_failed_submission_keeps_diagnostic_and_never_reserves_again(
    redis: Redis, unknown: bool, state: str
) -> None:
    store = RedisBatchStore(redis, PREFIX)
    await store.start_job("job-1", **OPTIONS)
    await store.reserve_call("job-1", "request-hash", "call-1")

    await store.fail_submission([("job-1", "request-hash")], "submission_lost", unknown=unknown)
    call, owned = await RedisBatchStore(redis, PREFIX).reserve_call("job-1", "request-hash", "replacement")

    assert not owned
    assert call.state == state
    assert call.custom_id == "call-1"
    assert call.error == "submission_lost"
    assert call.batch_id is None


async def test_final_result_survives_delivery_failure_and_finish(redis: Redis) -> None:
    store = RedisBatchStore(redis, PREFIX)
    await store.start_job("job-1", **OPTIONS)
    result = {"jobId": "job-1", "status": "DONE", "result": {"documentScore": 91.5}, "error": None}

    assert await store.get_result("job-1") is None
    await store.save_result("job-1", result)
    await store.save_result("job-1", {"status": "FAILED"})
    resumed = RedisBatchStore(redis, PREFIX)
    assert await resumed.get_result("job-1") == result
    await resumed.finish_job("job-1")
    assert await resumed.get_result("job-1") == result


async def test_active_state_does_not_expire_and_finished_state_is_retained(redis: Redis) -> None:
    store = RedisBatchStore(redis, PREFIX)
    first = await store.start_job("job-1", **OPTIONS)
    await store.reserve_call("job-1", "request-hash", "call-1")
    await store.save_result("job-1", {"status": "DONE"})
    keys = [key async for key in redis.scan_iter(match=f"{PREFIX}:*")]
    assert keys
    assert all([await redis.ttl(key) == -1 for key in keys])

    await store.finish_job("job-1")

    assert all([2_591_990 <= await redis.ttl(key) <= 2_592_000 for key in keys])
    assert await store.start_job("job-1", **{**OPTIONS, "model": "changed"}) == first
    assert await store.reserve_call("job-1", "request-hash", "replacement") == (
        BatchCall("reserved", "call-1"),
        False,
    )


async def test_submission_finishing_after_job_does_not_retain_provider_batch(redis: Redis) -> None:
    store = RedisBatchStore(redis, PREFIX)
    await store.start_job("job-1", **OPTIONS)
    await store.reserve_call("job-1", "request-hash", "call-1")
    await store.finish_job("job-1")

    await store.save_submission([("job-1", "request-hash")], "provider-batch")

    assert await store.batch_jobs("provider-batch") == set()
    assert await store.batches() == ["provider-batch"]
    call, owned = await store.reserve_call("job-1", "request-hash", "replacement")
    assert not owned and call.batch_id == "provider-batch"
