from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hiremate_ai.agents.generation.communication.writer import NoticeBody
from hiremate_ai.api.communication import router
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm


def notice(**overrides: Any) -> dict[str, Any]:
    """backend가 보내는 NoticeDraftContext JSON."""
    return {
        "noticeId": "3f6c1b8e-5a2d-4c7e-9b1a-2d4e6f8a0b1c",
        "templateType": "NEXT_STAGE",
        "companyName": "예시 기업",
        "recruitmentTitle": "백엔드 개발자 채용",
        "stageName": "서류 전형",
        "nextStageName": "1차 면접",
        "aiGuide": "확정 결과 · 다음 전형 정보",
        "content": "",
        **overrides,
    }


def client(llm: FakeLlm) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_llm] = lambda: llm
    return TestClient(app)


def test_write_returns_draft_from_model() -> None:
    llm = FakeLlm(NoticeBody(content="서류 전형에 합격하셨습니다."))

    response = client(llm).post("/agents/communication/write", json={"notice": notice(), "request": None})

    assert response.status_code == 200
    assert response.json() == {"reply": "초안을 만들었어요.", "content": "서류 전형에 합격하셨습니다."}
    call = llm.calls[0]
    assert call.agent == "communication"
    assert "다음 전형 안내 (합격)" in call.user
    assert "예시 기업" in call.user
    assert "다음 전형: 1차 면접" in call.user
    assert "HR 요청" not in call.user


def test_write_does_not_send_next_stage_for_rejection() -> None:
    llm = FakeLlm(NoticeBody(content="이번에는 함께하기 어렵게 되었습니다."))

    client(llm).post("/agents/communication/write", json={"notice": notice(templateType="REJECT"), "request": None})

    assert "불합격 안내" in llm.calls[0].user
    assert "1차 면접" not in llm.calls[0].user


def test_write_sends_current_content_and_request_when_revising() -> None:
    llm = FakeLlm(NoticeBody(content="고친 본문"))

    response = client(llm).post(
        "/agents/communication/write",
        json={"notice": notice(content="지금 본문입니다."), "request": "더 따뜻하게 써 줘"},
    )

    assert response.json() == {"reply": "요청하신 대로 고쳤어요.", "content": "고친 본문"}
    assert "지금 본문입니다." in llm.calls[0].user
    assert "HR 요청: 더 따뜻하게 써 줘" in llm.calls[0].user


def test_write_rejects_unknown_template_type() -> None:
    llm = FakeLlm()

    response = client(llm).post(
        "/agents/communication/write", json={"notice": notice(templateType="UNKNOWN"), "request": None}
    )

    assert response.status_code == 422
    assert llm.calls == []
