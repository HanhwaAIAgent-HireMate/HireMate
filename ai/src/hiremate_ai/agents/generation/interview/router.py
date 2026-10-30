"""Interview Agent 질문 생성 라우터 (FR-27). backend InterviewAgent.questions가 부른다.

POST /agents/interview/questions
  요청 {"applicant": ApplicantDetail, "posting": PostingContent, "analysis": CandidateAnalysis,
        "interview": InterviewView, "company": CompanyProfile | null, "focus": str | null,
        "questionCount": int | null}
        company 는 선택 (회사 인재상 · 조직 문화 → 최종면접 인성 · 조직 적응 질문의 기준). 없으면 기준 없이 만든다
  서류 전형 Agent가 저장한 상세 판정(ApplicationReview)이 ai DB에 있으면 읽어서 1차 빈틈을 고른다 (읽기만 한다).
  없으면 요청의 analysis(요약)로 고른다.
  응답 질문·생성 근거 객체 목록 [{"text": 질문, "reason": 생성 시 확인 목적과 출처}]

POST /agents/interview/follow-ups  backend InterviewAgent.followUps가 부른다
  🎤 면접관이 [꼬리질문 받기] · [다시 제안]을 눌렀을 때만 부른다
  요청 {"posting": PostingContent, "chain": [InterviewQuestion, ...], "avoid": [str, ...]}
        chain 은 처음 질문부터 꼬리질문을 받을 질문까지 (마지막이 지금 질문)
  응답 {"needed": bool, "suggestions": [{"text": 꼬리질문, "check": 확인 포인트}]}  답이 충분하면 needed=false
"""

from fastapi import APIRouter
from pydantic import Field

from hiremate_ai.agents.analysis.application.router import StoreDep
from hiremate_ai.agents.generation.interview.agent import generate_questions, load_review
from hiremate_ai.agents.generation.interview.follow_ups import suggest_follow_ups
from hiremate_ai.agents.generation.interview.types import FollowUpsRequest, InterviewFollowUps, InterviewQuestionDraft
from hiremate_ai.contract import (
    ApplicantDetail,
    CandidateAnalysis,
    CompanyProfile,
    ContractModel,
    InterviewerMemo,
    InterviewView,
    PostingContent,
)
from hiremate_ai.llm.client import LlmDep

router = APIRouter(prefix="/agents/interview", tags=["interview"])


class QuestionsRequest(ContractModel):
    """backend InterviewAgent.questions의 매개변수. questionCount는 Chat의 추가 목표 개수다."""

    applicant: ApplicantDetail
    posting: PostingContent
    analysis: CandidateAnalysis
    interview: InterviewView
    company: CompanyProfile | None = None  # backend가 아직 안 보내도 되게 선택으로 둔다
    focus: str | None = None
    question_count: int | None = Field(default=None, ge=1)
    memo: InterviewerMemo | None = None


@router.post("/questions")
async def questions(request: QuestionsRequest, llm: LlmDep, store: StoreDep) -> list[InterviewQuestionDraft]:
    """이전 전형 근거로 맞춤 질문을 만든다. 카드에 이미 있는 질문과 비슷한 질문은 뺀다."""
    review = await load_review(
        store, request.applicant, company_id=request.company.company_id if request.company else None
    )
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
        memo=request.memo,
    )
    return drafts


@router.post("/follow-ups")
async def follow_ups(request: FollowUpsRequest, llm: LlmDep) -> InterviewFollowUps:
    """🎤 지금 질문의 답을 보고 꼬리질문을 최대 2개 제안한다. 답이 충분하면 확인할 점이 없다고 돌려준다.

    제안은 저장하지 않는다. 면접관이 고른 질문은 backend가 저장한다.
    """
    return await suggest_follow_ups(llm, request)
