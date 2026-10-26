"""지원서 배치 작업의 고정된 실행 맥락과 결과 전달 재시도."""

import asyncio
import logging
import time

from pydantic import ValidationError

from hiremate_ai.contract import Job, JobResult, JobStatus
from hiremate_ai.llm.batch import BatchError
from hiremate_ai.llm.batch_state import BatchJob, BatchStore, batch_job
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.worker.handlers import Handler, PermanentError

log = logging.getLogger(__name__)


class ApplicationBatchJobs:
    """작업을 다시 맡아도 모델 설정, 날짜와 전체 한도를 처음 값으로 이어 쓴다."""

    def __init__(
        self,
        store: BatchStore,
        *,
        timeout_seconds: float,
        model: str,
        provider: str,
        max_tokens: int,
        temperature: float | None,
        reasoning_effort: str | None,
        attempts: int = 2,
        retry_delay_seconds: float = 5,
    ) -> None:
        self._store = store
        self._timeout_seconds = timeout_seconds
        self._model = model
        self._provider = provider
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._reasoning_effort = reasoning_effort
        self._attempts = attempts
        self._retry_delay_seconds = retry_delay_seconds

    def handles(self, job: Job | JobResult) -> bool:
        return job.type == "application/analyze"

    async def run(self, job: Job, handler: Handler) -> JobResult:
        job_id = str(job.job_id)
        saved = await self._store.get_result(job_id)
        if saved is not None:
            return JobResult.model_validate(saved)
        context = await self._store.start_job(
            job_id,
            timeout_seconds=self._timeout_seconds,
            model=self._model,
            provider=self._provider,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            reasoning_effort=self._reasoning_effort,
        )
        remaining = context.deadline - time.time()
        try:
            if remaining <= 0:
                raise TimeoutError
            async with asyncio.timeout(remaining):
                result = await self._analyze(job, handler, context)
        except TimeoutError:
            result = self._failed(job, "지원서 배치 분석의 전체 시간 한도를 다 썼다")
        await self._store.save_result(job_id, result.model_dump(mode="json"))
        # 중단된 워커가 늦게 끝나도 처음 확정한 결과와 다른 값을 backend에 보내지 않는다.
        committed = await self._store.get_result(job_id)
        if committed is None:
            raise RuntimeError("지원서 배치 결과를 저장한 뒤 읽지 못했다")
        return JobResult.model_validate(committed)

    async def _analyze(self, job: Job, handler: Handler, context: BatchJob) -> JobResult:
        for attempt in range(self._attempts):
            try:
                with batch_job(context):
                    output = await handler(dict(job.payload))
                return JobResult(
                    job_id=job.job_id,
                    type=job.type,
                    target=job.target,
                    status=JobStatus.DONE,
                    result=output,
                    error=None,
                )
            except (BatchError, LlmOutputError, PermanentError, ValidationError) as error:
                return self._failed(job, str(error))
            except TimeoutError:
                raise
            except Exception as error:
                log.warning("지원서 배치 분석 %s의 %d번째 시도 실패", job.job_id, attempt + 1, exc_info=True)
                if attempt + 1 >= self._attempts:
                    return self._failed(job, f"{type(error).__name__}: {error}")
                await asyncio.sleep(self._retry_delay_seconds)
        raise AssertionError("시도 횟수는 1 이상이어야 한다")

    async def finish(self, job_id: str) -> None:
        """backend 결과 스트림에 기록한 뒤에만 제공자 배치의 참조를 해제한다."""
        await self._store.finish_job(job_id)

    @staticmethod
    def _failed(job: Job, error: str) -> JobResult:
        return JobResult(
            job_id=job.job_id, type=job.type, target=job.target, status=JobStatus.FAILED, result=None, error=error
        )
