import json
from pathlib import Path

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from hiremate_ai.agents.root.memory import get_saver
from hiremate_ai.agents.root.route import RootRoute
from hiremate_ai.agents.root.types import EditAction
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.main import app

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contract"


def test_plan_endpoint_round_trip() -> None:
    context = json.loads((CONTRACT_DIR / "ChatContext.json").read_text(encoding="utf-8"))
    app.dependency_overrides[get_llm] = lambda: FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR))
    app.dependency_overrides[get_saver] = lambda: InMemorySaver()
    try:
        response = TestClient(app).post("/agents/root/plan", json={"context": context})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert (body["intent"], body["edit"]) == ("EDIT", "CLEAR")
    assert body["questionTargets"] == []


def plan_request(context: dict[str, object], message: str) -> dict[str, object]:
    return {"context": {**context, "message": message}}


def test_plan_history_and_forget_use_thread() -> None:
    context = json.loads((CONTRACT_DIR / "ChatContext.json").read_text(encoding="utf-8"))
    saver = InMemorySaver()
    llm = FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR), RootRoute(kind="EDIT", edit=EditAction.RESTORE))
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_saver] = lambda: saver
    client = TestClient(app)
    try:
        client.post("/agents/root/plan", json=plan_request(context, "비워줘"))
        client.post("/agents/root/plan", json=plan_request(context, "되돌려줘"))
        history = client.post("/agents/root/history", json={"threadId": context["threadId"]})
        other = client.post("/agents/root/history", json={"threadId": "다른 대화방"})
        forgotten = client.post("/agents/root/forget", json={"threadId": context["threadId"]})
        after = client.post("/agents/root/history", json={"threadId": context["threadId"]})
    finally:
        app.dependency_overrides.clear()

    assert "앞 대화" in llm.calls[1].user
    turns = history.json()
    assert [turn["message"] for turn in turns] == ["비워줘", "되돌려줘"]
    assert turns[1]["plan"]["edit"] == "RESTORE"
    assert turns[0]["total"] == 2
    assert other.json() == []
    assert forgotten.json() == {"deleted": 1}
    assert after.json() == []


def test_forget_stage_endpoint() -> None:
    context = json.loads((CONTRACT_DIR / "ChatContext.json").read_text(encoding="utf-8"))
    saver = InMemorySaver()
    app.dependency_overrides[get_llm] = lambda: FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR))
    app.dependency_overrides[get_saver] = lambda: saver
    client = TestClient(app)
    try:
        client.post("/agents/root/plan", json=plan_request(context, "비워줘"))
        removed = client.post("/agents/root/forgetStage", json={"stageId": context["stageId"]})
        history = client.post("/agents/root/history", json={"threadId": context["threadId"]})
    finally:
        app.dependency_overrides.clear()

    assert removed.json() == {"deleted": 1}
    assert history.json() == []
