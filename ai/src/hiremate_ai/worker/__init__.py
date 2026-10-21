"""AI 워커. Redis 작업 대기열에서 분석 작업을 꺼내 분석 Agent를 실행하고 결과를 결과 대기열에 넣는다.

backend job 모듈이 자료가 들어올 때(지원 접수 등) 작업을 넣고, 결과를 꺼내 업무 데이터에 기록한다.
ai는 backend를 부르지 않는다 (아키텍처 규칙 2 · 3). 실행: ai 폴더에서 uv run python -m hiremate_ai.worker
"""

from hiremate_ai.worker.handlers import Handler, PermanentError, job_handlers
from hiremate_ai.worker.runner import Worker, WorkerOptions

__all__ = ["Handler", "PermanentError", "Worker", "WorkerOptions", "job_handlers"]
