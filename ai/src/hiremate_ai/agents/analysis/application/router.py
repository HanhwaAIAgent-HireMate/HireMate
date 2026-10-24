"""backend 연동: POST /agents/application/analyze, POST /agents/candidate-analyst/analyze.

요청 본문은 Java 메서드의 매개변수 이름(applicant, posting, rubric)을 키로 한 JSON이다.
- application/analyze: 지원 접수 때 분석해 저장하고 요약(ApplicationAnalysis)을 돌려준다. backend가 180초 기다린다.
- candidate-analyst/analyze: 카드를 열 때 부른다. 저장된 결과가 있으면 바로 돌려주고, 없으면 분석한다.
  60초 안에 끝나지 않으면 지난 결과를 돌려주고, 그것도 없으면 503이다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from hiremate_ai.agents.analysis.application.present import to_analysis, to_candidate_analysis
from hiremate_ai.agents.analysis.application.service import RubricScopeError, analyze_application, weights
from hiremate_ai.agents.analysis.application.store import DbReviewStore, ReviewStore
from hiremate_ai.agents.analysis.application.types import AnalyzeRequest, ApplicationAnalysis
from hiremate_ai.config import settings
from hiremate_ai.contract import CandidateAnalysis
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.client import LlmDep

router = APIRouter(tags=["application"])


def get_store() -> ReviewStore:
    """FastAPI 의존성. 테스트는 app.dependency_overrides[get_store]로 메모리 저장소를 넣는다."""
    return DbReviewStore(session_factory())


StoreDep = Annotated[ReviewStore, Depends(get_store)]


@router.post("/agents/application/analyze")
async def analyze(request: AnalyzeRequest, llm: LlmDep, store: StoreDep) -> ApplicationAnalysis:
    try:
        review = await analyze_application(
            llm,
            store,
            request.applicant,
            request.posting,
            request.rubric,
            budget_seconds=settings.application_timeout_seconds,
        )
    except RubricScopeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return to_analysis(review)


@router.post("/agents/candidate-analyst/analyze")
async def candidate(request: AnalyzeRequest, llm: LlmDep, store: StoreDep) -> CandidateAnalysis:
    try:
        review = await analyze_application(
            llm,
            store,
            request.applicant,
            request.posting,
            request.rubric,
            budget_seconds=settings.application_card_timeout_seconds,
        )
    except RubricScopeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except TimeoutError as error:
        latest = await store.latest(request.applicant.info.application_id)
        if latest is None:
            raise HTTPException(status_code=503, detail="분석이 아직 끝나지 않았다") from error
        review = latest
    return to_candidate_analysis(review, request.applicant.documents, weights())
