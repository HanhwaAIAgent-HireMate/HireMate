"""🎤 꼬리질문 제안: 답이 충분하면 확인할 점 없음, 아니면 검사를 통과한 질문만 최대 2개."""

from uuid import uuid4

import httpx

from hiremate_ai.agents.generation.interview.follow_ups import FollowUpDraft, suggest_follow_ups
from hiremate_ai.agents.generation.interview.types import FollowUpsRequest
from hiremate_ai.contract import InterviewerRole, InterviewQuestion, PostingContent, QuestionSource
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.main import app

ROOT_TEXT = "정산 배치 개선에서 직접 설계·구현한 부분은 무엇이었나요?"


def turn(text: str, answer: str, *, role: InterviewerRole | None = InterviewerRole.PRACTICAL) -> InterviewQuestion:
    return InterviewQuestion(
        question_id=uuid4(), text=text, source=QuestionSource.AI, answer=answer, interviewer_role=role
    )


def request(posting: PostingContent, *answers: str, avoid: list[str] | None = None) -> FollowUpsRequest:
    chain = [turn(ROOT_TEXT, answers[0])]
    for index, answer in enumerate(answers[1:], start=1):
        chain.append(turn(f"꼬리질문 {index}: 그때 판단 기준은 무엇이었나요?", answer))
    return FollowUpsRequest(posting=posting, chain=chain, avoid=avoid or [])


def draft(*pairs: tuple[str, str], needed: bool = True) -> FollowUpDraft:
    return FollowUpDraft.model_validate(
        {"needed": needed, "suggestions": [{"text": text, "check": check} for text, check in pairs]}
    )


GOOD = (
    ("병렬로 나눌 때 작업 단위는 어떤 기준으로 정하셨나요?", "병렬화의 판단 기준이 드러나지 않았습니다."),
    ("병렬화 뒤 처리 결과가 맞는지는 어떻게 확인하셨나요?", "결과 검증 방법이 드러나지 않았습니다."),
)


async def test_sufficient_answer_has_nothing_more_to_check(sample_posting: PostingContent) -> None:
    llm = FakeLlm(draft(needed=False))

    result = await suggest_follow_ups(
        llm, request(sample_posting, "가맹점 단위로 나눠 병렬 처리하고 건수 검증까지 했습니다.")
    )

    assert result.needed is False
    assert result.suggestions == []
    assert len(llm.calls) == 1


async def test_two_suggestions_with_check_points(sample_posting: PostingContent) -> None:
    llm = FakeLlm(draft(*GOOD))

    result = await suggest_follow_ups(llm, request(sample_posting, "병렬로 바꿔서 빨라졌습니다."))

    assert result.needed is True
    assert [s.text for s in result.suggestions] == [text for text, _ in GOOD]
    assert all(s.check for s in result.suggestions)
    # 지원자의 답은 <data> 블록으로 감싸 넣는다 (규칙 5)
    user = llm.calls[0].user
    assert '<data kind="current" interviewer="PRACTICAL(실무)">' in user
    assert "병렬로 바꿔서 빨라졌습니다." in user


async def test_earlier_turns_and_avoid_are_in_the_prompt(sample_posting: PostingContent) -> None:
    llm = FakeLlm(draft(*GOOD))
    avoided = "가맹점별로 나눴을 때 생긴 문제는 무엇이었나요?"

    await suggest_follow_ups(llm, request(sample_posting, "병렬로 바꿨습니다.", "가맹점별로요.", avoid=[avoided]))

    user = llm.calls[0].user
    assert '<data kind="earlier">' in user and ROOT_TEXT in user
    assert avoided in user


async def test_discriminatory_internal_and_repeated_questions_are_dropped(sample_posting: PostingContent) -> None:
    avoided = "가맹점별로 나눴을 때 생긴 문제는 무엇이었나요?"
    llm = FakeLlm(
        draft(
            ("결혼하셨으면 야근은 괜찮으신가요?", "근무 가능 여부"),
            ("이 답이면 합격 점수에 미치지 못하는데 보충하실 게 있나요?", "평가"),
            (ROOT_TEXT, "앞 질문 반복"),
            (avoided, "앞 제안 반복"),
            GOOD[0],
            GOOD[1],
        )
    )

    result = await suggest_follow_ups(llm, request(sample_posting, "병렬로 바꿨습니다.", avoid=[avoided]))

    assert [s.text for s in result.suggestions] == [text for text, _ in GOOD]


async def test_retries_once_when_nothing_usable_then_gives_up(sample_posting: PostingContent) -> None:
    bad = ("나이가 어떻게 되시나요?", "나이")
    llm = FakeLlm(draft(bad), draft(bad))

    result = await suggest_follow_ups(llm, request(sample_posting, "병렬로 바꿨습니다."))

    assert result.needed is False  # 꾸며내지 않는다
    assert len(llm.calls) == 2
    assert '<data kind="rejected">' in llm.calls[1].user


async def test_retry_can_recover(sample_posting: PostingContent) -> None:
    llm = FakeLlm(draft((ROOT_TEXT, "반복")), draft(*GOOD))

    result = await suggest_follow_ups(llm, request(sample_posting, "병렬로 바꿨습니다."))

    assert len(result.suggestions) == 2


async def test_at_most_two_similar_ones_collapsed(sample_posting: PostingContent) -> None:
    llm = FakeLlm(draft(GOOD[0], (GOOD[0][0] + " ", "같은 질문"), GOOD[1], ("세 번째 질문은 무엇인가요?", "셋째")))

    result = await suggest_follow_ups(llm, request(sample_posting, "병렬로 바꿨습니다."))

    assert [s.text for s in result.suggestions] == [text for text, _ in GOOD]


async def test_hr_question_is_labeled_for_the_model(sample_posting: PostingContent) -> None:
    llm = FakeLlm(draft(needed=False))
    hr = FollowUpsRequest(
        posting=sample_posting,
        chain=[turn("지원 동기를 말씀해 주세요.", "성장하고 싶어서요.", role=InterviewerRole.HR)],
    )

    await suggest_follow_ups(llm, hr)

    assert 'interviewer="HR(인사)"' in llm.calls[0].user


async def test_follow_ups_route(sample_posting: PostingContent) -> None:
    app.dependency_overrides[get_llm] = lambda: FakeLlm(draft(*GOOD))
    body = request(sample_posting, "병렬로 바꿨습니다.").model_dump(mode="json", by_alias=True)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/agents/interview/follow-ups", json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "needed": True,
        "suggestions": [{"text": text, "check": check} for text, check in GOOD],
    }
