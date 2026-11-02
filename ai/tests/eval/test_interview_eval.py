"""LLM_EVAL=true일 때 가상 답변으로 충분성·반복·담당을 실제 모델에서 평가한다."""

from uuid import uuid4

import pytest

from hiremate_ai.agents.generation.interview.follow_ups import suggest_follow_ups
from hiremate_ai.agents.generation.interview.types import FollowUpsRequest
from hiremate_ai.config import settings
from hiremate_ai.contract import InterviewerRole, InterviewQuestion, PostingContent, QuestionSource
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm

pytestmark = [
    pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때 실제 모델로 평가한다"),
    pytest.mark.asyncio(loop_scope="module"),
]


class MemoryLog:
    async def record(self, record: CallRecord) -> None:
        print({"agent": record.agent, "status": record.status, "output": record.output})


@pytest.mark.parametrize(
    ("question", "answer", "role", "needed"),
    [
        (
            "성능 저하를 어떻게 진단하고 직접 개선했으며 결과를 어떻게 확인했나요?",
            "APM으로 DB 140ms와 외부 호출 30ms를 분리했습니다. 제가 실행 계획을 확인해 복합 인덱스를 적용했습니다. "
            "100만 행과 동시 사용자 200명으로 같은 조건에서 세 번 테스트해 p95가 180ms에서 90ms로 줄었습니다. "
            "오류율은 0.1%로 같았고 배포 뒤 24시간 지연과 오류를 모니터링했습니다.",
            InterviewerRole.PRACTICAL,
            False,
        ),
        (
            "의견이 다른 동료와 어떻게 협의했나요?",
            "배포 일정으로 충돌했을 때 제가 동료와 회의를 열고 테스트 12개를 통과하는 기준을 합의했습니다. "
            "제가 핵심 기능과 후속 기능을 분리하는 절충안을 제안했고 동료가 동의해 금요일에 배포했습니다. "
            "배포 후 일주일 동안 오류가 없음을 함께 확인했습니다.",
            InterviewerRole.HR,
            False,
        ),
        (
            "성능 문제에서 직접 맡은 일과 판단 기준은 무엇인가요?",
            "팀에서 잘 개선했습니다. 자세한 것은 기억나지 않습니다.",
            InterviewerRole.PRACTICAL,
            True,
        ),
    ],
)
async def test_follow_up_sufficiency(
    sample_posting: PostingContent,
    question: str,
    answer: str,
    role: InterviewerRole,
    needed: bool,
) -> None:
    request = FollowUpsRequest(
        posting=sample_posting,
        chain=[
            InterviewQuestion(
                question_id=uuid4(), text=question, answer=answer, source=QuestionSource.AI, interviewer_role=role
            )
        ],
    )
    result = await suggest_follow_ups(build_llm(MemoryLog()), request)
    print(result.model_dump(mode="json"))
    assert result.needed is needed
    if needed:
        assert result.suggestions
