from collections.abc import Sequence
from functools import cache
from typing import Annotated, Any, Protocol

from fastapi import Depends
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from hiremate_ai.config import settings
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.call_log import CallLog, DbCallLog
from hiremate_ai.llm.chat import ChatLlm, ToolAgent


class LlmClient(Protocol):
    """모델 호출. 모든 Agent는 이 인터페이스로만 모델을 부른다. 호출은 ai.llm_calls에 기록된다."""

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
        """system · user 지시로 모델을 불러 output 형식의 결과를 받는다.

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
    ) -> ToolAgent[T]:
        """모델이 도구를 골라 부르며 자료를 확인하고 output 형식으로 답하는 Agent(ReAct)를 만든다.

        무엇을 볼지 미리 정할 수 없는 곳(Root Agent의 B 분석 · 생성 경로)에만 쓴다.
        한 번 묻고 형식대로 받으면 structured를 쓴다.
        tools는 @tool로 만든 조회 도구다. context는 도구가 ToolRuntime으로 받을 조회 범위의 타입이고,
        값은 ToolAgent.run에 넘긴다. 도구 결과는 자료 블록으로 감싸지고 system에는 UNTRUSTED_RULE이 붙는다.
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


def build_llm(call_log: CallLog) -> LlmClient:
    """설정의 모델로 LlmClient를 만든다. 호출 로그를 DB가 아닌 곳에 남길 때(실제 모델 평가) 직접 부른다."""
    if not settings.llm_model:
        raise LlmNotConfiguredError("LLM_MODEL이 비어 있다. ai/.env에 모델 연결 설정을 넣는다 (ai/.env.example 참고).")
    if not settings.llm_api_key.get_secret_value():
        raise LlmNotConfiguredError("LLM_API_KEY가 비어 있다. 키가 필요 없는 서버면 아무 값이나 넣는다.")
    model = ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
        reasoning_effort=settings.llm_reasoning_effort,
    )
    return ChatLlm(
        model,
        call_log,
        model_name=settings.llm_model,
        method=settings.llm_structured_output,
        agent_max_calls=settings.llm_agent_max_calls,
    )


LlmDep = Annotated[LlmClient, Depends(get_llm)]
"""라우터 매개변수 타입. 예: async def plan(request: PlanRequest, llm: LlmDep) -> ChatPlan"""
