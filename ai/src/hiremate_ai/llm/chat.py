import json
import operator
import time
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from enum import StrEnum
from functools import reduce
from typing import Any, Literal, NotRequired, cast

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelCallLimitMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.structured_output import ToolStrategy
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from openai import LengthFinishReasonError
from pydantic import BaseModel, ValidationError, create_model

from hiremate_ai.llm.call_log import CallLog, CallRecord
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block
from hiremate_ai.llm.recipe import model_recipe

type StructuredMethod = Literal["json_schema", "function_calling", "json_mode"]

# 형식에 맞지 않거나 출력 길이 상한에서 잘린 답이 오면 한 번 더 묻는다
PARSE_ATTEMPTS = 2
# 답이 출력 길이 상한(LLM_MAX_TOKENS)에서 잘렸을 때 다시 물으며 덧붙이는 지시. 같은 지시로는 또 잘린다
SHORTER = "직전 답이 출력 길이 상한에서 잘렸다. 형식은 그대로 두고 더 짧게 쓴다. 같은 문장을 되풀이하지 않는다."
CUT = "출력 길이 상한에서 잘렸다"
# 도구 루프의 마지막 모델 호출에 덧붙이는 지시. 이때는 조회 도구 없이 최종 답만 낼 수 있다
LAST_CALL = "자료를 더 읽을 수 없다. 지금까지 확인한 자료로 최종 답을 낸다. 확인하지 못한 점은 확인이 필요하다고 둔다."
REUSED_READ = "동일한 조회 요청이 반복되어 기존 조회 결과를 재사용한다."
REPEATED_BATCH = "모든 조회가 반복이다. 기존 조회 결과로 최종 답을 낸다. 확인하지 못한 점은 확인이 필요하다고 둔다."
COALESCED_READ = "한 번에 요청한 동일한 조회는 한 번만 실행했다. 기존 조회 결과를 쓰고 필요한 다른 자료만 조회한다."


class LlmFailureReason(StrEnum):
    FORMAT = "FORMAT"
    VALIDATION = "VALIDATION"
    BUDGET = "BUDGET"


class LlmOutputError(RuntimeError):
    """모델 답을 완성하지 못한 이유를 보존한다."""

    def __init__(self, message: str, *, reason: LlmFailureReason = LlmFailureReason.FORMAT) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass
class ModelCallBudget:
    """요청 하나의 모델 호출 예산. 그래프 노드처럼 실행 context가 나뉘어도 같은 객체를 넘겨 이어 쓴다."""

    limit: int
    remaining: int
    interrupted_tools: list[str] = field(default_factory=list)


_MODEL_CALL_BUDGET: ContextVar[ModelCallBudget | None] = ContextVar("model_call_budget", default=None)
_RESERVED_MODEL_CALLS: ContextVar[int] = ContextVar("reserved_model_calls", default=0)


@contextmanager
def model_call_budget(limit: int) -> Iterator[None]:
    """요청의 모든 모델 호출이 예산을 공유한다. 병렬 도구도 같은 남은 횟수를 사용한다.

    이미 예산이 있는 실행 안에서는 기존 예산을 이어 쓴다. 종료하면 호출자 context로 복원한다.
    """
    budget = new_model_call_budget(limit)
    if _MODEL_CALL_BUDGET.get() is not None:
        yield
        return
    with using_model_call_budget(budget):
        yield


def new_model_call_budget(limit: int) -> ModelCallBudget:
    if limit < 0:
        raise ValueError("모델 호출 예산은 0 이상이어야 한다")
    return ModelCallBudget(limit=limit, remaining=limit)


@contextmanager
def using_model_call_budget(budget: ModelCallBudget) -> Iterator[None]:
    """이 블록의 모델 호출이 budget을 쓴다. 블록이 끝나면 호출자 context로 되돌린다."""
    token = _MODEL_CALL_BUDGET.set(budget)
    try:
        yield
    finally:
        _MODEL_CALL_BUDGET.reset(token)


@contextmanager
def reserve_model_calls(count: int) -> Iterator[None]:
    """도구 안의 분석이 마지막 답변용 호출을 소비하지 못하게 한다. 중첩 예약은 합산하지 않는다."""
    if count < 0:
        raise ValueError("보호할 모델 호출 수는 0 이상이어야 한다")
    token = _RESERVED_MODEL_CALLS.set(max(count, _RESERVED_MODEL_CALLS.get()))
    try:
        yield
    finally:
        _RESERVED_MODEL_CALLS.reset(token)


def interrupted_model_tools() -> tuple[str, ...]:
    """이번 요청에서 호출 예산으로 끝내지 못한 도구. 원문과 모델 출력은 보관하지 않는다."""
    budget = _MODEL_CALL_BUDGET.get()
    return tuple(budget.interrupted_tools) if budget is not None else ()


def record_interrupted_model_tool(name: str) -> None:
    """부분 결과를 반환한 도구도 완료되지 않은 검토로 남긴다."""
    budget = _MODEL_CALL_BUDGET.get()
    if budget is not None and name not in budget.interrupted_tools:
        budget.interrupted_tools.append(name)


def consume_model_call() -> None:
    """실제 모델 호출 직전에 한 회를 사용한다. await 없이 차감해 병렬 task의 중복 사용을 막는다."""
    budget = _MODEL_CALL_BUDGET.get()
    if budget is None:
        return
    if budget.remaining <= _RESERVED_MODEL_CALLS.get():
        raise LlmOutputError(f"요청의 모델 호출 상한을 넘었다 ({budget.limit}회)", reason=LlmFailureReason.BUDGET)
    budget.remaining -= 1


class _ToolState(AgentState[Any]):
    # 기본 private 필드는 그래프 재진입 입력에서 제외된다. 검증 후에도 같은 호출 예산을 이어받게 한다.
    thread_model_call_count: NotRequired[int]
    run_model_call_count: NotRequired[int]


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

    def analysis_recipe(self) -> dict[str, Any] | None:
        return model_recipe(self._model, method=self._method)

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
        messages: list[BaseMessage] = [SystemMessage(system), HumanMessage(user)]
        runnable = self._model.with_structured_output(output, method=self._method, include_raw=True)
        recorder = _Recorder(self._call_log, agent=agent, model=self._model_name)
        started = time.perf_counter()
        tokens = _Tokens()
        try:
            for _ in range(PARSE_ATTEMPTS):
                try:
                    consume_model_call()
                    result = cast(dict[str, Any], await runnable.ainvoke(messages))
                except (ValidationError, OutputParserException) as invalid:
                    # json_schema 방식은 형식 오류를 parsing_error 대신 예외로 알린다
                    failure: object = invalid
                    continue
                except LengthFinishReasonError:
                    failure = CUT
                    messages = [SystemMessage(system), HumanMessage(f"{user}\n\n{SHORTER}")]
                    continue
                tokens.add(result["raw"])
                if _at_limit(result["raw"], _max_tokens(self._model)):
                    failure = CUT
                    messages = [SystemMessage(system), HumanMessage(f"{user}\n\n{SHORTER}")]
                    continue
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
        forms: Mapping[str, type[BaseModel]] | None = None,
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
            forms=forms,
        )


class ToolAgent[T: BaseModel]:
    """도구 루프 Agent (ReAct). 모델이 도구를 골라 부르며 자료를 확인하고, 마지막에 output 형식으로 답한다.

    LlmClient.tool_agent로 만든다. 모델 호출마다 호출 로그를 남기고, 도구 결과는 자료 블록으로 감싸며,
    모델 호출이 정한 횟수(settings.llm_agent_max_calls)를 넘으면 멈춘다.
    최종 답을 형식별 도구(forms)로 나눴으면 받은 답을 {"kind": 도구 이름, **인자}로 검증해 output으로 바꾼다.
    """

    def __init__(
        self,
        graph: CompiledStateGraph[Any, Any, Any, Any],
        output: type[T],
        *,
        agent: str,
        forms: Mapping[type[BaseModel], str] | None = None,
    ) -> None:
        self._graph = graph
        self._output = output
        self._agent = agent
        self._forms = forms or {}

    async def run(
        self,
        user: str,
        *,
        context: object = None,
        validate: Callable[[T], Awaitable[str | None]] | None = None,
    ) -> T:
        """user 지시로 실행해 output 형식의 답을 받는다.

        context는 도구가 ToolRuntime의 runtime.context로 읽는 값이다. 조회 범위(기업 · 채용 · 전형)는
        도구 인자가 아니라 여기에 넣어 모델이 바꿀 수 없게 한다 (아키텍처 규칙 4).
        validate가 오류를 돌려주면 같은 자료와 호출 예산 안에서 한 번만 고쳐 쓴다.
        """
        state: dict[str, Any] = {"messages": [HumanMessage(user)]}
        for attempt in range(2):
            try:
                state = await self._graph.ainvoke(
                    state,
                    context=context,
                    # 기본 출력은 private 호출 수를 숨긴다. 재작성에도 원래 실행의 호출 수를 넘긴다.
                    output_keys=["messages", "structured_response", "thread_model_call_count", "run_model_call_count"],
                )
            except ModelCallLimitExceededError as exceeded:
                raise LlmOutputError(
                    f"{self._output.__name__} 답을 받기 전에 모델 호출 상한을 넘었다 ({self._agent})",
                    reason=LlmFailureReason.BUDGET,
                ) from exceeded
            result = state.get("structured_response")
            if isinstance(result, BaseModel) and (kind := self._forms.get(type(result))) is not None:
                try:
                    result = self._output.model_validate({"kind": kind, **result.model_dump()})
                except ValidationError as invalid:
                    raise LlmOutputError(f"{kind} 답을 {self._output.__name__}로 바꾸지 못했다: {invalid}") from invalid
            if not isinstance(result, self._output):
                raise LlmOutputError(f"{self._output.__name__} 형식의 답을 받지 못했다 ({self._agent})")
            problem = await validate(result) if validate is not None else None
            if problem is None:
                return result
            if attempt:
                raise LlmOutputError(
                    f"{self._output.__name__} 답을 검증하지 못했다: {problem}", reason=LlmFailureReason.VALIDATION
                )
            state = {**state, "messages": [*state["messages"], HumanMessage(problem)], "structured_response": None}
        raise AssertionError("도달할 수 없는 재작성 단계")


def final_answer_rule(names: Sequence[str]) -> str:
    """도구 루프 system에 붙이는 규칙. 서버가 도구 호출 앞의 글을 허용하면 모델이 답을 글로 쓰다 끊기는 일을 막는다."""
    target = f"{names[0]} 도구" if len(names) == 1 else f"{', '.join(names)} 중 하나의 도구"
    final = f"자료를 다 확인했으면 최종 답은 {target}의 인자로만 낸다."
    return f"응답은 언제나 도구 호출이다. 본문 글은 쓰지 않는다. {final}"


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
    forms: Mapping[str, type[BaseModel]] | None = None,
) -> ToolAgent[T]:
    """LangChain create_agent에 공통 미들웨어를 붙인다. ChatLlm과 FakeLlm이 같이 쓴다.

    forms를 주면 최종 답을 이름별 도구로 나눠 보여 준다. 모델은 고른 형식의 인자만 쓴다.
    """
    # ToolStrategy는 형식의 클래스 이름을 도구 이름으로 쓴다
    named = {name: create_model(name, __base__=form, __doc__=form.__doc__) for name, form in (forms or {}).items()}
    response_format = ToolStrategy(reduce(operator.or_, named.values()) if named else output)
    graph = create_agent(
        model,
        tools,
        system_prompt="\n\n".join(
            part for part in (system, UNTRUSTED_RULE, final_answer_rule(list(named) or [output.__name__])) if part
        ),
        middleware=[
            _ReadOnce(frozenset(tool.name for tool in tools)),
            _ToolResultBlock(),
            _ReserveFinalAnswer(),
            _LastCallAnswers(max_calls),
            _ShorterWhenCut(_max_tokens(model)),
            _CallLogMiddleware(_Recorder(call_log, agent=agent, model=model_name)),
            ModelCallLimitMiddleware(run_limit=max_calls, exit_behavior="error"),
            _ModelCallBudgetMiddleware(),
        ],
        response_format=response_format,
        state_schema=_ToolState,
        context_schema=context,
        # Root 그래프 노드 안에서 돌아도 대화방 체크포인터를 이어받지 않는다. 이어받으면 도구 결과(문서 본문)가 저장된다
        checkpointer=False,
    )
    return ToolAgent(graph, output, agent=agent, forms={form: name for name, form in named.items()})


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


type ReadKey = tuple[str, str]


def _read_key(call: Mapping[str, Any]) -> ReadKey:
    return call["name"], json.dumps(call["args"], ensure_ascii=False, sort_keys=True)


def _completed_reads(messages: Sequence[BaseMessage], names: frozenset[str]) -> dict[ReadKey, ToolMessage]:
    """이번 실행의 메시지에서 완료한 조회만 찾는다. 실패와 아직 실행 중인 호출은 재사용하지 않는다."""
    pending: dict[str, ReadKey] = {}
    completed: dict[ReadKey, ToolMessage] = {}
    for message in messages:
        if isinstance(message, AIMessage):
            pending = {
                call["id"]: _read_key(call)
                for call in message.tool_calls
                if call["name"] in names and call["id"] is not None
            }
        elif isinstance(message, ToolMessage) and message.status == "success":
            key = pending.get(message.tool_call_id)
            if key is not None:
                completed.setdefault(key, message)
    return completed


class _ReadOnce(AgentMiddleware[Any, Any, Any]):
    """동일 실행의 성공 조회를 재사용한다. 저장소나 공유 캐시 없이 도구 대화만 사용한다."""

    def __init__(self, names: frozenset[str]) -> None:
        super().__init__()
        self._names = names

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        saved = _completed_reads(request.state["messages"], self._names).get(_read_key(request.tool_call))
        if saved is None:
            return await handler(request)
        return saved.model_copy(
            update={
                "id": None,
                "tool_call_id": request.tool_call["id"],
                "content": data_block(
                    "tool",
                    f"{REUSED_READ}\n기존 도구 호출 번호: {saved.tool_call_id}. 앞선 원문과 근거를 사용한다.",
                    name=request.tool_call["name"],
                ),
                "additional_kwargs": {**saved.additional_kwargs, "read_reused": True},
            }
        )

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        latest_read = next(
            (
                (index, message)
                for index, message in reversed(list(enumerate(request.messages)))
                if isinstance(message, AIMessage) and any(call["name"] in self._names for call in message.tool_calls)
            ),
            None,
        )
        if latest_read is not None:
            index, latest = latest_read
            results = {}
            for tool_message in request.messages[index + 1 :]:
                if isinstance(tool_message, AIMessage):
                    break
                if isinstance(tool_message, ToolMessage):
                    results[tool_message.tool_call_id] = tool_message
            if latest.tool_calls and all(
                call["name"] in self._names
                and call["id"] in results
                and results[call["id"]].additional_kwargs.get("read_reused")
                for call in latest.tool_calls
            ):
                request = request.override(tools=[], messages=[*request.messages, HumanMessage(REPEATED_BATCH)])
            elif latest.additional_kwargs.get("read_coalesced"):
                request = request.override(messages=[*request.messages, HumanMessage(COALESCED_READ)])
        response = await handler(request)
        messages = []
        for message in response.result:
            if isinstance(message, AIMessage):
                seen: set[ReadKey] = set()
                calls = []
                for call in message.tool_calls:
                    key = _read_key(call)
                    if call["name"] in self._names:
                        if key in seen:
                            continue
                        seen.add(key)
                    calls.append(call)
                if len(calls) != len(message.tool_calls):
                    message = message.model_copy(
                        update={
                            "tool_calls": calls,
                            "additional_kwargs": {**message.additional_kwargs, "read_coalesced": True},
                        }
                    )
            messages.append(message)
        return replace(response, result=messages)


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


class _ReserveFinalAnswer(AgentMiddleware[Any, Any, Any]):
    """병렬 도구와 재시도도 하나의 최종 호출을 남기고, 예산 종료를 제어된 조회 결과로 돌려준다."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        try:
            with reserve_model_calls(1):
                return await handler(request)
        except LlmOutputError as error:
            if error.reason is not LlmFailureReason.BUDGET:
                raise
            name = request.tool_call["name"]
            record_interrupted_model_tool(name)
            return ToolMessage(
                content=json.dumps(
                    {
                        "status": "incomplete",
                        "reason": "model_call_budget",
                        "tool": name,
                        "message": "이번 검토를 완료하지 못했다. 이미 검증한 결과로 답하고, 하지 못한 검토를 명시한다.",
                    },
                    ensure_ascii=False,
                ),
                name=name,
                tool_call_id=request.tool_call["id"],
                status="error",
            )


class _LastCallAnswers(AgentMiddleware[Any, Any, Any]):
    """호출 상한의 마지막 모델 호출에서는 조회 도구를 빼 최종 답만 낼 수 있게 한다.

    자료를 더 읽으려다 상한을 넘기면 그때까지 확인한 자료도 버리고 실패한다.
    """

    def __init__(self, max_calls: int) -> None:
        super().__init__()
        self._max_calls = max_calls

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        # 실행은 질문 하나로 시작하므로 앞선 AI 메시지 수가 이번 실행에서 부른 모델 호출 수다
        called = sum(isinstance(message, AIMessage) for message in request.messages)
        budget = _MODEL_CALL_BUDGET.get()
        if called + 1 >= self._max_calls or (budget is not None and budget.remaining <= 1):
            request = request.override(tools=[], messages=[*request.messages, HumanMessage(LAST_CALL)])
        return await handler(request)


class _ShorterWhenCut(AgentMiddleware[Any, Any, Any]):
    """답이 출력 길이 상한에서 잘리면 짧게 쓰라고 덧붙여 한 번 더 묻는다. 또 잘리면 실패로 둔다.

    잘린 도구 호출 인자도 JSON으로 읽힐 수 있어, 그대로 두면 되풀이하다 끊긴 글이 답이 된다.
    max_tokens는 모델의 출력 상한이다. 잘린 JSON을 닫아 돌려주며 finish_reason을 바꾸지 않는 처리 업체가 있어
    출력 토큰이 상한에 닿았는지도 본다.
    """

    def __init__(self, max_tokens: int | None) -> None:
        super().__init__()
        self._max_tokens = max_tokens

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        response = await handler(request)
        if not self._cut(response):
            return response
        response = await handler(request.override(messages=[*request.messages, HumanMessage(SHORTER)]))
        if self._cut(response):
            raise LlmOutputError(f"도구 루프의 답이 {CUT}")
        return response

    def _cut(self, response: ModelResponse[Any]) -> bool:
        return any(
            isinstance(message, AIMessage)
            and (message.response_metadata.get("finish_reason") == "length" or _at_limit(message, self._max_tokens))
            for message in response.result
        )


def _max_tokens(model: BaseChatModel) -> int | None:
    """모델의 출력 상한(ChatOpenAI의 max_tokens). 없으면 None."""
    limit = getattr(model, "max_tokens", None)
    return limit if isinstance(limit, int) else None


def _at_limit(message: object, max_tokens: int | None) -> bool:
    """출력 토큰이 상한에 닿았는가. 어떤 처리 업체는 잘린 JSON을 닫아 돌려주고 finish_reason을 그대로 둔다."""
    usage = getattr(message, "usage_metadata", None)
    return max_tokens is not None and usage is not None and usage["output_tokens"] >= max_tokens


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


class _ModelCallBudgetMiddleware(AgentMiddleware[Any, Any, Any]):
    """다른 미들웨어의 재시도와 중첩 호출까지 요청의 공유 예산에서 차감한다."""

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        consume_model_call()
        return await handler(request)


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
