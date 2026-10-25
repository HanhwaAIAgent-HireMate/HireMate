"""LangSmith 추적. settings.langsmith_tracing이 참일 때만 기록을 보낸다.

ai 서버는 요청 하나(LlmDep을 받는 경로), AI 워커는 작업 하나를 기록(trace) 하나로 묶는다.
그 안의 그래프 노드, 모델 호출, 도구 호출은 LangChain이 하위 단계로 남긴다.
실제 모델 평가(tests/eval)는 묶지 않아 문항마다 그래프 실행이나 모델 호출 하나가 기록 하나다.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache

from langsmith import Client, trace, tracing_context

from hiremate_ai.config import settings


class TracingNotConfiguredError(RuntimeError):
    """추적을 켰는데 LangSmith 키가 없을 때."""


@contextmanager
def traced(name: str | None = None) -> Iterator[None]:
    """이 안에서 실행한 LangChain 단계를 LangSmith에 남긴다. 추적이 꺼져 있으면 아무것도 하지 않는다.

    name이 있으면 모두 name 기록 하나로 묶고, 없으면 바깥 LangChain 실행(그래프, 모델 호출)마다 기록 하나다.
    """
    if not settings.langsmith_tracing:
        yield
        return
    client = _client()
    project = settings.langsmith_project
    with tracing_context(enabled=True, client=client, project_name=project):
        if name is None:
            yield
            return
        with trace(name, client=client, project_name=project):
            yield


@cache
def _client() -> Client:
    key = settings.langsmith_api_key.get_secret_value()
    if not key:
        raise TracingNotConfiguredError(
            "LANGSMITH_TRACING을 켰는데 LANGSMITH_API_KEY가 비어 있다 (ai/.env.example 참고)."
        )
    return Client(api_key=key)
