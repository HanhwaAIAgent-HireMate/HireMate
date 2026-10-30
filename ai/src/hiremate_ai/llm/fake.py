from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from hiremate_ai.config import settings
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.chat import ToolAgent, build_tool_agent, consume_model_call, transcript


@dataclass(frozen=True)
class LlmCall:
    """FakeLlm이 받은 호출 한 번. 도구 루프 Agent 호출이면 user는 지금까지의 대화(질문, 도구 호출과 결과)다."""

    agent: str
    system: str
    user: str
    output: type[BaseModel]


@dataclass(frozen=True)
class ToolCall:
    """도구 루프 Agent에서 모델이 도구를 부르는 응답. 여러 도구를 한 번에 부르면 리스트로 넣는다."""

    name: str
    args: dict[str, Any] = field(default_factory=dict)


type FakeReply = BaseModel | ToolCall | list[ToolCall]
type FakeResponse = FakeReply | Callable[[LlmCall], FakeReply]


class FakeLlm:
    """테스트용 LLM. 정해 둔 응답을 차례로 돌려주고 호출을 calls에 기록한다. 응답이 함수면 호출 정보로 응답을 만든다.

    도구 루프 Agent는 모델 호출 한 번마다 응답 하나를 쓴다. ToolCall이면 도구를 부르고, output 형식의 값이면 답을 낸다.
    최종 답을 종류별 도구(forms)로 나눴으면 그 형식의 값이 답이다.
    """

    def __init__(self, *responses: FakeResponse, recipe: dict[str, Any] | None = None) -> None:
        self._responses = deque(responses)
        self.calls: list[LlmCall] = []
        self._recipe = recipe if recipe is not None else {"implementation": "fake-v1"}

    def analysis_recipe(self) -> dict[str, Any]:
        return dict(self._recipe)

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
        consume_model_call()
        result = self._reply(LlmCall(agent=agent, system=system, user=user, output=output))
        if not isinstance(result, output):
            raise AssertionError(f"FakeLlm 응답이 {output.__name__}가 아니다 ({type(result).__name__})")
        return result

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
        return build_tool_agent(
            _FakeChatModel(llm=self, agent=agent, output=output, forms=dict(forms or {})),
            _NoCallLog(),
            output,
            model_name="fake",
            agent=agent,
            system=system,
            tools=tools,
            context=context,
            max_calls=max_calls or settings.llm_agent_max_calls,
            forms=forms,
        )

    def _reply(self, call: LlmCall) -> FakeReply:
        self.calls.append(call)
        if not self._responses:
            raise AssertionError(f"FakeLlm에 남은 응답이 없다 ({call.agent})")
        response = self._responses.popleft()
        return response(call) if callable(response) else response


class _FakeChatModel(BaseChatModel):
    """FakeLlm 응답을 도구 루프 Agent의 모델 답으로 바꾼다."""

    llm: FakeLlm
    agent: str
    output: type[BaseModel]
    forms: dict[str, type[BaseModel]]

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        system = next((message.text for message in messages if isinstance(message, SystemMessage)), "")
        rest = [message for message in messages if not isinstance(message, SystemMessage)]
        reply = self.llm._reply(LlmCall(agent=self.agent, system=system, user=transcript(rest), output=self.output))
        return ChatResult(generations=[ChatGeneration(message=self._message(reply, step=len(self.llm.calls)))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, **kwargs)

    def _message(self, reply: FakeReply, *, step: int) -> AIMessage:
        if isinstance(reply, BaseModel) and self.forms:
            # 최종 답을 종류별 도구로 나눴으면 형식이 같은 도구의 호출로 받는다
            name = next((name for name, form in self.forms.items() if type(reply) is form), None)
            if name is None:
                raise AssertionError(f"FakeLlm 응답이 {', '.join(self.forms)} 형식이 아니다 ({type(reply).__name__})")
            calls = [ToolCall(name, reply.model_dump(mode="json"))]
        elif isinstance(reply, BaseModel):
            if not isinstance(reply, self.output):
                raise AssertionError(f"FakeLlm 응답이 {self.output.__name__}가 아니다 ({type(reply).__name__})")
            # 도구 루프 Agent는 답도 output 이름의 도구 호출로 받는다 (ToolStrategy)
            calls = [ToolCall(self.output.__name__, reply.model_dump(mode="json"))]
        else:
            calls = reply if isinstance(reply, list) else [reply]
        tool_calls = [{"name": call.name, "args": call.args, "id": f"call_{step}_{i}"} for i, call in enumerate(calls)]
        return AIMessage("", tool_calls=tool_calls)


class _NoCallLog:
    """FakeLlm은 호출을 calls에 기록하므로 호출 로그는 남기지 않는다."""

    async def record(self, record: CallRecord) -> None:
        pass
