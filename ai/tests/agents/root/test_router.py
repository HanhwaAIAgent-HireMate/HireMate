import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from hiremate_ai.agents.root.answer import AnswerItem, CandidateNotes, MultiSummary
from hiremate_ai.agents.root.memory import get_saver
from hiremate_ai.agents.root.route import RootRoute
from hiremate_ai.agents.root.toolkit import default_toolkit, get_toolkit
from hiremate_ai.agents.root.types import EditAction
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.main import app

CONTRACT_DIR = Path(__file__).resolve().parents[4] / "contract"


def test_plan_endpoint_round_trip() -> None:
    context = json.loads((CONTRACT_DIR / "ChatContext.json").read_text(encoding="utf-8"))
    app.dependency_overrides[get_llm] = lambda: FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR))
    app.dependency_overrides[get_saver] = lambda: InMemorySaver()
    try:
        response = TestClient(app).post("/agents/root/plan", json={"context": context})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = sse_events(response.text)
    assert [name for name, _ in events] == ["status", "status", "done"]
    assert events[0][1] == {"text": "요청을 확인하고 있어요"}
    body = events[-1][1]
    assert (body["intent"], body["edit"]) == ("EDIT", "CLEAR")
    assert body["questionTargets"] == []


def sse_events(text: str) -> list[tuple[str, Any]]:
    """SSE 본문을 (이벤트 이름, data JSON)으로 읽는다. 주석(: ...)과 이름 없는 이벤트는 건너뛴다."""
    events: list[tuple[str, Any]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        fields = [line.split(":", 1) for line in block.split("\n") if line and not line.startswith(":")]
        named = {key: value.strip() for key, value in fields}
        if "event" in named:
            events.append((named["event"], json.loads(named["data"])))
    return events


def done_of(response: Any) -> Any:
    """/plan 응답의 마지막 done 이벤트 data (ChatPlan JSON)."""
    name, data = sse_events(response.text)[-1]
    assert name == "done"
    return data


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


def test_plan_without_thread_does_not_remember() -> None:
    context = json.loads((CONTRACT_DIR / "ChatContext.json").read_text(encoding="utf-8"))
    saver = InMemorySaver()
    app.dependency_overrides[get_llm] = lambda: FakeLlm(
        RootRoute(kind="ANSWER"),
        CandidateNotes(items=[AnswerItem(label="확인할 점", text="세부 근거는 추가 확인이 필요해요.", status="CHECK")]),
        MultiSummary(message="요약이에요."),
    )
    app.dependency_overrides[get_saver] = lambda: saver
    # 대상이 있는 분석은 지원자 자료를 모아 정리한다. DB 없이 문서로 모은다
    app.dependency_overrides[get_toolkit] = default_toolkit
    try:
        response = TestClient(app).post("/agents/root/plan", json={"context": {**context, "threadId": ""}})
    finally:
        app.dependency_overrides.clear()

    assert done_of(response)["message"] == "요약이에요."
    assert saver.storage == {}
