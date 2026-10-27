"""지원서 워커의 structured 호출을 OpenRouter 비동기 배치로 전송한다."""

import asyncio
import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from hiremate_ai.config import settings
from hiremate_ai.llm.batch_state import BatchJob, BatchStore, current_batch_job, next_batch_call
from hiremate_ai.llm.call_log import CallLog
from hiremate_ai.llm.chat import ChatLlm, ToolAgent


class BatchError(RuntimeError):
    """자동 재제출하지 않는 배치 분석 실패."""


class BatchSubmissionUnknown(BatchError):
    """제공자가 제출을 받았는지 확인할 수 없다."""


@dataclass
class _Call:
    job: BatchJob
    fingerprint: str
    custom_id: str
    body: dict[str, Any]
    future: asyncio.Future[dict[str, Any]]
    batch_id: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.job.job_id, self.fingerprint


class BatchDispatcher:
    """짧게 모은 호출을 제출하고, 저장된 배치 ID를 이어 조회한다.

    client는 인증 헤더와 OpenRouter /api/v1/ base_url이 설정된 전용 클라이언트다.
    aclose는 이 클라이언트도 닫는다. 요청 본문은 대기 중 메모리에만 보관한다.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        store: BatchStore,
        *,
        collection_seconds: float = 5,
        max_requests: int = 32,
        poll_seconds: float = 60,
    ) -> None:
        if collection_seconds < 0 or poll_seconds <= 0 or max_requests < 1:
            raise ValueError("배치 수집 시간은 0 이상, 조회 간격과 최대 건수는 양수여야 한다")
        self._client = client
        self._model_client = httpx.AsyncClient(transport=_BatchTransport(self))
        self._store = store
        self._collection_seconds = collection_seconds
        self._max_requests = max_requests
        self._poll_seconds = poll_seconds
        self._calls: dict[tuple[str, str], _Call] = {}
        self._pending: list[_Call] = []
        self._waiting: dict[str, list[_Call]] = {}
        self._flush: asyncio.Task[None] | None = None
        self._submissions: set[asyncio.Task[None]] = set()
        self._polls: dict[str, asyncio.Task[None]] = {}
        self._closed = False

    async def complete(self, body: dict[str, Any]) -> dict[str, Any]:
        job = current_batch_job()
        if job is None:
            raise BatchError("배치 모델은 워커 작업 context 안에서만 호출할 수 있다")
        if self._closed:
            raise BatchError("배치 전송기가 종료됐다")
        await self._check_job(job)
        # 제공자와 모델까지 해시에 넣는다. 문서 본문과 JSON schema는 Redis에 복사하지 않는다.
        body = {**body, "model": job.model}
        serialized = json.dumps({"provider": job.provider, "body": body}, sort_keys=True, separators=(",", ":"))
        body_hash = hashlib.sha256(serialized.encode()).hexdigest()
        occurrence = next_batch_call(body_hash)
        fingerprint = hashlib.sha256(f"{body_hash}:{occurrence}".encode()).hexdigest()
        key = job.job_id, fingerprint
        if key in self._calls:
            return await asyncio.shield(self._calls[key].future)
        custom_id = hashlib.sha256(f"{job.job_id}:{fingerprint}".encode()).hexdigest()
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        future.add_done_callback(_observe_future)
        pending = _Call(job, fingerprint, custom_id, body, future)
        self._calls[key] = pending
        try:
            saved, owner = await self._store.reserve_call(job.job_id, fingerprint, custom_id)
        except BaseException:
            self._calls.pop(key, None)
            future.cancel()
            raise
        pending.custom_id = saved.custom_id
        if self._closed:
            # aclose와 Redis 예약이 겹쳐도 이 호출은 아직 전송 큐에 들어가지 않았다.
            if owner:
                await self._store.release_calls([key])
            pending.body = {}
            future.cancel()
        elif owner:
            self._enqueue(pending)
        elif saved.state == "submitted" and saved.batch_id:
            pending.body = {}
            self._watch(saved.batch_id, [pending])
        elif saved.state == "failed":
            future.set_exception(BatchError(saved.error or "배치 제출이 거절됐다"))
        else:
            future.set_exception(BatchSubmissionUnknown("앞선 배치 제출 여부를 확인할 수 없어 자동 재제출하지 않는다"))
        try:
            return await asyncio.shield(future)
        finally:
            if future.done() and pending.batch_id is None:
                self._calls.pop(key, None)

    async def aclose(self) -> None:
        """진행 중 배치를 실패로 바꾸지 않고 task만 중단해 다음 워커가 복원한다."""
        if self._closed:
            return
        self._closed = True
        queued, self._pending = self._pending, []
        tasks = [*self._submissions, *self._polls.values()]
        if self._flush is not None:
            tasks.append(self._flush)
        for task in tasks:
            task.cancel()
        for call in self._calls.values():
            if not call.future.done():
                call.future.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            # 큐를 떠나 _submissions로 넘어간 호출은 POST가 시작됐을 수 있어 예약을 유지한다.
            await self._store.release_calls([call.key for call in queued])
        finally:
            for call in self._calls.values():
                call.body = {}
            self._calls.clear()
            self._waiting.clear()
            await self._client.aclose()
            await self._model_client.aclose()

    async def cleanup(self) -> None:
        """최종 결과 전달을 마친 모든 작업이 참조를 놓은 배치만 삭제한다."""
        for batch_id in await self._store.batches():
            if await self._store.batch_jobs(batch_id):
                continue
            try:
                response = await self._client.get(f"batches/{batch_id}")
                if response.status_code not in (404, 410):
                    if response.status_code != 200:
                        continue
                    data = response.json()
                    if not isinstance(data, dict) or data.get("status") not in _TERMINAL:
                        continue
                    if await self._store.batch_jobs(batch_id):
                        continue
                    deleted = await self._client.delete(f"batches/{batch_id}")
                    if deleted.status_code not in (200, 404, 410):
                        continue
            except (httpx.HTTPError, ValueError):
                continue
            poll = self._polls.pop(batch_id, None)
            if poll is not None:
                poll.cancel()
                await asyncio.gather(poll, return_exceptions=True)
            await self._store.remove_batch(batch_id)
            for call in self._waiting.pop(batch_id, []):
                self._calls.pop(call.key, None)
                if not call.future.done():
                    call.future.cancel()

    async def _check_job(self, job: BatchJob) -> None:
        if time.time() >= job.deadline:
            raise BatchError("배치 분석 전체 시간 한도를 넘었다")
        if await self._store.get_result(job.job_id) is not None:
            raise BatchError("최종 결과가 기록된 작업에는 새 배치 호출을 추가할 수 없다")

    def _enqueue(self, call: _Call) -> None:
        self._pending.append(call)
        group = [
            item for item in self._pending if (item.job.model, item.job.provider) == (call.job.model, call.job.provider)
        ]
        if len(group) >= self._max_requests:
            self._launch(group[: self._max_requests])
        if self._pending and (self._flush is None or self._flush.done()):
            self._flush = asyncio.create_task(self._flush_later())

    async def _flush_later(self) -> None:
        await asyncio.sleep(self._collection_seconds)
        while self._pending:
            first = self._pending[0]
            group = [
                item
                for item in self._pending
                if (item.job.model, item.job.provider) == (first.job.model, first.job.provider)
            ]
            self._launch(group[: self._max_requests])

    def _launch(self, calls: list[_Call]) -> None:
        keys = {call.key for call in calls}
        self._pending = [call for call in self._pending if call.key not in keys]
        task = asyncio.create_task(self._submit(calls))
        self._submissions.add(task)
        task.add_done_callback(self._submissions.discard)

    async def _submit(self, calls: list[_Call]) -> None:
        try:
            await self._send(calls)
        except Exception:
            # 저장소 장애도 task 밖에 남겨 대기자를 무기한 붙잡지 않는다. 예약은 복구 때 unknown으로 본다.
            for call in calls:
                call.body = {}
                if not call.future.done():
                    call.future.set_exception(BatchSubmissionUnknown("배치 제출 상태를 기록하거나 확인하지 못했다"))

    async def _send(self, calls: list[_Call]) -> None:
        active: list[_Call] = []
        for call in calls:
            try:
                await self._check_job(call.job)
            except BatchError as error:
                await self._fail([call], error, unknown=False)
            else:
                active.append(call)
        if not active:
            return
        first = active[0]
        payload = {
            "endpoint": "/v1/chat/completions",
            "model": first.job.model,
            "provider": {"only": [first.job.provider], "allow_fallbacks": False},
            "completion_window": "24h",
            "requests": [{"custom_id": call.custom_id, "body": call.body} for call in active],
        }
        try:
            response = await self._client.post("batches", json=payload)
        except httpx.HTTPError:
            await self._fail(
                active, BatchSubmissionUnknown("배치 제출 응답을 받지 못해 자동 재제출하지 않는다"), unknown=True
            )
            return
        if 400 <= response.status_code < 500 and response.status_code != 408:
            await self._fail(active, BatchError(f"배치 제출이 거절됐다 (HTTP {response.status_code})"), unknown=False)
            return
        batch_id: str | None = None
        if response.status_code == 202:
            try:
                data = response.json()
                if isinstance(data, dict) and isinstance(data.get("id"), str) and data["id"]:
                    batch_id = data["id"]
            except ValueError:
                pass
        if batch_id is None:
            await self._fail(
                active, BatchSubmissionUnknown("배치 제출 ID를 확인하지 못해 자동 재제출하지 않는다"), unknown=True
            )
            return
        try:
            await self._store.save_submission([call.key for call in active], batch_id)
        except Exception:
            await self._fail(
                active,
                BatchSubmissionUnknown(f"제출한 배치 참조를 저장하지 못했다 ({batch_id}). 자동 재제출하지 않는다"),
                unknown=True,
            )
            return
        for call in active:
            call.body = {}
        self._watch(batch_id, active)

    async def _fail(self, calls: list[_Call], error: BatchError, *, unknown: bool) -> None:
        try:
            await self._store.fail_submission([call.key for call in calls], str(error), unknown=unknown)
        finally:
            for call in calls:
                call.body = {}
                if not call.future.done():
                    call.future.set_exception(error)

    def _watch(self, batch_id: str, calls: list[_Call]) -> None:
        for call in calls:
            call.batch_id = batch_id
        self._waiting.setdefault(batch_id, []).extend(calls)
        if batch_id not in self._polls or self._polls[batch_id].done():
            self._polls[batch_id] = asyncio.create_task(self._poll(batch_id))

    async def _poll(self, batch_id: str) -> None:
        try:
            while True:
                data = await self._get_batch(batch_id)
                if data is not None:
                    status = data.get("status")
                    if not isinstance(status, str):
                        raise BatchError("제공자 배치 상태를 해석할 수 없다")
                    if status in {"failed", "expired", "cancelled"}:
                        raise BatchError(f"제공자 배치 작업이 종료됐다 ({status})")
                    if status == "completed" and data.get("results") is not None:
                        self._resolve(batch_id, data["results"])
                        return
                    if status not in {"validating", "in_progress", "finalizing", "completed"}:
                        raise BatchError("제공자 배치 상태를 해석할 수 없다")
                await asyncio.sleep(self._poll_seconds)
        except BatchError as error:
            for call in self._waiting[batch_id]:
                if not call.future.done():
                    call.future.set_exception(error)
        except Exception:
            for call in self._waiting[batch_id]:
                if not call.future.done():
                    call.future.set_exception(BatchError("배치 결과를 처리하지 못했다. 저장된 배치 ID를 보존한다"))

    async def _get_batch(self, batch_id: str) -> dict[str, Any] | None:
        try:
            response = await self._client.get(f"batches/{batch_id}")
            # 접수 직후에는 같은 배치가 잠시 404로 조회될 수 있다. 새로 제출하지 않고 같은 ID를 기다린다.
            if response.status_code in (404, 429) or response.status_code >= 500:
                return None
            if response.status_code != 200:
                raise BatchError(f"배치를 조회할 수 없다 (HTTP {response.status_code})")
            data = response.json()
            return data if isinstance(data, dict) else None
        except (httpx.HTTPError, ValueError):
            # 조회는 새 청구를 만들지 않으므로 같은 ID로 재시도한다.
            return None

    def _resolve(self, batch_id: str, results: object) -> None:
        if not isinstance(results, list):
            raise BatchError("제공자 배치 결과 형식을 해석할 수 없다")
        by_id: dict[str, dict[str, Any]] = {}
        for item in results:
            if isinstance(item, dict) and isinstance(item.get("custom_id"), str):
                if item["custom_id"] in by_id:
                    raise BatchError("배치 결과의 호출 식별자가 중복됐다")
                by_id[item["custom_id"]] = item
        for call in self._waiting[batch_id]:
            if call.future.done():
                continue
            item = by_id.get(call.custom_id)
            response = item.get("response") if item is not None else None
            if (
                item is None
                or item.get("error") is not None
                or not isinstance(response, dict)
                or response.get("status_code") != 200
                or not isinstance(response.get("body"), dict)
            ):
                call.future.set_exception(BatchError(f"배치의 개별 호출 결과가 없거나 실패했다 ({call.custom_id})"))
            else:
                call.future.set_result(response["body"])


_TERMINAL = {"completed", "failed", "expired", "cancelled"}


def _observe_future(future: asyncio.Future[dict[str, Any]]) -> None:
    # 전체 분석이 먼저 중단된 뒤 도착하는 개별 실패도 미수집 Future 경고를 만들지 않는다.
    if not future.cancelled():
        future.exception()


class _BatchTransport(httpx.AsyncBaseTransport):
    def __init__(self, dispatcher: BatchDispatcher) -> None:
        self._dispatcher = dispatcher

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != "/v1/chat/completions":
            raise BatchError("배치 전송기는 chat/completions 요청만 받는다")
        body = json.loads(await request.aread())
        if not isinstance(body, dict):
            raise BatchError("배치 호출 본문은 JSON 객체여야 한다")
        return httpx.Response(200, json=await self._dispatcher.complete(body), request=request)


class BatchLlm:
    """전송만 배치로 교체하고 ChatLlm의 검증, 재시도, 호출 로그를 유지한다."""

    def __init__(self, dispatcher: BatchDispatcher, call_log: CallLog) -> None:
        self._dispatcher = dispatcher
        self._call_log = call_log
        self._http_client = dispatcher._model_client
        self._models: dict[tuple[str, int, float | None, str | None], ChatLlm] = {}

    def analysis_recipe(self) -> dict[str, Any] | None:
        job = current_batch_job()
        if job is None:
            return None
        return {
            "implementation": "openrouter-batch-v1",
            "model": job.model,
            "provider": job.provider,
            "method": "json_schema",
            "max_tokens": job.max_tokens,
            "temperature": job.temperature,
            "reasoning_effort": job.reasoning_effort,
        }

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
        job = current_batch_job()
        if job is None:
            raise BatchError("배치 모델은 워커 작업 context 안에서만 호출할 수 있다")
        key = job.model, job.max_tokens, job.temperature, job.reasoning_effort
        if key not in self._models:
            model = ChatOpenAI(
                model=job.model,
                # 이 클라이언트는 _BatchTransport 안에서 끝나며 외부에 연결하지 않는다.
                base_url="https://batch.invalid/v1",
                api_key=SecretStr("batch-transport"),
                timeout=None,
                max_retries=0,
                max_tokens=job.max_tokens,
                temperature=job.temperature,
                extra_body={"reasoning": {"effort": job.reasoning_effort}} if job.reasoning_effort else None,
                http_async_client=self._http_client,
            )
            self._models[key] = ChatLlm(
                model,
                self._call_log,
                model_name=job.model,
                method="json_schema",
                agent_max_calls=settings.llm_agent_max_calls,
            )
        try:
            return await self._models[key].structured(output, agent=agent, system=system, user=user)
        except Exception as error:
            # OpenAI SDK는 사용자 전송기 예외도 APIConnectionError로 감싼다. 영구 실패 구분을 복원한다.
            cause: BaseException | None = error
            while cause is not None:
                if isinstance(cause, BatchError):
                    raise cause from None
                cause = cause.__cause__
            raise

    def tool_agent[T: BaseModel](
        self,
        output: type[T],
        *,
        agent: str,
        system: str,
        tools: Sequence[BaseTool],
        context: type[Any] | None = None,
    ) -> ToolAgent[T]:
        raise BatchError("배치 모델은 지원서의 structured 호출에만 사용한다")
