"""AI 워커 실행. ai 폴더에서: uv run python -m hiremate_ai.worker

ai 서버(uvicorn)와 같은 설정(ai/.env)을 쓰고 따로 띄운다. 여러 개 띄워도 같은 작업을 두 번 맡지 않는다.
"""

import asyncio
import contextlib
import logging
import os
import signal
import socket
from dataclasses import replace

import httpx

from hiremate_ai.agents.analysis.application.store import DbReviewStore
from hiremate_ai.config import settings
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.batch import BatchDispatcher, BatchLlm
from hiremate_ai.llm.call_log import DbCallLog
from hiremate_ai.llm.client import get_llm
from hiremate_ai.tools.profile_search import get_profile_embedder, profile_indexer
from hiremate_ai.worker.batch import ApplicationBatchJobs
from hiremate_ai.worker.batch_store import RedisBatchStore
from hiremate_ai.worker.handlers import job_handlers
from hiremate_ai.worker.runner import Worker, WorkerOptions, connect

log = logging.getLogger("hiremate_ai.worker")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    options = WorkerOptions(
        job_stream=settings.worker_job_stream,
        result_stream=settings.worker_result_stream,
        group=settings.worker_group,
        consumer=f"{socket.gethostname()}-{os.getpid()}",
        concurrency=settings.worker_concurrency,
        attempts=settings.worker_attempts,
        claim_idle_seconds=settings.worker_claim_idle_seconds,
    )
    redis = connect(settings.redis_url, options)
    sessions = session_factory()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        # Windows는 신호 처리기를 달 수 없다. Ctrl+C로 멈추면 처리 중인 작업은 다른 워커가 이어받는다
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signum, stop.set)
    try:
        async with contextlib.AsyncExitStack() as stack:
            batch: ApplicationBatchJobs | None = None
            application_llm: BatchLlm | None = None
            cleanup: asyncio.Task[None] | None = None
            application_stream = f"{options.job_stream}:application-batch"
            store = RedisBatchStore(redis, f"{settings.worker_job_stream}:batch")
            # 기능을 꺼도 이미 옮긴 작업과 제공자 배치는 같은 식별자로 마저 처리한다.
            pending_batches = await redis.xlen(application_stream) > 0 or bool(await store.batches())
            if settings.application_batch_enabled or pending_batches:
                client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        base_url="https://openrouter.ai/api/v1/",
                        headers={"Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}"},
                        timeout=settings.application_batch_http_timeout_seconds,
                    )
                )
                dispatcher = BatchDispatcher(
                    client,
                    store,
                    collection_seconds=settings.application_batch_collection_seconds,
                    max_requests=settings.application_batch_max_requests,
                    poll_seconds=settings.application_batch_poll_seconds,
                )
                stack.push_async_callback(dispatcher.aclose)
                application_llm = BatchLlm(dispatcher, DbCallLog(sessions))
                batch = ApplicationBatchJobs(
                    store,
                    timeout_seconds=settings.application_batch_timeout_seconds,
                    model=settings.application_batch_model,
                    provider=settings.application_batch_provider,
                    max_tokens=settings.llm_max_tokens,
                    temperature=settings.llm_temperature,
                    reasoning_effort="none",
                    attempts=settings.worker_attempts,
                )
                cleanup = asyncio.create_task(_clean_batches(dispatcher))
                log.info(
                    "지원서 분석 배치: %s / %s", settings.application_batch_model, settings.application_batch_provider
                )
            instant_llm = get_llm()
            reviews = DbReviewStore(sessions)
            indexer = profile_indexer(sessions, get_profile_embedder())
            handlers = job_handlers(instant_llm, reviews, sessions, profile_indexer=indexer)
            worker = Worker(
                redis,
                handlers,
                options,
                application_stream=application_stream if settings.application_batch_enabled else None,
            )
            log.info("AI 워커 시작: %s (동시 처리 %d)", options.consumer, options.concurrency)
            try:
                async with asyncio.TaskGroup() as tasks:
                    tasks.create_task(worker.run(stop))
                    if batch is not None:
                        batch_options = replace(
                            options,
                            job_stream=application_stream,
                            group=f"{options.group}:application-batch",
                            consumer=f"{options.consumer}:application-batch",
                            concurrency=settings.application_batch_concurrency,
                        )
                        batch_handlers = job_handlers(
                            instant_llm, reviews, sessions, application_llm=application_llm, profile_indexer=indexer
                        )
                        tasks.create_task(Worker(redis, batch_handlers, batch_options, batch=batch).run(stop))
            finally:
                if cleanup is not None:
                    cleanup.cancel()
                    await asyncio.gather(cleanup, return_exceptions=True)
    finally:
        await redis.aclose()
    log.info("AI 워커 멈춤: %s", options.consumer)


async def _clean_batches(dispatcher: BatchDispatcher) -> None:
    """결과 전달을 마친 작업과 연결된 제공자 배치를 끝난 뒤 삭제한다."""
    while True:
        try:
            await dispatcher.cleanup()
        except Exception:
            log.warning("끝난 제공자 배치를 정리하지 못했다. 같은 ID로 다시 확인한다", exc_info=True)
        await asyncio.sleep(settings.application_batch_poll_seconds)


if __name__ == "__main__":
    # Windows 기본 루프(ProactorEventLoop)에서는 psycopg가 async로 DB에 붙지 못해 SelectorEventLoop로 돌린다
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
