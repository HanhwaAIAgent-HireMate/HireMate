"""Interview Agent 질문 생성 라우터 (FR-27). backend InterviewAgent.questions가 부른다.

POST /agents/interview/questions
  요청 {"applicant": ApplicantDetail, "posting": PostingContent, "analysis": CandidateAnalysis,
        "interview": InterviewView, "company": CompanyProfile | null, "focus": str | null,
        "questionCount": int | null}
        company 는 선택 (회사 인재상 · 조직 문화 → 최종면접 인성 · 조직 적응 질문의 기준). 없으면 기준 없이 만든다
  서류 전형 Agent가 저장한 상세 판정(ApplicationReview)이 ai DB에 있으면 읽어서 1차 빈틈을 고른다 (읽기만 한다).
  없으면 요청의 analysis(요약)로 고른다.
  응답 질문·생성 근거 객체 목록 [{"text": 질문, "reason": 생성 시 확인 목적과 출처}]

InterviewView는 Root Agent가 먼저 정의한 타입(agents/root/types.py)을 그대로 쓴다. 면접 Agent 쪽 모듈은 이 파일에서
가져다 쓰도록 이름을 다시 내보낸다 (QuestionSource · InterviewQuestion · PreviousInterview · InterviewView · Schedule).
"""

from fastapi import APIRouter
from pydantic import Field

from hiremate_ai.agents.analysis.application.router import StoreDep
from hiremate_ai.agents.generation.interview.agent import generate_questions, load_review
from hiremate_ai.agents.generation.interview.types import InterviewQuestionDraft
from hiremate_ai.agents.root.types import InterviewQuestion, InterviewView, PreviousInterview, QuestionSource
from hiremate_ai.agents.root.types import InterviewSchedule as Schedule
from hiremate_ai.contract import ApplicantDetail, CandidateAnalysis, CompanyProfile, ContractModel, PostingContent
from hiremate_ai.llm.client import LlmDep

router = APIRouter(prefix="/agents/interview", tags=["interview"])

__all__ = [
    "InterviewQuestion",
    "InterviewView",
    "PreviousInterview",
    "QuestionSource",
    "QuestionsRequest",
    "Schedule",
    "router",
]


class QuestionsRequest(ContractModel):
    """backend InterviewAgent.questions의 매개변수. questionCount는 Chat의 추가 목표 개수다."""

    applicant: ApplicantDetail
    posting: PostingContent
    analysis: CandidateAnalysis
    interview: InterviewView
    company: CompanyProfile | None = None  # backend가 아직 안 보내도 되게 선택으로 둔다
    focus: str | None = None
    question_count: int | None = Field(default=None, ge=1)


@router.post("/questions")
async def questions(request: QuestionsRequest, llm: LlmDep, store: StoreDep) -> list[InterviewQuestionDraft]:
    """이전 전형 근거로 맞춤 질문을 만든다. 카드에 이미 있는 질문과 비슷한 질문은 뺀다."""
    review = await load_review(store, request.applicant)
    drafts: list[InterviewQuestionDraft] = []
    await generate_questions(
        llm,
        applicant=request.applicant,
        posting=request.posting,
        analysis=request.analysis,
        interview=request.interview,
        focus=request.focus,
        question_count=request.question_count,
        company=request.company,
        review=review,
        drafts=drafts,
    )
    return drafts
