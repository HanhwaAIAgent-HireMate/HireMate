from typing import Any
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.interview import InterviewAnalysisInput, InterviewReference, analyze_interview
from hiremate_ai.agents.analysis.interview.types import FindingDraft, InterviewDraft
from hiremate_ai.db.profile import CandidateProfile, ItemAgent, ItemCategory, ProfileStatus
from hiremate_ai.db.profile_store import NewItem, save_profile
from hiremate_ai.db.session import get_session
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm, LlmCall
from hiremate_ai.llm.prompt import UNTRUSTED_RULE
from hiremate_ai.main import app

ROLE = '"결제 승인 API 응답 시간을 180ms에서 90ms로 줄인 일"에서 본인이 맡은 역할을 말해 주세요.'
ROLE_ANSWER = (
    "승인 API의 DB 조회를 캐시로 바꾸는 작업을 직접 설계했습니다. "
    "부하 테스트로 응답 시간이 180ms에서 90ms로 줄어든 것을 확인했습니다."
)
TEST = "장애 상황을 재현하는 테스트를 어떻게 작성했나요?"
TEST_ANSWER = "테스트는 다른 팀원이 주로 맡아서 자세히는 모릅니다."
CAREER = "결제 시스템 경력 5년 중 정산 업무는 얼마나 맡았나요?"

# backend InterviewAnalysisListener가 보내는 모양 그대로. 가상 지원자 정유민의 1차 면접 기록
INPUT_JSON: dict[str, Any] = {
    "companyId": "3c1f5e2a-7b4d-4e8a-9f60-1a2b3c4d5e6f",
    "recruitmentId": "7a1e2b3c-4d5e-4f60-8a9b-0c1d2e3f4a51",
    "stageId": "6e3d9a2f-4b5c-4d7e-9f01-2a3b4c5d6e7f",
    "applicationId": "8fc0c84b-e27b-508c-8797-64fd232e1b4c",
    "stageName": "1차 면접",
    "questions": [
        {"text": ROLE, "answer": ROLE_ANSWER},
        {"text": TEST, "answer": TEST_ANSWER},
        {"text": CAREER, "answer": ""},
    ],
    "previous": [],
}


def interview_input(**overrides: Any) -> InterviewAnalysisInput:
    return InterviewAnalysisInput.model_validate({**INPUT_JSON, **overrides})


def confirmed() -> FindingDraft:
    return FindingDraft(
        kind="CONFIRMED",
        content="승인 API 응답 시간을 180ms에서 90ms로 줄인 작업을 직접 설계했다고 확인했다.",
        evidence="승인 API의 DB 조회를 캐시로 바꾸는 작업을 직접 설계했습니다.",
    )


def unconfirmed() -> FindingDraft:
    return FindingDraft(
        kind="UNCONFIRMED",
        content="장애 재현 테스트 경험은 아직 확인되지 않았다.",
        evidence="테스트는 다른 팀원이 주로 맡아서 자세히는 모릅니다.",
    )


def from_question() -> FindingDraft:
    return FindingDraft(
        kind="CONFIRMED",
        content="장애 재현 테스트를 작성했다.",
        evidence="장애 상황을 재현하는 테스트를 어떻게 작성했나요?",
    )


async def test_confirmed_and_unconfirmed_points_keep_answer_evidence() -> None:
    llm = FakeLlm(InterviewDraft(findings=[confirmed(), unconfirmed()]))

    analysis = await analyze_interview(interview_input(), llm)

    assert analysis.status is ProfileStatus.DONE
    assert analysis.dropped == 0
    assert [(item.category, item.source) for item in analysis.items] == [
        (ItemCategory.CHECK, "면접 질문"),
        (ItemCategory.STRENGTH, "1차 면접 답변"),
        (ItemCategory.CHECK, "1차 면접 답변"),
    ]
    assert analysis.items[0].content == f"면접에서 답변을 기록하지 않았다: {CAREER}"
    assert analysis.items[1].evidence == "승인 API의 DB 조회를 캐시로 바꾸는 작업을 직접 설계했습니다."
    assert len(llm.calls) == 1


async def test_answers_are_data_blocks_and_unanswered_questions_are_left_out() -> None:
    llm = FakeLlm(InterviewDraft(findings=[]))

    await analyze_interview(interview_input(), llm)

    call = llm.calls[0]
    assert call.system.endswith(UNTRUSTED_RULE)
    assert f'<data kind="interview" label="1차 면접 답변">\n질문: {ROLE}\n답변: {ROLE_ANSWER}' in call.user
    assert CAREER not in call.user


async def test_previous_interviews_are_context_not_evidence() -> None:
    previous = [
        {"stageName": "1차 면접", "questions": [{"text": TEST, "answer": "장애 재현 테스트를 직접 작성했습니다."}]}
    ]
    borrowed = FindingDraft(
        kind="CONFLICT", content="장애 재현 테스트를 직접 작성했다.", evidence="장애 재현 테스트를 직접 작성했습니다."
    )
    conflict = FindingDraft(
        kind="CONFLICT",
        content="1차 면접에서는 테스트를 직접 작성했다고 했지만 이번에는 팀원이 맡았다고 답했다.",
        evidence="테스트는 다른 팀원이 주로 맡아서 자세히는 모릅니다.",
    )
    data = interview_input(stageName="2차 면접", previous=previous)
    llm = FakeLlm(InterviewDraft(findings=[borrowed]), InterviewDraft(findings=[conflict]))

    analysis = await analyze_interview(data, llm)

    assert "이전 면접 기록 (비교용, 근거로 쓰지 않는다)" in llm.calls[0].user
    assert '<data kind="interview" label="1차 면접 답변">' in llm.calls[0].user
    assert "evidence가 이번 면접 답변 원문에 없다" in llm.calls[1].user
    assert [(item.category, item.source) for item in analysis.items][-1] == (ItemCategory.CHECK, "2차 면접 답변")
    assert analysis.dropped == 0


async def test_prior_specialist_results_are_comparison_context_with_current_answer_evidence() -> None:
    reference = InterviewReference(
        content="장애 재현 테스트는 팀의 결과로 기록되어 본인의 역할은 아직 확인되지 않았다.",
        evidence="팀에서 장애 재현 테스트를 작성했습니다.",
        source="평가 결과",
        verification="미확인",
    )
    llm = FakeLlm(InterviewDraft(findings=[unconfirmed()]))

    analysis = await analyze_interview(interview_input(), llm, references=[reference])

    [call] = llm.calls
    assert '<data kind="specialist-reference"' in call.user
    assert reference.content in call.user
    assert reference.evidence in call.user
    assert reference.source in call.user
    assert reference.verification in call.user
    assert "비교용" in call.user
    assert call.system.endswith(UNTRUSTED_RULE)
    assert analysis.dropped == 0
    assert [(item.content, item.evidence, item.source) for item in analysis.items][-1] == (
        "장애 재현 테스트 경험은 아직 확인되지 않았다.",
        "테스트는 다른 팀원이 주로 맡아서 자세히는 모릅니다.",
        "1차 면접 답변",
    )


async def test_evidence_only_in_prior_specialist_result_is_retried_then_dropped() -> None:
    prior_evidence = "팀에서 장애 재현 테스트를 작성했습니다."
    reference = InterviewReference(
        content="팀의 장애 재현 테스트 결과가 있다.",
        evidence=prior_evidence,
        source="평가 결과",
        verification="팀 결과",
    )
    borrowed = FindingDraft(kind="CONFIRMED", content="장애 재현 테스트를 직접 작성했다.", evidence=prior_evidence)
    llm = FakeLlm(
        InterviewDraft(findings=[borrowed]),
        InterviewDraft(findings=[borrowed]),
        InterviewDraft(findings=[borrowed]),
    )

    analysis = await analyze_interview(interview_input(), llm, references=[reference])

    assert len(llm.calls) == 3
    assert "evidence가 이번 면접 답변 원문에 없다" in llm.calls[1].user
    assert reference.content in llm.calls[1].user
    assert analysis.dropped == 1
    assert [(item.category, item.source) for item in analysis.items] == [(ItemCategory.CHECK, "면접 질문")]


async def test_evidence_copied_from_the_question_is_rewritten_then_dropped() -> None:
    llm = FakeLlm(
        InterviewDraft(findings=[confirmed(), from_question()]),
        InterviewDraft(findings=[from_question()]),
        InterviewDraft(findings=[from_question()]),
    )

    analysis = await analyze_interview(interview_input(), llm)

    assert len(llm.calls) == 3
    assert [item.category for item in analysis.items] == [ItemCategory.CHECK, ItemCategory.STRENGTH]
    assert analysis.dropped == 1


async def test_rejects_decisions_discrimination_and_invented_numbers() -> None:
    decision = FindingDraft(
        kind="CONFIRMED", content="실무 역량이 확인돼 합격시킬 만하다.", evidence=ROLE_ANSWER.split(". ")[0]
    )
    invented = FindingDraft(kind="CONFIRMED", content="응답 시간을 50ms로 줄였다.", evidence=ROLE_ANSWER.split(". ")[1])
    attribute = FindingDraft(kind="UNCONFIRMED", content="나이가 많아 야근이 어려워 보인다.", evidence=TEST_ANSWER)
    llm = FakeLlm(InterviewDraft(findings=[decision, invented, attribute]), InterviewDraft(findings=[]))

    analysis = await analyze_interview(interview_input(), llm)

    retry = llm.calls[1].user
    assert "채용 결정이나 순위를 말하는 표현(합격)" in retry
    assert "content에 면접 기록에 없는 숫자가 있다" in retry
    assert "채용 판단에 쓰면 안 되는 조건" in retry
    assert [item.category for item in analysis.items] == [ItemCategory.CHECK]


async def test_without_answers_does_not_call_model() -> None:
    llm = FakeLlm()
    questions = [{"text": ROLE, "answer": ""}, {"text": TEST, "answer": "  "}]

    analysis = await analyze_interview(interview_input(questions=questions), llm)

    assert analysis.status is ProfileStatus.CHECK
    assert [item.source for item in analysis.items] == ["면접 질문", "면접 질문"]
    assert llm.calls == []


async def test_model_format_errors_end_as_failed_without_raising() -> None:
    def fail(call: LlmCall) -> InterviewDraft:
        raise LlmOutputError("형식 오류")

    llm = FakeLlm(fail, fail, fail)

    analysis = await analyze_interview(interview_input(), llm)

    assert analysis.status is ProfileStatus.FAILED
    assert [item.source for item in analysis.items] == ["면접 질문"]


async def post_analyze(session: AsyncSession, llm: FakeLlm, body: dict[str, Any]) -> Any:
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_session] = lambda: session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/agents/interview-analyst/analyze", json={"input": body})
    finally:
        app.dependency_overrides.clear()


async def profile_items(session: AsyncSession, application_id: UUID) -> list[tuple[str, str, UUID | None]]:
    session.expunge_all()
    profile = await session.scalar(select(CandidateProfile).where(CandidateProfile.application_id == application_id))
    assert profile is not None
    # 한 트랜잭션 안의 테스트라 created_at이 같다. 저장 순서 대신 내용으로 비교한다
    return sorted((item.agent, item.content, item.stage_id) for item in profile.items)


async def test_reanalysis_replaces_only_this_stage_interview_items(db_session: AsyncSession) -> None:
    application_id = UUID(INPUT_JSON["applicationId"])
    stage_id = UUID(INPUT_JSON["stageId"])
    await save_profile(
        db_session,
        company_id=UUID(INPUT_JSON["companyId"]),
        recruitment_id=UUID(INPUT_JSON["recruitmentId"]),
        application_id=application_id,
        agent=ItemAgent.APPLICATION,
        items=[NewItem(category=ItemCategory.DOMAIN, content="금융 (카드 결제)", source="이력서")],
    )
    await post_analyze(db_session, FakeLlm(InterviewDraft(findings=[confirmed(), unconfirmed()])), INPUT_JSON)
    answered = [{"text": ROLE, "answer": ROLE_ANSWER}]

    response = await post_analyze(
        db_session, FakeLlm(InterviewDraft(findings=[confirmed()])), {**INPUT_JSON, "questions": answered}
    )

    assert response.status_code == 200
    assert response.json() == {"status": "DONE", "saved": 1, "dropped": 0}
    assert await profile_items(db_session, application_id) == sorted(
        [
            (ItemAgent.APPLICATION, "금융 (카드 결제)", None),
            (ItemAgent.INTERVIEW, confirmed().content, stage_id),
        ]
    )


async def test_router_refuses_profile_of_another_company(db_session: AsyncSession) -> None:
    await post_analyze(db_session, FakeLlm(InterviewDraft(findings=[confirmed()])), INPUT_JSON)

    response = await post_analyze(
        db_session, FakeLlm(InterviewDraft(findings=[confirmed()])), {**INPUT_JSON, "companyId": str(uuid4())}
    )

    assert response.status_code == 409


async def test_model_budget_exhaustion_stops_interview_retries_immediately() -> None:
    from hiremate_ai.llm.chat import LlmFailureReason

    def exhausted(call: LlmCall) -> InterviewDraft:
        raise LlmOutputError("호출 예산", reason=LlmFailureReason.BUDGET)

    llm = FakeLlm(exhausted, exhausted, exhausted)
    analysis = await analyze_interview(interview_input(), llm)

    assert analysis.status is ProfileStatus.CHECK
    assert analysis.interrupted is True
    assert len(llm.calls) == 1
    assert all(item.category is ItemCategory.CHECK for item in analysis.items)


async def test_budget_stop_preserves_validated_interview_items_without_marking_review_done() -> None:
    from hiremate_ai.llm.chat import LlmFailureReason

    def exhausted(call: LlmCall) -> InterviewDraft:
        raise LlmOutputError("호출 예산", reason=LlmFailureReason.BUDGET)

    llm = FakeLlm(InterviewDraft(findings=[confirmed(), from_question()]), exhausted, exhausted)
    analysis = await analyze_interview(interview_input(), llm)

    assert analysis.status is ProfileStatus.CHECK
    assert analysis.interrupted is True
    assert len(llm.calls) == 2
    assert any(item.evidence == confirmed().evidence for item in analysis.items)
    assert not any(item.evidence == from_question().evidence for item in analysis.items)
