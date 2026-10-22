"""AI 워커 실행. ai 폴더에서: uv run python -m hiremate_ai.worker

ai 서버(uvicorn)와 같은 설정(ai/.env)을 쓰고 따로 띄운다. 여러 개 띄워도 같은 작업을 두 번 맡지 않는다.
"""

import asyncio
import contextlib
import logging
import os
import signal
import socket

from hiremate_ai.agents.analysis.application.store import DbReviewStore
from hiremate_ai.config import settings
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.client import get_llm
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
    worker = Worker(redis, job_handlers(get_llm(), DbReviewStore(sessions), sessions), options)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        # Windows는 신호 처리기를 달 수 없다. Ctrl+C로 멈추면 처리 중인 작업은 다른 워커가 이어받는다
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signum, stop.set)
    log.info("AI 워커 시작: %s (동시 처리 %d)", options.consumer, options.concurrency)
    try:
        await worker.run(stop)
    finally:
        await redis.aclose()
    log.info("AI 워커 멈춤: %s", options.consumer)


if __name__ == "__main__":
    # Windows 기본 루프(ProactorEventLoop)에서는 psycopg가 async로 DB에 붙지 못해 SelectorEventLoop로 돌린다
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
