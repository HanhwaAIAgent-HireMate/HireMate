from collections.abc import AsyncIterator, Mapping, Sequence
from functools import cache
from typing import Annotated, Any, Protocol
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, Request
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from hiremate_ai.config import settings
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.call_log import CallLog, DbCallLog
from hiremate_ai.llm.chat import ChatLlm, ToolAgent
from hiremate_ai.llm.tracing import traced


class LlmClient(Protocol):
    """모델 호출. 모든 Agent는 이 인터페이스로만 모델을 부른다. 호출은 ai.llm_calls에 기록된다."""

    def analysis_recipe(self) -> dict[str, Any] | None:
        """비밀정보 없는 실제 모델 설정. 알 수 없는 구현이면 None으로 재사용을 막는다."""
        ...

    async def structured[T: BaseModel](
        self, output: type[T], *, agent: str, system: str, user: str, images: Sequence[str] = ()
    ) -> T:
        """system과 user 지시로 모델을 불러 output 형식의 결과를 받는다.

        agent는 호출한 Agent 키다 (예: "root", "candidate-analyst"). 호출 로그에 남는다.
        제출 문서나 URL 본문은 hiremate_ai.llm.prompt의 블록으로 감싸 user에 넣는다.
        """
        ...

    def tool_agent[T: BaseModel](
        self,
        output: type[T],
        *,
        agent: str,
        system: str,
        tools: Sequence[BaseTool],
        context: type[Any] | None = None,
        forms: Mapping[str, type[BaseModel]] | None = None,
        max_calls: int | None = None,
    ) -> ToolAgent[T]:
        """모델이 도구를 골라 부르며 자료를 확인하고 output 형식으로 답하는 Agent(ReAct)를 만든다.

        Root Agent는 이 루프로 대화 맥락을 해석하고 조회 도구를 조합해 최종 명령을 낸다.
        한 번 묻고 형식대로 받으면 structured를 쓴다.
        tools는 @tool로 만든 조회 도구다. context는 도구가 ToolRuntime으로 받을 조회 범위의 타입이고,
        값은 ToolAgent.run에 넘긴다. 도구 결과는 자료 블록으로 감싸지고 system에는 UNTRUSTED_RULE이 붙는다.
        forms는 최종 답을 종류별 도구로 나눌 때 도구 이름별 인자 형식이다. 모델은 고른 종류의 인자만 쓰고,
        받은 답은 {"kind": 도구 이름, **인자}로 output을 검증해 만든다.
        max_calls는 모델 호출 상한이고, 비우면 settings.llm_agent_max_calls다.
        """
        ...


class LlmNotConfiguredError(RuntimeError):
    """모델 연결 설정이 없을 때."""


@cache
def get_llm() -> LlmClient:
    """FastAPI 의존성. 설정의 모델로 한 번 만들어 재사용한다. 호출은 ai.llm_calls에 기록한다.

    테스트는 app.dependency_overrides[get_llm]으로 FakeLlm을 넣는다.
    """
    return build_llm(DbCallLog(session_factory()))


def get_worker_llm() -> LlmClient:
    """AI 워커용. 워커 작업은 화면이 기다리지 않아서 호출 한 번 시간 한도를 WORKER_LLM_TIMEOUT_SECONDS로 길게 둔다.
    작업마다의 전체 시간 한도(예: 지원서 분석 application_timeout_seconds)는 작업 쪽에서 따로 지킨다.
    """
    return build_llm(DbCallLog(session_factory()), timeout=settings.worker_llm_timeout_seconds)


@cache
def get_document_normalization_llm() -> LlmClient:
    return build_document_normalization_llm(DbCallLog(session_factory()))


def build_document_normalization_llm(call_log: CallLog) -> LlmClient:
    """실제 PDF 평가에서 사용한 OpenAI 모델과 출력 설정을 문서 정제에만 적용한다."""
    key = settings.document_normalization_api_key
    if not key.get_secret_value() and settings.llm_base_url.rstrip("/") == "https://api.openai.com/v1":
        key = settings.llm_api_key
    if not key.get_secret_value():
        raise LlmNotConfiguredError("문서 정제에 사용할 OpenAI API 키가 설정되지 않았다")
    model = ChatOpenAI(
        model="gpt-6-luna",
        base_url="https://api.openai.com/v1",
        api_key=key,
        timeout=600,
        max_retries=2,
        max_tokens=32768,
        temperature=None,
        reasoning_effort="medium",
        use_responses_api=True,
        store=False,
    )
    return ChatLlm(
        model,
        call_log,
        model_name="gpt-6-luna",
        method="json_mode",
        agent_max_calls=settings.llm_agent_max_calls,
        structured_max_tokens={
            "application.normalize.characters": 16384,
            "application.normalize.characters.retry": 8192,
        },
        structured_parse_attempts=1,
        structured_shorten_on_cut=False,
    )


def build_llm(call_log: CallLog, *, timeout: float | None = None) -> LlmClient:
    """설정의 모델로 LlmClient를 만든다. 호출 로그를 DB가 아닌 곳에 남길 때(실제 모델 평가) 직접 부른다.

    timeout은 호출 한 번의 시간 한도다. 비우면 LLM_TIMEOUT_SECONDS(화면이 기다리는 동기 호출 기준)를 쓴다.
    """
    if not settings.llm_model:
        raise LlmNotConfiguredError("LLM_MODEL이 비어 있다. ai/.env에 모델 연결 설정을 넣는다 (ai/.env.example 참고).")
    if not settings.llm_api_key.get_secret_value():
        raise LlmNotConfiguredError("LLM_API_KEY가 비어 있다. 키가 필요 없는 서버면 아무 값이나 넣는다.")
    model = ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=timeout if timeout is not None else settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
        reasoning_effort=settings.llm_reasoning_effort,
        extra_body=_provider_limit(settings.llm_providers),
    )
    return ChatLlm(
        model,
        call_log,
        model_name=settings.llm_model,
        method=settings.llm_structured_output,
        agent_max_calls=settings.llm_agent_max_calls,
    )


@cache
def get_poster_llm() -> LlmClient | None:
    """포스터 디자인에서만 선택적으로 OpenAI 모델을 사용한다."""
    if not settings.poster_llm_model:
        return None
    if not settings.poster_api_key.get_secret_value():
        raise LlmNotConfiguredError("POSTER_LLM_MODEL에는 POSTER_API_KEY 설정이 필요합니다.")
    model = ChatOpenAI(
        model=settings.poster_llm_model,
        base_url="https://api.openai.com/v1",
        api_key=settings.poster_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        max_tokens=settings.llm_max_tokens,
        reasoning_effort="none",
    )
    return ChatLlm(
        model,
        DbCallLog(session_factory()),
        model_name=settings.poster_llm_model,
        method="function_calling",
        agent_max_calls=settings.llm_agent_max_calls,
    )


async def release_local_poster_model() -> bool:
    """Ollama 서버는 유지하고 가중치만 내려 이미지 모델의 GPU 공간을 확보한다."""
    base = settings.llm_base_url.rstrip("/").removesuffix("/v1")
    if urlsplit(base).hostname not in {"127.0.0.1", "localhost", "host.docker.internal"}:
        return False
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(base + "/api/generate", json={"model": settings.llm_model, "keep_alive": 0})
            response.raise_for_status()
            return response.json().get("done") is True
    except (httpx.HTTPError, ValueError):
        return False


def _provider_limit(providers: str) -> dict[str, Any] | None:
    """OpenRouter 요청 본문의 업체 제한. 적은 업체가 없으면 보내지 않는다."""
    only = [name.strip() for name in providers.split(",") if name.strip()]
    return {"provider": {"only": only}} if only else None


async def _traced_llm(request: Request, llm: Annotated[LlmClient, Depends(get_llm)]) -> AsyncIterator[LlmClient]:
    """요청 하나를 LangSmith 기록 하나로 묶는다 (추적을 켰을 때만). SSE 응답은 스트림이 끝날 때 기록이 닫힌다."""
    with traced(request.url.path):
        yield llm


LlmDep = Annotated[LlmClient, Depends(_traced_llm)]
"""라우터 매개변수 타입. 예: async def plan(request: PlanRequest, llm: LlmDep) -> ChatPlan"""


async def _traced_document_normalization_llm(
    request: Request, llm: Annotated[LlmClient, Depends(get_document_normalization_llm)]
) -> AsyncIterator[LlmClient]:
    with traced(request.url.path):
        yield llm


DocumentNormalizationLlmDep = Annotated[LlmClient, Depends(_traced_document_normalization_llm)]
