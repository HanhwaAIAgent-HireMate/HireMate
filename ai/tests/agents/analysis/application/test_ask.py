import pytest
from pydantic import BaseModel

from hiremate_ai.agents.analysis.application.ask import ATTEMPTS, ask
from hiremate_ai.llm.fake import FakeLlm, LlmCall


class Answer(BaseModel):
    text: str


class LengthFinishReasonError(Exception):
    """openai.LengthFinishReasonError와 이름이 같은 테스트용 오류. 모델 답이 출력 한도에서 잘렸다."""


def truncated(call: LlmCall) -> Answer:
    raise LengthFinishReasonError("length limit was reached")


async def test_asks_again_when_answer_is_cut_off() -> None:
    llm = FakeLlm(truncated, Answer(text="ok"))

    answer = await ask(llm, Answer, system="s", user="u")

    assert answer == Answer(text="ok")
    assert len(llm.calls) == 2
    assert all(call.agent == "application" for call in llm.calls)


async def test_gives_up_after_attempts() -> None:
    llm = FakeLlm(*[truncated] * ATTEMPTS)

    with pytest.raises(LengthFinishReasonError):
        await ask(llm, Answer, system="s", user="u")
    assert len(llm.calls) == ATTEMPTS


async def test_other_errors_are_not_retried() -> None:
    def broken(call: LlmCall) -> Answer:
        raise RuntimeError("server down")

    llm = FakeLlm(broken, Answer(text="ok"))

    with pytest.raises(RuntimeError):
        await ask(llm, Answer, system="s", user="u")
    assert len(llm.calls) == 1
