import json
from pathlib import Path

from fastapi.testclient import TestClient

from hiremate_ai.agents.root.route import RootRoute
from hiremate_ai.agents.root.types import EditAction
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.main import app

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contract"


def test_plan_endpoint_round_trip() -> None:
    context = json.loads((CONTRACT_DIR / "ChatContext.json").read_text(encoding="utf-8"))
    app.dependency_overrides[get_llm] = lambda: FakeLlm(RootRoute(kind="EDIT", edit=EditAction.CLEAR))
    try:
        response = TestClient(app).post("/agents/root/plan", json={"context": context})
    finally:
        app.dependency_overrides.pop(get_llm, None)

    assert response.status_code == 200
    body = response.json()
    assert (body["intent"], body["edit"]) == ("EDIT", "CLEAR")
    assert body["questionTargets"] == []
