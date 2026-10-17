import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from hiremate_ai.llm.client import LlmDep, LlmNotConfiguredError, get_llm
from hiremate_ai.llm.fake import FakeLlm, LlmCall


class Summary(BaseModel):
    text: str


class Score(BaseModel):
    value: int


async def test_fake_returns_responses_in_order_and_records_calls() -> None:
    llm = FakeLlm(Summary(text="첫 번째"), Summary(text="두 번째"))

    first = await llm.structured(Summary, agent="report", system="요약한다", user="자료 1")
    second = await llm.structured(Summary, agent="report", system="요약한다", user="자료 2")

    assert [first.text, second.text] == ["첫 번째", "두 번째"]
    assert [call.user for call in llm.calls] == ["자료 1", "자료 2"]
    assert llm.calls[0] == LlmCall(agent="report", system="요약한다", user="자료 1", output=Summary)


async def test_fake_builds_response_from_call() -> None:
    llm = FakeLlm(lambda call: Summary(text=call.user.upper()))

    result = await llm.structured(Summary, agent="posting", system="", user="java")

    assert result.text == "JAVA"


async def test_fake_rejects_wrong_type_and_missing_response() -> None:
    llm = FakeLlm(Summary(text="요약"))

    with pytest.raises(AssertionError, match="Score"):
        await llm.structured(Score, agent="root", system="", user="")
    with pytest.raises(AssertionError, match="남은 응답"):
        await llm.structured(Summary, agent="root", system="", user="")


def test_router_gets_fake_through_dependency_override() -> None:
    router = APIRouter()

    @router.post("/agents/report/write")
    async def write(llm: LlmDep) -> Summary:
        return await llm.structured(Summary, agent="report", system="", user="")

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_llm] = lambda: FakeLlm(Summary(text="리포트"))

    response = TestClient(app).post("/agents/report/write")

    assert response.json() == {"text": "리포트"}


def test_get_llm_without_implementation() -> None:
    with pytest.raises(LlmNotConfiguredError):
        get_llm()
