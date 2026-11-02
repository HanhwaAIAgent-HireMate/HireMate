from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hiremate_ai.agents.generation.posting.poster import (
    PosterContext,
    PosterDesign,
    PosterEdits,
    PosterRecommendation,
)
from hiremate_ai.agents.generation.posting.poster_chat import PosterChatReply
from hiremate_ai.agents.generation.posting.reviser import (
    NOTHING_CHANGED_REPLY,
    ContentChanges,
    FieldChange,
    LineEdit,
    Route,
)
from hiremate_ai.agents.generation.posting.router import router
from hiremate_ai.contract import CompanyProfile, PostingContent
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm, ToolCall

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


def test_design_keeps_existing_endpoint_and_runs_inside_posting_agent(sample_company: CompanyProfile) -> None:
    design = PosterDesign(
        template="CLASSIC",
        mood="TRUST",
        color="#2459a6",
        decoration=1,
        enabled=True,
        show_logo=False,
        logo_file_id=None,
    )
    llm = FakeLlm(
        ToolCall("consult_posting_designer", {"request": "더 고급스럽게"}),
        PosterEdits(
            scope="DESIGN",
            reply="디자인 수정안이에요.",
            recommendations=[
                PosterRecommendation(design=design.model_copy(update={"mood": "PREMIUM"}), reason="차분한 분위기"),
            ],
        ),
        PosterChatReply(kind="DESIGN", reply="수정안을 확인해 주세요.", result=1),
    )
    context = PosterContext(
        company=sample_company,
        posting=PostingContent.model_validate(CONTENT),
        design=design,
        brand_color=None,
    )
    response = client(llm).post(
        "/agents/posting/design",
        json={
            "context": context.model_dump(mode="json"),
            "request": "더 고급스럽게",
        },
    )
    assert response.status_code == 200
    assert response.json()["recommendations"][0]["design"]["mood"] == "PREMIUM"
    assert [call.agent for call in llm.calls] == ["posting", "posting", "posting"]


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


def test_design_conversation_keeps_posting_path(sample_company: CompanyProfile) -> None:
    context = PosterContext(
        company=sample_company, posting=PostingContent.model_validate(CONTENT), design=None, brand_color=None
    )
    llm = FakeLlm(PosterChatReply(kind="CONVERSATION", reply="원하는 분위기를 알려 주세요.", result=None))
    response = client(llm).post(
        "/agents/posting/design",
        json={"context": context.model_dump(mode="json", by_alias=True), "request": "디자인은 어떻게 바꿔?"},
    )
    assert response.status_code == 200
    assert response.json() == {"reply": "원하는 분위기를 알려 주세요.", "recommendations": []}
