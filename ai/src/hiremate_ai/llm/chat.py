import json
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelCallLimitMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.structured_output import ToolStrategy
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel, ValidationError

from hiremate_ai.llm.call_log import CallLog, CallRecord
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

type StructuredMethod = Literal["json_schema", "function_calling", "json_mode"]

# 형식에 맞지 않는 답이 오면 한 번 더 묻는다
PARSE_ATTEMPTS = 2


class LlmOutputError(RuntimeError):
    """모델 답이 요청한 형식에 맞지 않을 때."""


class ChatLlm:
    """LangChain 채팅 모델로 만든 LlmClient 구현. 모델 호출마다 call_log에 기록한다."""

    def __init__(
        self,
        model: BaseChatModel,
        call_log: CallLog,
        *,
        model_name: str,
        method: StructuredMethod,
        agent_max_calls: int,
    ) -> None:
        self._model = model
        self._call_log = call_log
        self._model_name = model_name
        self._method = method
        self._agent_max_calls = agent_max_calls

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
        messages: list[BaseMessage] = [SystemMessage(system), HumanMessage(user)]
        runnable = self._model.with_structured_output(output, method=self._method, include_raw=True)
        recorder = _Recorder(self._call_log, agent=agent, model=self._model_name)
        started = time.perf_counter()
        tokens = _Tokens()
        try:
            for _ in range(PARSE_ATTEMPTS):
                try:
                    result = cast(dict[str, Any], await runnable.ainvoke(messages))
                except (ValidationError, OutputParserException) as invalid:
                    # json_schema 방식은 형식 오류를 parsing_error 대신 예외로 알린다
                    failure: object = invalid
                    continue
                tokens.add(result["raw"])
                parsed = result["parsed"]
                if result["parsing_error"] is None and isinstance(parsed, output):
                    break
                failure = result["parsing_error"]
            else:
                raise LlmOutputError(f"{output.__name__} 형식의 답을 받지 못했다: {failure}")
        except Exception as exception:
            await recorder.record(system, user, started, tokens, error=exception)
            raise
        await recorder.record(system, user, started, tokens, output=parsed.model_dump(mode="json"))
        return parsed

    def tool_agent[T: BaseModel](
        self,
        output: type[T],
        *,
        agent: str,
        system: str,
        tools: Sequence[BaseTool],
        context: type[Any] | None = None,
    ) -> "ToolAgent[T]":
        return build_tool_agent(
            self._model,
            self._call_log,
            output,
            model_name=self._model_name,
            agent=agent,
            system=system,
            tools=tools,
            context=context,
            max_calls=self._agent_max_calls,
        )


class ToolAgent[T: BaseModel]:
    """도구 루프 Agent (ReAct). 모델이 도구를 골라 부르며 자료를 확인하고, 마지막에 output 형식으로 답한다.

    LlmClient.tool_agent로 만든다. 모델 호출마다 호출 로그를 남기고, 도구 결과는 자료 블록으로 감싸며,
    모델 호출이 정한 횟수(settings.llm_agent_max_calls)를 넘으면 멈춘다.
    """

    def __init__(self, graph: CompiledStateGraph[Any, Any, Any, Any], output: type[T], *, agent: str) -> None:
        self._graph = graph
        self._output = output
        self._agent = agent

    async def run(self, user: str, *, context: object = None) -> T:
        """user 지시로 실행해 output 형식의 답을 받는다.

        context는 도구가 ToolRuntime의 runtime.context로 읽는 값이다. 조회 범위(기업 · 채용 · 전형)는
        도구 인자가 아니라 여기에 넣어 모델이 바꿀 수 없게 한다 (아키텍처 규칙 4).
        """
        try:
            state = await self._graph.ainvoke({"messages": [HumanMessage(user)]}, context=context)
        except ModelCallLimitExceededError as exceeded:
            raise LlmOutputError(
                f"{self._output.__name__} 답을 받기 전에 모델 호출 상한을 넘었다 ({self._agent})"
            ) from exceeded
        result = state.get("structured_response")
        if not isinstance(result, self._output):
            raise LlmOutputError(f"{self._output.__name__} 형식의 답을 받지 못했다 ({self._agent})")
        return result


def build_tool_agent[T: BaseModel](
    model: BaseChatModel,
    call_log: CallLog,
    output: type[T],
    *,
    model_name: str,
    agent: str,
    system: str,
    tools: Sequence[BaseTool],
    context: type[Any] | None,
    max_calls: int,
) -> ToolAgent[T]:
    """LangChain create_agent에 공통 미들웨어를 붙인다. ChatLlm과 FakeLlm이 같이 쓴다."""
    graph = create_agent(
        model,
        tools,
        system_prompt="\n\n".join(part for part in (system, UNTRUSTED_RULE) if part),
        middleware=[
            _ToolResultBlock(),
            _CallLogMiddleware(_Recorder(call_log, agent=agent, model=model_name)),
            ModelCallLimitMiddleware(run_limit=max_calls, exit_behavior="error"),
        ],
        response_format=ToolStrategy(output),
        context_schema=context,
    )
    return ToolAgent(graph, output, agent=agent)


def transcript(messages: Sequence[BaseMessage]) -> str:
    """도구 루프의 대화(질문, 도구 호출, 도구 결과)를 호출 로그에 남길 글로 바꾼다."""
    lines = []
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            calls = (f"{call['name']}({json.dumps(call['args'], ensure_ascii=False)})" for call in message.tool_calls)
            lines.append(f"[ai] {', '.join(calls)}")
        elif isinstance(message, ToolMessage):
            lines.append(f"[tool {message.name}] {message.text}")
        else:
            lines.append(f"[{message.type}] {message.text}")
    return "\n".join(lines)


class _ToolResultBlock(AgentMiddleware[Any, Any, Any]):
    """도구 결과를 <data> 블록으로 감싼다. 도구가 가져온 원문 속 지시를 모델이 따르지 않게 한다 (규칙 5)."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        result = await handler(request)
        if isinstance(result, ToolMessage):
            block = data_block("tool", result.text, name=request.tool_call["name"])
            return result.model_copy(update={"content": block})
        return result


class _CallLogMiddleware(AgentMiddleware[Any, Any, Any]):
    """도구 루프의 모델 호출을 한 번씩 호출 로그에 남긴다."""

    def __init__(self, recorder: "_Recorder") -> None:
        super().__init__()
        self._recorder = recorder

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        system = request.system_message.text if request.system_message else ""
        user = transcript(request.messages)
        started = time.perf_counter()
        tokens = _Tokens()
        try:
            response = await handler(request)
        except Exception as exception:
            await self._recorder.record(system, user, started, tokens, error=exception)
            raise
        message = next(message for message in response.result if isinstance(message, AIMessage))
        tokens.add(message)
        calls = [{"name": call["name"], "args": call["args"]} for call in message.tool_calls]
        await self._recorder.record(
            system, user, started, tokens, output={"content": message.text, "tool_calls": calls}
        )
        return response


@dataclass(frozen=True)
class _Recorder:
    call_log: CallLog
    agent: str
    model: str

    async def record(
        self,
        system: str,
        user: str,
        started: float,
        tokens: "_Tokens",
        *,
        output: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        await self.call_log.record(
            CallRecord(
                agent=self.agent,
                model=self.model,
                status="ERROR" if error else "OK",
                system=system,
                user=user,
                output=output,
                error=f"{type(error).__name__}: {error}" if error else None,
                input_tokens=tokens.input,
                output_tokens=tokens.output,
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
        )


class _Tokens:
    def __init__(self) -> None:
        self.input: int | None = None
        self.output: int | None = None

    def add(self, message: object) -> None:
        usage = getattr(message, "usage_metadata", None)
        if usage:
            self.input = (self.input or 0) + usage["input_tokens"]
            self.output = (self.output or 0) + usage["output_tokens"]
