import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from ncs_context import UNIT, FakeNcs

from hiremate_ai.agents.generation.posting.ncs import (
    NCS_HEADER,
    LineCitation,
    NcsQuery,
    SupportReview,
    SupportVerdict,
)
from hiremate_ai.agents.generation.posting.poster import (
    PosterContext,
    PosterDesign,
    PosterEdits,
    PosterRecommendation,
)
from hiremate_ai.agents.generation.posting.poster_chat import PosterChatReply
from hiremate_ai.agents.generation.posting.reviser import (
    NOTHING_CHANGED_REPLY,
    CitedContentChanges,
    ContentChanges,
    FieldChange,
    LineEdit,
    Route,
)
from hiremate_ai.agents.generation.posting.router import router
from hiremate_ai.contract import CompanyProfile, PostingContent
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm, ToolCall
from hiremate_ai.ncs_search.reference import get_ncs

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
    """/revise 응답의 마지막 done 이벤트 data (RevisionResult JSON)."""
    name, data = sse_events(response.text)[-1]
    assert name == "done"
    return data


def client(llm: FakeLlm, ncs: FakeNcs | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_ncs] = lambda: ncs or FakeNcs(unit_list=[])
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
        Route(targets=["CONTENT"], question=None, writes_posting=False, ncs="SKIP"),
        ContentChanges(
            changes=[
                FieldChange(field="우대 사항", text=None, items=["금융 도메인 경험", "결제 · 정산 시스템 운영 경험"])
            ]
        ),
    )

    response = client(llm).post("/agents/posting/revise", json=body("우대 사항에 결제 · 정산 경험 추가해 줘"))
    events = sse_events(response.text)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert events[:-1] == [
        ("status", {"text": "요청을 확인하고 있어요", "depth": 0}),
        ("status", {"text": "수정안을 쓰고 있어요", "depth": 0}),
    ]
    assert done_of(response) == {
        "reply": "우대 사항 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요.",
        "suggestion": {
            "content": {**CONTENT, "preferred": ["금융 도메인 경험", "결제 · 정산 시스템 운영 경험"]},
            "stages": None,
            "requiredExtras": None,
            "changedFields": ["preferred"],
        },
    }


def test_revise_passes_ncs_dependency() -> None:
    duty = "주문 · 결제 서버 프로그램 구현"
    llm = FakeLlm(
        Route(targets=["CONTENT"], question=None, writes_posting=False, ncs="REQUESTED"),
        NcsQuery(tasks=["서버 프로그램을 구현 한다"], units=[UNIT]),
        CitedContentChanges(
            changes=[FieldChange(field="주요 업무", text=None, items=["결제 승인 · 정산 API 개발", duty])],
            citations=[LineCitation(field="주요 업무", line=duty, sources=["S1"])],
        ),
        SupportReview(verdicts=[SupportVerdict(index=0, verdict="supports")]),
    )

    response = client(llm, FakeNcs()).post("/agents/posting/revise", json=body("NCS 참고해서 주요 업무 추가해 줘"))

    assert response.status_code == 200
    assert f"\n\n{NCS_HEADER}\n주요 업무 2번 ← " in done_of(response)["reply"]


def test_revise_changes_only_the_line_hr_picked() -> None:
    llm = FakeLlm(LineEdit(action="REWRITE", text="카드 결제 · 정산 도메인 경험"))
    request = {**body("결제 쪽으로 구체적으로"), "focus": {"field": "preferred", "index": 0}}

    response = client(llm).post("/agents/posting/revise", json=request)

    assert response.status_code == 200
    assert done_of(response)["suggestion"] == {
        "content": {**CONTENT, "preferred": ["카드 결제 · 정산 도메인 경험"]},
        "stages": None,
        "requiredExtras": None,
        "changedFields": ["preferred"],
    }
    assert [call.output for call in llm.calls] == [LineEdit]


def test_revise_returns_null_suggestion_when_nothing_changes() -> None:
    llm = FakeLlm(Route(targets=[], question=None, writes_posting=False, ncs="SKIP"))

    response = client(llm).post("/agents/posting/revise", json=body("음"))

    assert done_of(response) == {"reply": NOTHING_CHANGED_REPLY, "suggestion": None}


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
