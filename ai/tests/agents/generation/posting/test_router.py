from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hiremate_ai.agents.generation.posting.reviser import (
    NOTHING_CHANGED_REPLY,
    ContentChanges,
    FieldChange,
    LineEdit,
    Route,
)
from hiremate_ai.agents.generation.posting.router import router
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm

CONTENT = {
    "roles": [],
    "title": "결제 플랫폼 백엔드 개발자",
    "jobCategory": "백엔드 개발",
    "employmentType": "정규직",
    "career": "경력 3년 이상",
    "location": "서울 중구",
    "intro": "카드 결제와 정산을 처리하는 플랫폼을 함께 만들 백엔드 개발자를 찾습니다.",
    "duties": ["결제 승인 · 정산 API 개발"],
    "qualifications": ["Java · Spring Boot 기반 서버 개발 경력 3년 이상"],
    "preferred": ["금융 도메인 경험"],
    "benefits": ["유연 근무"],
    "headcount": 2,
    "position": "",
    "education": "학력 무관",
    "workHours": "",
    "salary": "",
}


def body(request: str) -> dict[str, Any]:
    """backend PostingAgent.revise(posting, writingStyle, request, focus)가 보내는 JSON."""
    return {
        "posting": {
            "recruitmentId": "6f1c2b3a-4d5e-4f60-8a7b-9c0d1e2f3a4b",
            "status": "DRAFT",
            "content": CONTENT,
            "stages": [{"name": "서류 전형", "type": "DOCUMENT"}],
            "requiredExtras": [],
        },
        "writingStyle": "",
        "request": request,
        "focus": None,
    }


def client(llm: FakeLlm) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_llm] = lambda: llm
    return TestClient(app)


def test_revise_returns_backend_result_shape() -> None:
    llm = FakeLlm(
        Route(targets=["CONTENT"], question=None, writes_posting=False),
        ContentChanges(
            changes=[
                FieldChange(field="우대 사항", text=None, items=["금융 도메인 경험", "결제 · 정산 시스템 운영 경험"])
            ]
        ),
    )

    response = client(llm).post("/agents/posting/revise", json=body("우대 사항에 결제 · 정산 경험 추가해 줘"))

    assert response.status_code == 200
    assert response.json() == {
        "reply": "우대 사항 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요.",
        "suggestion": {
            "content": {**CONTENT, "preferred": ["금융 도메인 경험", "결제 · 정산 시스템 운영 경험"]},
            "stages": None,
            "requiredExtras": None,
            "changedFields": ["preferred"],
        },
    }


def test_revise_changes_only_the_line_hr_picked() -> None:
    llm = FakeLlm(LineEdit(action="REWRITE", text="카드 결제 · 정산 도메인 경험"))
    request = {**body("결제 쪽으로 구체적으로"), "focus": {"field": "preferred", "index": 0}}

    response = client(llm).post("/agents/posting/revise", json=request)

    assert response.status_code == 200
    assert response.json()["suggestion"] == {
        "content": {**CONTENT, "preferred": ["카드 결제 · 정산 도메인 경험"]},
        "stages": None,
        "requiredExtras": None,
        "changedFields": ["preferred"],
    }
    assert [call.output for call in llm.calls] == [LineEdit]


def test_revise_returns_null_suggestion_when_nothing_changes() -> None:
    llm = FakeLlm(Route(targets=[], question=None, writes_posting=False))

    response = client(llm).post("/agents/posting/revise", json=body("음"))

    assert response.json() == {"reply": NOTHING_CHANGED_REPLY, "suggestion": None}


def test_revise_rejects_unknown_status() -> None:
    llm = FakeLlm()
    request = body("우대 사항 고쳐 줘")
    request["posting"]["status"] = "UNKNOWN"

    response = client(llm).post("/agents/posting/revise", json=request)

    assert response.status_code == 422
    assert llm.calls == []
