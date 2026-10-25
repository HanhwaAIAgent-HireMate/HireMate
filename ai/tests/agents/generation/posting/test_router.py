from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hiremate_ai.agents.generation.posting.criteria import RuleDraft
from hiremate_ai.agents.generation.posting.important import ImportantPicks, Pick
from hiremate_ai.agents.generation.posting.reviser import NOTHING_CHANGED_REPLY, ContentChanges, FieldChange, Route
from hiremate_ai.agents.generation.posting.router import router
from hiremate_ai.contract import CriterionType
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm

CONTENT = {
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
}


def body(request: str) -> dict[str, Any]:
    """backend PostingAgent.revise(posting, writingStyle, request)가 보내는 JSON."""
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
    }


def client(llm: FakeLlm) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_llm] = lambda: llm
    return TestClient(app)


def test_revise_returns_backend_result_shape() -> None:
    llm = FakeLlm(
        Route(targets=["CONTENT"], question=None),
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


def test_revise_returns_null_suggestion_when_nothing_changes() -> None:
    llm = FakeLlm(Route(targets=[], question=None))

    response = client(llm).post("/agents/posting/revise", json=body("음"))

    assert response.json() == {"reply": NOTHING_CHANGED_REPLY, "suggestion": None}


def test_revise_rejects_unknown_status() -> None:
    llm = FakeLlm()
    request = body("우대 사항 고쳐 줘")
    request["posting"]["status"] = "UNKNOWN"

    response = client(llm).post("/agents/posting/revise", json=request)

    assert response.status_code == 422
    assert llm.calls == []


def test_draft_criterion_takes_backend_parameters_and_returns_draft_shape() -> None:
    """backend PostingCriteriaAgent.draftCriterion(posting, category, text, ncsUnitCode)가 보내는 JSON."""
    llm = FakeLlm(
        RuleDraft(
            criterion_type=CriterionType.CONDITION,
            met="Java 서버 개발 재직 경력이 3년 이상이다.",
            partial=None,
            unmet="Java 서버 개발 경력이 서류에서 확인되지 않는다.",
            certificates=[],
        )
    )

    response = client(llm).post(
        "/agents/posting/draftCriterion",
        json={
            "posting": CONTENT,
            "category": "QUALIFICATION",
            "text": "Java · Spring Boot 기반 서버 개발 경력 3년 이상",
            "ncsUnitCode": None,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "criterionType": "CONDITION",
        "met": "Java 서버 개발 재직 경력이 3년 이상이다.",
        "partial": None,
        "unmet": "Java 서버 개발 경력이 서류에서 확인되지 않는다.",
        "certificates": [],
    }


def test_recommend_important_reads_lists_from_the_posting() -> None:
    """backend PostingCriteriaAgent.recommendImportant(posting). 한 항목 목록은 묻지 않는다."""
    content = {**CONTENT, "qualifications": ["Java 서버 개발 경력", "SQL 작성 경험", "Git 협업 경험"]}
    llm = FakeLlm(ImportantPicks(picks=[Pick(item=1, duty=1)]))

    response = client(llm).post("/agents/posting/recommendImportant", json={"posting": content})

    assert response.json() == {
        "qualifications": [{"index": 0, "duty": "결제 승인 · 정산 API 개발"}],
        "preferred": [],
    }
    assert len(llm.calls) == 1
