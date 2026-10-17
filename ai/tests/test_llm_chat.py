import json
from typing import Any

import httpx
import pytest
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hiremate_ai.config import settings
from hiremate_ai.db.llm_call import LlmCallLog
from hiremate_ai.llm import client
from hiremate_ai.llm.call_log import CallRecord, DbCallLog
from hiremate_ai.llm.chat import ChatLlm, LlmOutputError


class Summary(BaseModel):
    text: str


class RecordingCallLog:
    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def record(self, record: CallRecord) -> None:
        self.records.append(record)


def completion(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content, "refusal": None},
                "finish_reason": "stop",
                "logprobs": None,
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    }


def chat_llm(contents: list[str], call_log: RecordingCallLog, requests: list[dict[str, Any]]) -> ChatLlm:
    answers = iter(contents)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion(next(answers)))

    model = ChatOpenAI(
        model="test-model",
        base_url="http://llm.test/v1",
        api_key=SecretStr("test"),
        max_retries=0,
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return ChatLlm(model, call_log, model_name="test-model", method="json_schema")


async def test_returns_structured_output_and_records_call() -> None:
    call_log = RecordingCallLog()
    requests: list[dict[str, Any]] = []
    llm = chat_llm(['{"text": "금융 도메인 4년"}'], call_log, requests)

    result = await llm.structured(Summary, agent="candidate-analyst", system="요약한다", user="이력서")

    assert result == Summary(text="금융 도메인 4년")
    assert [message["role"] for message in requests[0]["messages"]] == ["system", "user"]
    assert requests[0]["response_format"]["type"] == "json_schema"
    [record] = call_log.records
    assert (record.agent, record.model, record.status) == ("candidate-analyst", "test-model", "OK")
    assert (record.system, record.user, record.output) == ("요약한다", "이력서", {"text": "금융 도메인 4년"})
    assert (record.input_tokens, record.output_tokens) == (12, 5)


async def test_asks_again_when_output_does_not_match() -> None:
    call_log = RecordingCallLog()
    requests: list[dict[str, Any]] = []
    llm = chat_llm(['{"wrong": 1}', '{"text": "두 번째 답"}'], call_log, requests)

    result = await llm.structured(Summary, agent="report", system="", user="")

    assert result.text == "두 번째 답"
    assert len(requests) == 2
    assert [record.status for record in call_log.records] == ["OK"]


async def test_records_error_when_output_never_matches() -> None:
    call_log = RecordingCallLog()
    llm = chat_llm(['{"wrong": 1}', '{"wrong": 2}'], call_log, [])

    with pytest.raises(LlmOutputError):
        await llm.structured(Summary, agent="report", system="", user="")

    [record] = call_log.records
    assert record.status == "ERROR"
    assert record.error is not None and record.error.startswith("LlmOutputError")
    assert record.output is None


async def test_db_call_log_saves_record(db_session: AsyncSession) -> None:
    sessions = async_sessionmaker(bind=db_session.bind, join_transaction_mode="create_savepoint")
    record = CallRecord(
        agent="root",
        model="test-model",
        status="OK",
        system="계획한다",
        user="금융 경험 찾아줘",
        output={"intent": "FIND"},
        error=None,
        input_tokens=10,
        output_tokens=3,
        latency_ms=120,
    )

    await DbCallLog(sessions).record(record)

    saved = (await db_session.scalars(select(LlmCallLog))).one()
    assert (saved.agent, saved.status, saved.output, saved.latency_ms) == ("root", "OK", {"intent": "FIND"}, 120)
    assert saved.created_at is not None


async def test_db_call_log_failure_does_not_raise() -> None:
    engine = create_async_engine("postgresql+psycopg://hiremate:hiremate@127.0.0.1:1/hiremate")
    try:
        await DbCallLog(async_sessionmaker(engine)).record(
            CallRecord("root", "m", "OK", "", "", None, None, None, None, 0)
        )
    finally:
        await engine.dispose()


def test_get_llm_requires_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "")
    client.get_llm.cache_clear()

    with pytest.raises(client.LlmNotConfiguredError):
        client.get_llm()


def test_get_llm_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "llm_api_key", SecretStr(""))
    client.get_llm.cache_clear()

    with pytest.raises(client.LlmNotConfiguredError, match="LLM_API_KEY"):
        client.get_llm()


def test_get_llm_builds_chat_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("test"))
    client.get_llm.cache_clear()

    try:
        assert isinstance(client.get_llm(), ChatLlm)
    finally:
        client.get_llm.cache_clear()
