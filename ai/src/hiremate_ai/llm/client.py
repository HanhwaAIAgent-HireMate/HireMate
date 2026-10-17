from typing import Annotated, Protocol

from fastapi import Depends
from pydantic import BaseModel


class LlmClient(Protocol):
    """모델 호출. 모든 Agent는 이 인터페이스로만 모델을 부른다."""

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
        """system · user 지시로 모델을 불러 output 형식의 결과를 받는다.

        agent는 호출한 Agent 키다 (예: "root", "candidate-analyst"). 호출 로그에 남는다.
        """
        ...


class LlmNotConfiguredError(RuntimeError):
    """모델 연결 설정이 없을 때."""


def get_llm() -> LlmClient:
    """FastAPI 의존성. 테스트는 app.dependency_overrides[get_llm]으로 FakeLlm을 넣는다."""
    raise LlmNotConfiguredError("LLM 클라이언트 구현 전이다. 테스트에서는 hiremate_ai.llm.fake.FakeLlm을 쓴다.")


LlmDep = Annotated[LlmClient, Depends(get_llm)]
"""라우터 매개변수 타입. 예: async def plan(request: PlanRequest, llm: LlmDep) -> ChatPlan"""
