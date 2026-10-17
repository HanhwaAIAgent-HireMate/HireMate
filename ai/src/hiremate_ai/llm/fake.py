from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class LlmCall:
    """FakeLlm이 받은 호출 한 번."""

    agent: str
    system: str
    user: str
    output: type[BaseModel]


type FakeResponse = BaseModel | Callable[[LlmCall], BaseModel]


class FakeLlm:
    """테스트용 LLM. 정해 둔 응답을 차례로 돌려주고 호출을 calls에 기록한다. 응답이 함수면 호출 정보로 응답을 만든다."""

    def __init__(self, *responses: FakeResponse) -> None:
        self._responses = deque(responses)
        self.calls: list[LlmCall] = []

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
        call = LlmCall(agent=agent, system=system, user=user, output=output)
        self.calls.append(call)
        if not self._responses:
            raise AssertionError(f"FakeLlm에 남은 응답이 없다 ({agent})")
        response = self._responses.popleft()
        result = response(call) if callable(response) else response
        if not isinstance(result, output):
            raise AssertionError(f"FakeLlm 응답이 {output.__name__}가 아니다 ({type(result).__name__})")
        return result
