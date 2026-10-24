import json
from typing import Any

import httpx
import pytest
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hiremate_ai.config import settings
from hiremate_ai.db.llm_call import LlmCallLog
from hiremate_ai.llm import client
from hiremate_ai.llm.call_log import CallRecord, DbCallLog
from hiremate_ai.llm.chat import LAST_CALL, SHORTER, ChatLlm, LlmOutputError


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


def tool_completion(*calls: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    body = completion("")
    body["choices"][0]["message"] = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
            for i, (name, args) in enumerate(calls)
        ],
    }
    body["choices"][0]["finish_reason"] = "tool_calls"
    return body


def chat_llm(
    contents: list[str | dict[str, Any]],
    call_log: RecordingCallLog,
    requests: list[dict[str, Any]],
    *,
    max_calls: int = 8,
    max_tokens: int | None = None,
) -> ChatLlm:
    """contents의 글은 모델 답 본문, dict는 응답 전체(tool_completion)다."""
    answers = iter(contents)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        answer = next(answers)
        return httpx.Response(200, json=answer if isinstance(answer, dict) else completion(answer))

    model = ChatOpenAI(
        model="test-model",
        base_url="http://llm.test/v1",
        api_key=SecretStr("test"),
        max_retries=0,
        max_tokens=max_tokens,
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return ChatLlm(model, call_log, model_name="test-model", method="json_schema", agent_max_calls=max_calls)


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


def cut(body: dict[str, Any]) -> dict[str, Any]:
    """출력 길이 상한(max_tokens)에서 끊긴 응답."""
    body["choices"][0]["finish_reason"] = "length"
    return body


async def test_asks_shorter_when_output_is_cut() -> None:
    call_log = RecordingCallLog()
    requests: list[dict[str, Any]] = []
    llm = chat_llm([cut(completion('{"text": "같은 문장을 되풀이')), '{"text": "짧은 답"}'], call_log, requests)

    result = await llm.structured(Summary, agent="root", system="", user="정리해")

    assert result.text == "짧은 답"
    assert requests[0]["messages"][1]["content"] == "정리해"
    assert SHORTER in requests[1]["messages"][1]["content"]
    assert [record.status for record in call_log.records] == ["OK"]


def at_limit(body: dict[str, Any], limit: int) -> dict[str, Any]:
    """출력 토큰이 상한에 닿았는데 finish_reason은 그대로인 응답. 어떤 처리 업체는 잘린 JSON을 닫아 돌려준다."""
    body["usage"]["completion_tokens"] = limit
    return body


async def test_output_at_token_limit_counts_as_cut() -> None:
    requests: list[dict[str, Any]] = []
    llm = chat_llm(
        [at_limit(completion('{"text": "되풀이하다 닫힌 글"}'), 50), '{"text": "짧은 답"}'],
        RecordingCallLog(),
        requests,
        max_tokens=50,
    )

    result = await llm.structured(Summary, agent="root", system="", user="정리해")

    assert result.text == "짧은 답"
    assert SHORTER in requests[1]["messages"][1]["content"]


async def test_fails_with_output_error_when_output_stays_cut() -> None:
    call_log = RecordingCallLog()
    llm = chat_llm([cut(completion('{"text": "끊')), cut(completion('{"text": "또 끊'))], call_log, [])

    with pytest.raises(LlmOutputError, match="잘렸다"):
        await llm.structured(Summary, agent="root", system="", user="")

    [record] = call_log.records
    assert record.status == "ERROR"


@tool
async def career(item: str) -> str:
    """지원자 프로필에서 항목 하나를 찾는다."""
    return f"{item}: 결제 시스템 4년"


async def test_tool_agent_records_each_model_call() -> None:
    call_log = RecordingCallLog()
    requests: list[dict[str, Any]] = []
    llm = chat_llm(
        [tool_completion(("career", {"item": "경력"})), tool_completion(("Summary", {"text": "경력 4년"}))],
        call_log,
        requests,
    )

    result = await llm.tool_agent(Summary, agent="root", system="분석한다", tools=[career]).run("@김지원 경력")

    assert result == Summary(text="경력 4년")
    assert [tool["function"]["name"] for tool in requests[0]["tools"]] == ["career", "Summary"]
    assert requests[0]["tool_choice"] == "required"
    first, second = call_log.records
    assert (first.agent, first.status, first.user) == ("root", "OK", "[human] @김지원 경력")
    assert first.system.startswith("분석한다\n\n")
    assert first.output == {"content": "", "tool_calls": [{"name": "career", "args": {"item": "경력"}}]}
    assert (first.input_tokens, first.output_tokens) == (12, 5)
    assert '[tool career] <data kind="tool" name="career">' in second.user


async def test_tool_agent_asks_shorter_when_answer_is_cut() -> None:
    call_log = RecordingCallLog()
    requests: list[dict[str, Any]] = []
    llm = chat_llm(
        [
            cut(tool_completion(("Summary", {"text": "같은 문장 같은 문장 같은"}))),
            tool_completion(("Summary", {"text": "짧게"})),
        ],
        call_log,
        requests,
    )

    result = await llm.tool_agent(Summary, agent="root", system="", tools=[career]).run("경력")

    assert result == Summary(text="짧게")
    assert requests[1]["messages"][-1] == {"role": "user", "content": SHORTER}
    assert len(call_log.records) == 2


async def test_tool_agent_answer_at_token_limit_counts_as_cut() -> None:
    requests: list[dict[str, Any]] = []
    llm = chat_llm(
        [
            at_limit(tool_completion(("Summary", {"text": "항목이 잘려 나간 답"})), 50),
            tool_completion(("Summary", {"text": "짧게"})),
        ],
        RecordingCallLog(),
        requests,
        max_tokens=50,
    )

    result = await llm.tool_agent(Summary, agent="root", system="", tools=[career]).run("경력")

    assert result == Summary(text="짧게")
    assert requests[1]["messages"][-1] == {"role": "user", "content": SHORTER}


async def test_tool_agent_fails_when_answer_stays_cut() -> None:
    cut_answer = tool_completion(("Summary", {"text": "끊"}))
    llm = chat_llm([cut(cut_answer), cut(json.loads(json.dumps(cut_answer)))], RecordingCallLog(), [])

    with pytest.raises(LlmOutputError, match="잘렸다"):
        await llm.tool_agent(Summary, agent="root", system="", tools=[career]).run("경력")


async def test_tool_agent_last_call_can_only_answer() -> None:
    """호출 상한의 마지막 호출에서는 도구를 빼고 최종 답만 내게 한다. 자료를 더 읽다 상한을 넘기지 않게 한다."""
    requests: list[dict[str, Any]] = []
    llm = chat_llm(
        [tool_completion(("career", {"item": "경력"})), tool_completion(("Summary", {"text": "확인한 만큼 답"}))],
        RecordingCallLog(),
        requests,
        max_calls=2,
    )

    result = await llm.tool_agent(Summary, agent="root", system="", tools=[career]).run("경력")

    assert result.text == "확인한 만큼 답"
    assert [tool["function"]["name"] for tool in requests[0]["tools"]] == ["career", "Summary"]
    assert [tool["function"]["name"] for tool in requests[1]["tools"]] == ["Summary"]
    assert requests[1]["messages"][-1] == {"role": "user", "content": LAST_CALL}


async def test_repeated_read_batch_switches_to_final_answer_before_limit() -> None:
    requests: list[dict[str, Any]] = []
    call_log = RecordingCallLog()
    llm = chat_llm(
        [
            tool_completion(("career", {"item": "경력"})),
            tool_completion(("career", {"item": "경력"})),
            tool_completion(("Summary", {"text": "이미 확인한 경력 4년"})),
        ],
        call_log,
        requests,
    )

    result = await llm.tool_agent(Summary, agent="root", system="", tools=[career]).run("경력")

    assert result.text == "이미 확인한 경력 4년"
    assert [tool["function"]["name"] for tool in requests[-1]["tools"]] == ["Summary"]
    assert "기존 조회 결과" in requests[-1]["messages"][-1]["content"]
    assert len(call_log.records) == 3


async def test_mixed_batch_keeps_unread_tools_available() -> None:
    requests: list[dict[str, Any]] = []
    llm = chat_llm(
        [
            tool_completion(("career", {"item": "경력"})),
            tool_completion(("career", {"item": "경력"}), ("career", {"item": "프로젝트"})),
            tool_completion(("Summary", {"text": "경력과 프로젝트"})),
        ],
        RecordingCallLog(),
        requests,
    )

    result = await llm.tool_agent(Summary, agent="root", system="", tools=[career]).run("경력과 프로젝트")

    assert result.text == "경력과 프로젝트"
    assert [tool["function"]["name"] for tool in requests[-1]["tools"]] == ["career", "Summary"]


async def test_repeated_reads_stay_closed_during_format_repair() -> None:
    requests: list[dict[str, Any]] = []
    llm = chat_llm(
        [
            tool_completion(("career", {"item": "경력"})),
            tool_completion(("career", {"item": "경력"})),
            tool_completion(("Summary", {"wrong": "잘못된 형식"})),
            tool_completion(("Summary", {"text": "형식을 고친 답"})),
        ],
        RecordingCallLog(),
        requests,
    )

    result = await llm.tool_agent(Summary, agent="root", system="", tools=[career]).run("경력")

    assert result.text == "형식을 고친 답"
    assert [tool["function"]["name"] for tool in requests[-1]["tools"]] == ["Summary"]


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


def test_build_llm_uses_given_call_log(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("test"))
    log = RecordingCallLog()

    llm = client.build_llm(log)

    assert isinstance(llm, ChatLlm)
    assert llm._call_log is log


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


@pytest.mark.parametrize("effort", [None, "none", "low"])
def test_get_llm_builds_chat_llm(monkeypatch: pytest.MonkeyPatch, effort: str | None) -> None:
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("test"))
    monkeypatch.setattr(settings, "llm_max_tokens", 512)
    monkeypatch.setattr(settings, "llm_temperature", 0.3)
    monkeypatch.setattr(settings, "llm_reasoning_effort", effort)
    monkeypatch.setattr(settings, "llm_providers", "")
    client.get_llm.cache_clear()

    try:
        llm = client.get_llm()
        assert isinstance(llm, ChatLlm)
        model = llm._model
        assert isinstance(model, ChatOpenAI)
        assert model.max_tokens == 512
        assert model.temperature == 0.3
        assert model.reasoning_effort == effort
        assert model.extra_body is None
    finally:
        client.get_llm.cache_clear()


def test_get_llm_limits_openrouter_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("test"))
    monkeypatch.setattr(settings, "llm_providers", "baidu, coreweave")
    client.get_llm.cache_clear()

    try:
        llm = client.get_llm()
        assert isinstance(llm, ChatLlm)
        assert isinstance(llm._model, ChatOpenAI)
        assert llm._model.extra_body == {"provider": {"only": ["baidu", "coreweave"]}}
    finally:
        client.get_llm.cache_clear()
