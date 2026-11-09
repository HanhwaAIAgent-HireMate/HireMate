"""Application Agent의 모델 호출 한 번. 답이 출력 한도에서 잘리면 다시 묻는다.

구조화 출력에서 모델이 JSON 중간에 공백 · 탭을 끝없이 써 출력 한도(LLM_MAX_TOKENS)에 걸리는 일이 가끔 있다
(gpt-4o-mini로 같은 이력서를 8번 물으면 1번꼴). 같은 질문을 다시 하면 대개 제대로 답한다.
지원자 한 명을 분석하는 데 모델을 여러 번 부르므로, 한 번 잘린 것으로 분석 전체가 실패하지 않게 한다.
"""

from pydantic import BaseModel

from hiremate_ai.llm.client import LlmClient

AGENT = "application"
ATTEMPTS = 3


async def ask[T: BaseModel](llm: LlmClient, output: type[T], *, system: str, user: str) -> T:
    """출력 한도에서 잘리면 ATTEMPTS번까지 다시 묻는다. 그 밖의 오류는 그대로 올린다."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return await llm.structured(output, agent=AGENT, system=system, user=user)
        except Exception as error:
            if attempt == ATTEMPTS or not truncated(error):
                raise
    raise AssertionError("ATTEMPTS는 1 이상이다")


def truncated(error: Exception) -> bool:
    """OpenAI 호환 SDK가 출력 한도로 답을 끊었을 때 내는 오류인가 (openai.LengthFinishReasonError)."""
    return type(error).__name__ == "LengthFinishReasonError"
