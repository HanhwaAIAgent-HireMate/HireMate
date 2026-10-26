import asyncio
import json
import time
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from hiremate_ai.llm.batch import BatchDispatcher, BatchError, BatchLlm, BatchSubmissionUnknown
from hiremate_ai.llm.batch_state import BatchCall, BatchJob, batch_job
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.chat import SHORTER, LlmOutputError, model_call_budget


def job(job_id: str = "job-1") -> BatchJob:
    return BatchJob(
        job_id=job_id,
        started_at=time.time(),
        deadline=time.time() + 60,
        today=date(2026, 10, 26),
        model="deepseek/deepseek-v4.1-flash",
        provider="sail-research",
        max_tokens=512,
        temperature=0.25,
        reasoning_effort="none",
    )


class MemoryStore:
    def __init__(self) -> None:
        self.calls: dict[tuple[str, str], BatchCall] = {}
        self.refs: dict[str, set[str]] = {}
        self.results: dict[str, dict[str, Any]] = {}
        self.saved_before_get = False
        self.reserved = asyncio.Event()

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
        return replace(
            job(job_id),
            deadline=time.time() + timeout_seconds,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

    async def reserve_call(self, job_id: str, fingerprint: str, custom_id: str) -> tuple[BatchCall, bool]:
        key = job_id, fingerprint
        if key in self.calls:
            return self.calls[key], False
        self.calls[key] = BatchCall("reserved", custom_id)
        self.reserved.set()
        return self.calls[key], True

    async def save_submission(self, calls: Sequence[tuple[str, str]], batch_id: str) -> None:
        for key in calls:
            self.calls[key] = replace(self.calls[key], state="submitted", batch_id=batch_id)
            self.refs.setdefault(batch_id, set()).add(key[0])
        self.saved_before_get = True

    async def fail_submission(self, calls: Sequence[tuple[str, str]], error: str, *, unknown: bool) -> None:
        for key in calls:
            self.calls[key] = replace(self.calls[key], state="unknown" if unknown else "failed", error=error)

    async def release_calls(self, calls: Sequence[tuple[str, str]]) -> None:
        for key in calls:
            if key in self.calls and self.calls[key].state == "reserved":
                del self.calls[key]

    async def get_result(self, job_id: str) -> dict[str, Any] | None:
        return self.results.get(job_id)

    async def save_result(self, job_id: str, result: dict[str, Any]) -> None:
        self.results[job_id] = result

    async def finish_job(self, job_id: str) -> None:
        for refs in self.refs.values():
            refs.discard(job_id)

    async def batches(self) -> list[str]:
        return list(self.refs)

    async def batch_jobs(self, batch_id: str) -> set[str]:
        return self.refs[batch_id].copy()

    async def remove_batch(self, batch_id: str) -> None:
        del self.refs[batch_id]


def completion(text: str, *, cut: bool = False) -> dict[str, Any]:
    return {
        "id": "chatcmpl-batch-test",
        "object": "chat.completion",
        "created": 0,
        "model": "deepseek/deepseek-v4.1-flash",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text, "refusal": None},
                "finish_reason": "length" if cut else "stop",
                "logprobs": None,
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    }


class Provider:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.posts: list[dict[str, Any]] = []
        self.gets = 0
        self.deletes: list[str] = []
        self.answers: list[dict[str, Any]] = []
        self.saved_answers: dict[str, list[dict[str, Any]]] = {}
        self.post_failure: str | None = None
        self.get_failures = 0
        self.status = "completed"
        self.item_error = False
        self.missing_result = False
        self.polled = asyncio.Event()

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payload = json.loads(request.content)
            self.posts.append(payload)
            if self.post_failure == "timeout":
                raise httpx.ReadTimeout("response lost", request=request)
            if self.post_failure == "json":
                return httpx.Response(202, content=b"not-json")
            if self.post_failure == "id":
                return httpx.Response(202, json={"status": "validating"})
            if self.post_failure == "server":
                return httpx.Response(503, json={"error": "upstream unavailable"})
            if self.post_failure == "reject":
                return httpx.Response(400, json={"error": "private document must not enter metadata"})
            batch_id = f"batch-{len(self.posts)}"
            self.saved_answers[batch_id] = [
                self.answers.pop(0)
                if self.answers
                else completion(json.dumps({"text": item["body"]["messages"][-1]["content"]}))
                for item in payload["requests"]
            ]
            return httpx.Response(202, json={"id": batch_id, "status": "validating"})
        batch_id = request.url.path.rsplit("/", 1)[-1]
        if request.method == "DELETE":
            self.deletes.append(batch_id)
            return httpx.Response(200, json={"id": batch_id, "deletion": {"openrouter": "deleted"}})
        assert self.store.saved_before_get, "provider output was read before its durable reference"
        self.gets += 1
        self.polled.set()
        if self.get_failures:
            self.get_failures -= 1
            return httpx.Response(503, json={"error": "temporary failure"})
        results = []
        for item, answer in zip(
            self.posts[int(batch_id.split("-")[-1]) - 1]["requests"], self.saved_answers[batch_id], strict=True
        ):
            results.append(
                {
                    "custom_id": item["custom_id"],
                    "response": None if self.item_error else {"status_code": 200, "body": answer},
                    "error": {"type": "invalid_request_error", "message": "private upstream content"}
                    if self.item_error
                    else None,
                }
            )
        return httpx.Response(
            200,
            json={"id": batch_id, "status": self.status, "results": [] if self.missing_result else results[::-1]},
        )


def dispatcher(provider: Provider, store: MemoryStore, **options: Any) -> BatchDispatcher:
    return BatchDispatcher(
        httpx.AsyncClient(base_url="https://openrouter.test/api/v1/", transport=httpx.MockTransport(provider.handle)),
        store,
        collection_seconds=options.pop("collection_seconds", 0.001),
        poll_seconds=0.001,
        **options,
    )


async def invoke(target: BatchDispatcher, job_id: str = "job-1", text: str = "문서") -> dict[str, Any]:
    with batch_job(job(job_id)):
        return await target.complete({"messages": [{"role": "user", "content": text}]})


async def test_groups_jobs_and_matches_reversed_custom_ids_after_saving_refs() -> None:
    store = MemoryStore()
    provider = Provider(store)
    target = dispatcher(provider, store)
    try:
        first, second = await asyncio.gather(invoke(target, "one", "첫 문서"), invoke(target, "two", "둘째 문서"))
        assert json.loads(first["choices"][0]["message"]["content"]) == {"text": "첫 문서"}
        assert json.loads(second["choices"][0]["message"]["content"]) == {"text": "둘째 문서"}
        [payload] = provider.posts
        assert list(payload) == ["endpoint", "model", "provider", "completion_window", "requests"]
        assert payload["endpoint"] == "/v1/chat/completions"
        assert payload["model"] == "deepseek/deepseek-v4.1-flash"
        assert payload["provider"] == {"only": ["sail-research"], "allow_fallbacks": False}
        assert payload["completion_window"] == "24h"
        assert len({item["custom_id"] for item in payload["requests"]}) == 2
        assert set(store.refs["batch-1"]) == {"one", "two"}
        assert "문서" not in repr(store.calls)
    finally:
        await target.aclose()


async def test_full_group_submits_before_collection_window() -> None:
    store = MemoryStore()
    provider = Provider(store)
    target = dispatcher(provider, store, max_requests=2, collection_seconds=60)
    try:
        await asyncio.wait_for(asyncio.gather(invoke(target, "one"), invoke(target, "two")), timeout=1)
        assert len(provider.posts) == 1
    finally:
        await target.aclose()


async def test_restart_replays_existing_batch_without_posting_again() -> None:
    store = MemoryStore()
    provider = Provider(store)
    first = dispatcher(provider, store)
    result = await invoke(first)
    await first.aclose()
    resumed = dispatcher(provider, store)
    try:
        assert await invoke(resumed) == result
        assert len(provider.posts) == 1
        assert provider.gets == 2
    finally:
        await resumed.aclose()


@pytest.mark.parametrize("failure", ["timeout", "json", "id", "server"])
async def test_unknown_submission_is_durable_and_never_retried(failure: str) -> None:
    store = MemoryStore()
    provider = Provider(store)
    provider.post_failure = failure
    target = dispatcher(provider, store)
    try:
        with pytest.raises(BatchSubmissionUnknown):
            await invoke(target)
        assert [call.state for call in store.calls.values()] == ["unknown"]
        with pytest.raises(BatchSubmissionUnknown):
            await invoke(target)
        assert len(provider.posts) == 1
    finally:
        await target.aclose()


async def test_definite_submission_rejection_is_permanent_without_upstream_content() -> None:
    store = MemoryStore()
    provider = Provider(store)
    provider.post_failure = "reject"
    target = dispatcher(provider, store)
    try:
        with pytest.raises(BatchError) as failure:
            await invoke(target)
        assert not isinstance(failure.value, BatchSubmissionUnknown)
        assert [call.state for call in store.calls.values()] == ["failed"]
        assert "private" not in repr(store.calls)
    finally:
        await target.aclose()


async def test_poll_transient_errors_reuse_the_same_batch() -> None:
    store = MemoryStore()
    provider = Provider(store)
    provider.get_failures = 2
    target = dispatcher(provider, store)
    try:
        assert (await invoke(target))["choices"]
        assert len(provider.posts) == 1
        assert provider.gets == 3
    finally:
        await target.aclose()


@pytest.mark.parametrize(
    "status,item_error,missing", [("expired", False, False), ("completed", True, False), ("completed", False, True)]
)
async def test_terminal_and_individual_failures_are_permanent(status: str, item_error: bool, missing: bool) -> None:
    store = MemoryStore()
    provider = Provider(store)
    provider.status = status
    provider.item_error = item_error
    provider.missing_result = missing
    target = dispatcher(provider, store)
    try:
        with pytest.raises(BatchError) as failure:
            await invoke(target)
        assert "private" not in str(failure.value)
        assert len(provider.posts) == 1
    finally:
        await target.aclose()


async def test_close_releases_queued_calls_that_were_never_submitted() -> None:
    store = MemoryStore()
    provider = Provider(store)
    target = dispatcher(provider, store, collection_seconds=60)
    running = asyncio.create_task(invoke(target))
    await store.reserved.wait()
    await target.aclose()
    with pytest.raises(asyncio.CancelledError):
        await running
    resumed = dispatcher(provider, store)
    try:
        assert (await invoke(resumed))["choices"]
        assert len(provider.posts) == 1
    finally:
        await resumed.aclose()


async def test_preexisting_reservation_without_confirmed_submission_stays_unknown() -> None:
    class RestoredStore(MemoryStore):
        async def reserve_call(self, job_id: str, fingerprint: str, custom_id: str) -> tuple[BatchCall, bool]:
            return BatchCall("reserved", "previous-call"), False

    store = RestoredStore()
    provider = Provider(store)
    target = dispatcher(provider, store)
    try:
        with pytest.raises(BatchSubmissionUnknown):
            await invoke(target)
        assert not provider.posts
    finally:
        await target.aclose()


async def test_close_while_reserving_releases_only_new_unsubmitted_call() -> None:
    class DelayedStore(MemoryStore):
        def __init__(self) -> None:
            super().__init__()
            self.proceed = asyncio.Event()

        async def reserve_call(self, job_id: str, fingerprint: str, custom_id: str) -> tuple[BatchCall, bool]:
            result = await super().reserve_call(job_id, fingerprint, custom_id)
            await self.proceed.wait()
            return result

    store = DelayedStore()
    provider = Provider(store)
    target = dispatcher(provider, store)
    running = asyncio.create_task(invoke(target))
    await store.reserved.wait()
    await target.aclose()
    store.proceed.set()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert store.calls == {}
    assert not provider.posts


async def test_failed_submission_does_not_retain_document_in_local_dispatcher_state() -> None:
    store = MemoryStore()
    provider = Provider(store)
    provider.post_failure = "timeout"
    target = dispatcher(provider, store)
    try:
        with pytest.raises(BatchSubmissionUnknown):
            await invoke(target, text="sensitive-applicant-document")
        assert "sensitive-applicant-document" not in repr(vars(target))
    finally:
        await target.aclose()


async def test_cleanup_waits_until_every_job_releases_shared_batch() -> None:
    store = MemoryStore()
    provider = Provider(store)
    target = dispatcher(provider, store)
    try:
        await asyncio.gather(invoke(target, "one"), invoke(target, "two"))
        await store.finish_job("one")
        await target.cleanup()
        assert provider.deletes == []
        await store.finish_job("two")
        await target.cleanup()
        assert provider.deletes == ["batch-1"]
        assert await store.batches() == []
    finally:
        await target.aclose()


async def test_cleanup_removes_registry_when_provider_already_deleted_batch() -> None:
    store = MemoryStore()
    provider = Provider(store)
    missing = False

    def handle(request: httpx.Request) -> httpx.Response:
        if missing and request.method == "GET":
            return httpx.Response(404, json={"error": "batch not found"})
        return provider.handle(request)

    target = BatchDispatcher(
        httpx.AsyncClient(base_url="https://openrouter.test/api/v1/", transport=httpx.MockTransport(handle)),
        store,
        collection_seconds=0,
        poll_seconds=0.001,
    )
    try:
        await invoke(target)
        await store.finish_job("job-1")
        missing = True
        await target.cleanup()
        assert await store.batches() == []
    finally:
        await target.aclose()


async def test_store_failure_during_flush_fails_waiter_without_sending_model_request() -> None:
    class BrokenStore(MemoryStore):
        checks = 0

        async def get_result(self, job_id: str) -> dict[str, Any] | None:
            self.checks += 1
            if self.checks > 1:
                raise RuntimeError("Redis unavailable")
            return None

    store = BrokenStore()
    provider = Provider(store)
    target = dispatcher(provider, store)
    try:
        with pytest.raises(BatchError):
            await asyncio.wait_for(invoke(target), timeout=0.2)
        assert not provider.posts
    finally:
        await target.aclose()


async def test_cancelled_waiter_can_resume_provider_work_without_a_second_post() -> None:
    store = MemoryStore()
    provider = Provider(store)
    provider.status = "in_progress"
    target = dispatcher(provider, store)
    running = asyncio.create_task(invoke(target))
    await provider.polled.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    await target.aclose()
    provider.status = "completed"
    resumed = dispatcher(provider, store)
    try:
        assert (await invoke(resumed))["choices"]
        assert len(provider.posts) == 1
    finally:
        await resumed.aclose()


async def test_finalized_job_cannot_start_or_submit_orphaned_calls() -> None:
    store = MemoryStore()
    provider = Provider(store)
    target = dispatcher(provider, store, collection_seconds=0.02)
    try:
        queued = asyncio.create_task(invoke(target))
        await store.reserved.wait()
        await store.save_result("job-1", {"status": "FAILED"})
        with pytest.raises(BatchError):
            await queued
        with pytest.raises(BatchError):
            await invoke(target, text="다음 문서")
        assert not provider.posts
    finally:
        await target.aclose()


class Summary(BaseModel):
    text: str


class CallLog:
    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def record(self, record: CallRecord) -> None:
        self.records.append(record)


async def test_structured_preserves_schema_frozen_options_tokens_and_model_budget() -> None:
    store = MemoryStore()
    provider = Provider(store)
    target = dispatcher(provider, store)
    log = CallLog()
    llm = BatchLlm(target, log)
    try:
        with batch_job(job()), model_call_budget(1):
            result = await llm.structured(Summary, agent="application", system="자료로 요약", user="제출 문서")
            with pytest.raises(LlmOutputError, match="상한"):
                await llm.structured(Summary, agent="application", system="자료로 요약", user="다음 문서")
        assert result.text == "제출 문서"
        [payload] = provider.posts
        [request] = payload["requests"]
        assert request["body"]["response_format"]["type"] == "json_schema"
        assert request["body"]["max_completion_tokens"] == 512
        assert request["body"]["temperature"] == 0.25
        assert request["body"]["reasoning"] == {"effort": "none"}
        first = log.records[0]
        assert (first.model, first.status, first.output) == (
            "deepseek/deepseek-v4.1-flash",
            "OK",
            {"text": "제출 문서"},
        )
        assert (first.input_tokens, first.output_tokens) == (12, 5)
    finally:
        await target.aclose()


async def test_structured_parse_retry_is_distinct_and_replayed_after_restart() -> None:
    store = MemoryStore()
    provider = Provider(store)
    provider.answers = [completion('{"wrong": true}'), completion('{"text": "검증 완료"}')]
    target = dispatcher(provider, store)
    try:
        with batch_job(job()):
            assert (
                await BatchLlm(target, CallLog()).structured(Summary, agent="application", system="", user="문서")
            ).text == "검증 완료"
    finally:
        await target.aclose()
    resumed = dispatcher(provider, store)
    try:
        with batch_job(job()):
            assert (
                await BatchLlm(resumed, CallLog()).structured(Summary, agent="application", system="", user="문서")
            ).text == "검증 완료"
        assert len(provider.posts) == 2
        assert len(store.calls) == 2
    finally:
        await resumed.aclose()


async def test_structured_shortens_cut_output_and_unwraps_permanent_provider_errors() -> None:
    store = MemoryStore()
    provider = Provider(store)
    provider.answers = [completion('{"text": "긴 답', cut=True), completion('{"text": "짧은 답"}')]
    target = dispatcher(provider, store)
    llm = BatchLlm(target, CallLog())
    try:
        with batch_job(job()):
            result = await llm.structured(Summary, agent="application", system="", user="정리")
        assert result.text == "짧은 답"
        assert SHORTER in provider.posts[1]["requests"][0]["body"]["messages"][-1]["content"]
        provider.item_error = True
        with batch_job(job("failed")), pytest.raises(BatchError):
            await llm.structured(Summary, agent="application", system="", user="오류")
        assert len(provider.posts) == 3
    finally:
        await target.aclose()


async def test_dispatcher_rejects_calls_without_worker_context() -> None:
    store = MemoryStore()
    provider = Provider(store)
    target = dispatcher(provider, store)
    try:
        with pytest.raises(BatchError):
            await target.complete({"messages": [{"role": "user", "content": "문서"}]})
        assert not store.calls
        assert not provider.posts
    finally:
        await target.aclose()
