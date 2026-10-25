import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import Client, get_current_run_tree
from pydantic import SecretStr

from hiremate_ai.agents.root.memory import get_saver
from hiremate_ai.agents.root.route import RootRoute
from hiremate_ai.agents.root.types import EditAction
from hiremate_ai.config import settings
from hiremate_ai.llm import tracing
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.llm.tracing import TracingNotConfiguredError, traced
from hiremate_ai.main import app

CONTRACT_DIR = Path(__file__).resolve().parents[3] / "contract"


def runs(client: MagicMock, method: str) -> list[Mapping[str, Any]]:
    """클라이언트가 받은 create_run · update_run 호출의 인자. 맨 위 기록에는 parent_run_id가 없다."""
    return [call.kwargs for call in client.mock_calls if call[0] == method]


def test_off_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock(spec=Client)
    monkeypatch.setattr(tracing, "_client", lambda: client)

    with traced("/agents/report/write"):
        assert get_current_run_tree() is None
        RunnableLambda(lambda text: text).invoke("리포트")

    assert client.mock_calls == []


def test_groups_langchain_runs_into_one_trace(langsmith: MagicMock) -> None:
    with traced("report/write"):
        RunnableLambda(lambda text: text).invoke("리포트")

    created = runs(langsmith, "create_run")
    assert [run["name"] for run in created] == ["report/write", "RunnableLambda"]
    root, child = created
    assert root.get("parent_run_id") is None
    assert child["parent_run_id"] == root["id"]
    assert child["trace_id"] == root["id"]


def test_without_name_each_langchain_run_is_a_trace(langsmith: MagicMock) -> None:
    with traced():
        RunnableLambda(lambda text: text).invoke("하나")
        RunnableLambda(lambda text: text).invoke("둘")

    created = runs(langsmith, "create_run")
    assert len(created) == 2
    assert all(run.get("parent_run_id") is None for run in created)
    assert created[0]["trace_id"] != created[1]["trace_id"]


def test_sse_request_is_one_trace_closed_after_stream(langsmith: MagicMock) -> None:
    context = json.loads((CONTRACT_DIR / "ChatContext.json").read_text(encoding="utf-8"))
    app.dependency_overrides[get_llm] = lambda: FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR))
    app.dependency_overrides[get_saver] = lambda: InMemorySaver()
    try:
        response = TestClient(app).post("/agents/root/plan", json={"context": context})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    created = runs(langsmith, "create_run")
    root = created[0]
    assert (root["name"], root.get("parent_run_id")) == ("/agents/root/plan", None)
    assert "LangGraph" in [run["name"] for run in created]
    assert all(run["trace_id"] == root["id"] for run in created)
    # 기록은 그래프가 끝나고 SSE 스트림을 다 보낸 뒤에 닫힌다
    assert runs(langsmith, "update_run")[-1]["run_id"] == root["id"]


def test_routes_without_model_send_nothing(langsmith: MagicMock) -> None:
    # 모델을 부르지 않는 경로는 LlmDep을 받지 않아 빈 기록이 쌓이지 않는다
    app.dependency_overrides[get_saver] = lambda: InMemorySaver()
    try:
        response = TestClient(app).post("/agents/root/history", json={"threadId": "대화방"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert langsmith.mock_calls == []


def test_on_without_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "langsmith_tracing", True)
    monkeypatch.setattr(settings, "langsmith_api_key", SecretStr(""))
    tracing._client.cache_clear()

    with pytest.raises(TracingNotConfiguredError, match="LANGSMITH_API_KEY"), traced("report/write"):
        pass
