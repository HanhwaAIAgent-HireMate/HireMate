from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hiremate_ai.agents.generation.communication.checks import problems, tidy
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
    assert "서류 전형에 합격하셨음을 알려드리며" in call.user
    assert call.user.endswith("다음 전형은 1차 면접입니다.")
    assert "별도로" not in call.user


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
    assert "예시 본문" not in llm.calls[0].user


def test_write_rejects_unknown_template_type() -> None:
    llm = FakeLlm()

    response = client(llm).post(
        "/agents/communication/write", json={"notice": notice(templateType="UNKNOWN"), "request": None}
    )

    assert response.status_code == 422
    assert llm.calls == []


def test_tidy_fixes_number_and_punctuation_spacing() -> None:
    tidied = tidy(" 다음 전형은 1 차 면접입니다.일정은 11 월 3 일에 안내드리겠습니다,곧 연락드리겠습니다. ")

    assert tidied == "다음 전형은 1차 면접입니다.\n\n일정은 11월 3일에 안내드리겠습니다, 곧 연락드리겠습니다."


def test_tidy_keeps_paragraphs_and_cleans_extra_spaces_and_blank_lines() -> None:
    tidied = tidy("서류 전형에  합격하셨습니다.  \r\n\r\n\r\n  다음 전형은 1차 면접입니다.\n일정은 별도로 안내드려요.")

    assert tidied == "서류 전형에 합격하셨습니다.\n\n다음 전형은 1차 면접입니다.\n일정은 별도로 안내드려요."


def test_problems_finds_invented_evaluation_or_reason() -> None:
    found = problems("뛰어난 역량에도 경험이 부족하여 함께하기 어렵습니다.", source="쓸 내용: 결과를 알린다")

    assert found == ["주어진 정보에 없는 평가나 불합격 사유를 썼다: 뛰어난, 부족, 역량"]
    assert problems("열정에 감사드립니다.", source="HR 요청: 지원자의 열정에 감사하다고 써 줘") == []


def test_problems_finds_later_notice_promise_not_in_source() -> None:
    """다음 전형 안내와 입사 안내는 backend가 본문 아래에 붙여, 본문에 따로 안내한다고 쓰면 붙은 안내와 어긋난다."""
    found = problems("다음 전형은 1차 면접입니다. 일정은 별도로 안내드리겠습니다.", source="쓸 내용: 결과만 알린다")

    assert found == ["쓸 내용에 없는 나중 안내 약속을 썼다: 별도로 안내"]
    request = "HR 요청: 처우는 따로 안내드린다고 한 문장 넣어 줘"
    assert problems("처우는 담당자가 따로 안내드릴 예정입니다.", source=request) == []


def test_write_final_pass_leaves_onboarding_to_backend() -> None:
    llm = FakeLlm(NoticeBody(content="최종 합격을 축하드립니다."))

    client(llm).post(
        "/agents/communication/write",
        json={"notice": notice(templateType="FINAL_PASS", nextStageName=None), "request": None},
    )

    assert "입사 일정과 준비 사항은 쓰지 않는다" in llm.calls[0].user
    assert "별도로" not in llm.calls[0].user


def test_problems_passes_clean_content() -> None:
    assert problems("서류 전형에 합격하셨습니다. 다음 전형은 1차 면접입니다.", source="다음 전형: 1차 면접") == []
    assert problems("면접은 11월 3일입니다.", source="일정: 11 월 3 일") == []


def test_problems_finds_rule_violations() -> None:
    found = problems("안녕하세요. {지원자명}님, 일정과場所は 11월 3일입니다. 감사합니다.", source="다음 전형: 1차 면접")

    assert found == [
        "한국어가 아닌 문자(한자, 일본어)를 썼다: 場所は",
        "중괄호 변수를 썼다: {지원자명}",
        "인사말로 시작한다",
        "맺음말로 끝난다",
        "주어진 정보에 없는 날짜나 시각을 썼다: 11월, 3일",
    ]


def test_write_tidies_spacing_without_retry() -> None:
    llm = FakeLlm(NoticeBody(content="다음 전형은 1 차 면접입니다."))

    response = client(llm).post("/agents/communication/write", json={"notice": notice(), "request": None})

    assert response.json()["content"] == "다음 전형은 1차 면접입니다."
    assert len(llm.calls) == 1


def test_write_retries_once_with_reasons() -> None:
    llm = FakeLlm(
        NoticeBody(content="안녕하세요. 서류 전형에 합격하셨습니다."),
        NoticeBody(content="서류 전형에 합격하셨습니다."),
    )

    response = client(llm).post("/agents/communication/write", json={"notice": notice(), "request": None})

    assert response.json()["content"] == "서류 전형에 합격하셨습니다."
    assert len(llm.calls) == 2
    assert "안녕하세요.\n\n서류 전형에 합격하셨습니다." in llm.calls[1].user
    assert "인사말로 시작한다" in llm.calls[1].user


def test_write_fails_when_retry_breaks_rules_again() -> None:
    llm = FakeLlm(
        NoticeBody(content="안녕하세요. 합격입니다."), NoticeBody(content="일정과場所は 별도로 안내드립니다.")
    )

    response = client(llm).post("/agents/communication/write", json={"notice": notice(), "request": None})

    assert response.status_code == 422
    assert "한국어가 아닌 문자" in response.json()["detail"]
    assert len(llm.calls) == 2
