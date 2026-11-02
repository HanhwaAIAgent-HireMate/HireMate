"""실제 평가에서 발견한 모호한 질문을 회귀 검사한다."""

import pytest

from hiremate_ai.agents.generation.interview.quality import checked_role, clarity_problem
from hiremate_ai.contract import InterviewerRole


@pytest.mark.parametrize(
    "text",
    [
        "결제 승인 API에서 두 가지 방법 중 어느 쪽을 선택하나요?",
        "처리 구조 개선 시 적용하는 원칙은 무엇인가요?",
        "Java와 Spring Batch로 개발할 때 두 가지 방법 중 어느 쪽을 선택하나요?",
        "Spring Boot로 만들 때 적용하는 구체적인 원칙의 차이와 어느 쪽을 선택하는지 설명해 주세요.",
    ],
)
def test_rejects_missing_comparison_or_conditions(text: str) -> None:
    assert clarity_problem(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "낙관적 잠금과 비관적 잠금 중 충돌이 잦을 때 어느 쪽을 선택하나요?",
        "결제 중복 요청이 생기면 멱등 키로 어떻게 처리하나요?",
        "일정 충돌 상황에서 적용한 원칙은 무엇인가요?",
    ],
)
def test_concrete_questions_are_allowed(text: str) -> None:
    assert clarity_problem(text) is None


@pytest.mark.parametrize(
    ("text", "proposed", "expected"),
    [
        ("Java와 Redis 등 기술 스택의 선택 목적은 무엇인가요?", InterviewerRole.HR, InterviewerRole.PRACTICAL),
        ("고객 신뢰에 관한 신념을 적용한 경험을 말씀해 주세요.", InterviewerRole.PRACTICAL, InterviewerRole.HR),
        ("코드 리뷰에서 동료와 갈등을 조율한 경험은?", InterviewerRole.HR, InterviewerRole.HR),
    ],
)
def test_clear_question_focus_corrects_owner(text: str, proposed: InterviewerRole, expected: InterviewerRole) -> None:
    assert checked_role(text, proposed) == expected
