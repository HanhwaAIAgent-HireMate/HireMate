"""Interview Agent 답변 분석 라우터 (FR-28). backend InterviewAnalyst.analyze가 부른다.

POST /agents/interview/analyze  요청 {"interview": InterviewView}  응답 InterviewAnalysis
"""

from enum import StrEnum
from uuid import UUID

from fastapi import APIRouter

from hiremate_ai.agents.analysis.interview.agent import analyze_answers
from hiremate_ai.contract import ContractModel, InterviewView
from hiremate_ai.llm.client import LlmDep

router = APIRouter(prefix="/agents/interview", tags=["interview"])


class AnswerStatus(StrEnum):
    """질문 하나의 확인 상태 (ai.application.InterviewAnalysis.Status)."""

    CONFIRMED = "CONFIRMED"
    """질문이 확인하려던 것이 답변에 구체적으로 나왔다."""
    PARTIAL = "PARTIAL"
    """일부만 나왔다."""
    NOT_CONFIRMED = "NOT_CONFIRMED"
    """답변은 있지만 확인하려던 것이 나오지 않았다."""
    NO_ANSWER = "NO_ANSWER"
    """면접관이 답변을 기록하지 않았다. 모델을 부르지 않는다."""


class ConfirmedPoint(ContractModel):
    """확인된 점과 답변 원문 속 인용. 인용은 답변에 실제로 있는 글자만 남긴다 (규칙 7)."""

    point: str
    quote: str


class AnswerFinding(ContractModel):
    """질문 하나의 분석. 답변 원문은 backend에 그대로 있고, 여기에는 AI 해석만 담는다."""

    question_id: UUID
    status: AnswerStatus
    confirmed: list[ConfirmedPoint]
    unconfirmed: list[str]


class InterviewAnalysis(ContractModel):
    """면접 답변 분석 결과 (ai.application.InterviewAnalysis). 합격 · 불합격 의견은 담지 않는다."""

    answers: list[AnswerFinding]
    agent: str
    stub: bool


class AnalyzeRequest(ContractModel):
    """backend InterviewAnalyst.analyze(InterviewView interview)의 매개변수."""

    interview: InterviewView


@router.post("/analyze")
async def analyze(request: AnalyzeRequest, llm: LlmDep) -> InterviewAnalysis:
    """지금 전형 카드의 질문(interview.questions)마다 답변에서 확인된 점과 확인 안 된 점을 정리한다."""
    findings = await analyze_answers(llm, request.interview.questions)
    answers = [
        AnswerFinding(
            question_id=finding.question_id,
            status=AnswerStatus(finding.status),
            confirmed=[ConfirmedPoint(point=point, quote=quote) for point, quote in finding.confirmed],
            unconfirmed=finding.unconfirmed,
        )
        for finding in findings
    ]
    return InterviewAnalysis(answers=answers, agent="Interview Agent", stub=False)
