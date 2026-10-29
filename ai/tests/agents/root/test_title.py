from fastapi.testclient import TestClient

from hiremate_ai.agents.guardrails import BLOCKED_REPLY
from hiremate_ai.agents.root.title import TabTitle, make_title
from hiremate_ai.llm.chat import LlmFailureReason, LlmOutputError
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm, LlmCall
from hiremate_ai.main import app


async def test_title_summarizes_first_question_and_answer() -> None:
    llm = FakeLlm(TabTitle(title="  금융 도메인 경험자 찾기. "))

    title = await make_title(llm, "금융 도메인 경험이 있는 지원자 찾아줘", "조건에 맞는 3명을 선택했어요.")

    assert title == "금융 도메인 경험자 찾기"
    assert "금융 도메인 경험이 있는 지원자 찾아줘" in llm.calls[0].user
    assert "조건에 맞는 3명을 선택했어요." in llm.calls[0].user


async def test_blocked_question_gets_no_title_without_calling_the_model() -> None:
    llm = FakeLlm()

    assert await make_title(llm, "30살 이하 남자 지원자 찾아줘", BLOCKED_REPLY) is None
    assert llm.calls == []


async def test_long_title_is_cut_to_thirty_characters() -> None:
    assert await make_title(FakeLlm(TabTitle(title="가" * 40)), "질문", "답") == "가" * 30


async def test_model_failure_gives_no_title() -> None:
    def fail(call: LlmCall) -> TabTitle:
        raise LlmOutputError("형식이 맞지 않는다", reason=LlmFailureReason.FORMAT)

    assert await make_title(FakeLlm(fail), "질문", "답") is None


async def test_title_with_blocked_attribute_is_dropped() -> None:
    assert await make_title(FakeLlm(TabTitle(title="남자 개발자 찾기")), "백엔드 개발자 찾아줘", "답") is None


def test_title_endpoint() -> None:
    app.dependency_overrides[get_llm] = lambda: FakeLlm(TabTitle(title="경력 10년 이상 비교"))
    try:
        response = TestClient(app).post(
            "/agents/root/title", json={"message": "경력 10년 넘는 사람 비교해줘", "reply": "2명이에요."}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.json() == {"title": "경력 10년 이상 비교"}
