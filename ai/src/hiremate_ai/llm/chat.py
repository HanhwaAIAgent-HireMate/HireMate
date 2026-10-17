import time
from typing import Any, Literal, cast

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from hiremate_ai.llm.call_log import CallLog, CallRecord

type StructuredMethod = Literal["json_schema", "function_calling", "json_mode"]

# 형식에 맞지 않는 답이 오면 한 번 더 묻는다
PARSE_ATTEMPTS = 2


class LlmOutputError(RuntimeError):
    """모델 답이 요청한 형식에 맞지 않을 때."""


class ChatLlm:
    """LangChain 채팅 모델로 구조화 출력을 받는 LlmClient 구현. 호출마다 call_log에 기록한다."""

    def __init__(self, model: BaseChatModel, call_log: CallLog, *, model_name: str, method: StructuredMethod) -> None:
        self._model = model
        self._call_log = call_log
        self._model_name = model_name
        self._method = method

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
        messages: list[BaseMessage] = [SystemMessage(system), HumanMessage(user)]
        runnable = self._model.with_structured_output(output, method=self._method, include_raw=True)
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
            await self._record(agent, system, user, started, tokens, error=exception)
            raise
        await self._record(agent, system, user, started, tokens, output=parsed)
        return parsed

    async def _record(
        self,
        agent: str,
        system: str,
        user: str,
        started: float,
        tokens: "_Tokens",
        *,
        output: BaseModel | None = None,
        error: Exception | None = None,
    ) -> None:
        await self._call_log.record(
            CallRecord(
                agent=agent,
                model=self._model_name,
                status="ERROR" if error else "OK",
                system=system,
                user=user,
                output=output.model_dump(mode="json") if output else None,
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
