"""backend 연동: POST /agents/application/analyze, POST /agents/candidate-analyst/analyze.

요청 본문은 Java 메서드의 매개변수 이름(applicant, posting, rubric)을 키로 한 JSON이다.
- application/analyze: 지원 접수 때 분석해 저장하고 요약(ApplicationAnalysis)을 돌려준다. backend가 180초 기다린다.
- candidate-analyst/labels · factors · talents: 표 보기의 열 이름, 회사 글의 인재상 요소,
  지원자별 인재상 판정 (table.py).
- candidate-analyst/analyze: 카드를 열 때 부른다. 저장된 결과가 있으면 바로 돌려주고, 없으면 분석한다.
  60초 안에 끝나지 않으면 지난 결과를 돌려주고, 그것도 없으면 503이다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from hiremate_ai.agents.analysis.application.present import to_analysis, to_candidate_analysis
from hiremate_ai.agents.analysis.application.service import RubricScopeError, analyze_application
from hiremate_ai.agents.analysis.application.store import DbReviewStore, ReviewStore
from hiremate_ai.agents.analysis.application.table import (
    company_factors,
    feature_labels,
    judge_talents,
    talent_recipe,
    talent_source,
)
from hiremate_ai.agents.analysis.application.types import AnalyzeRequest, ApplicationAnalysis
from hiremate_ai.config import settings
from hiremate_ai.contract import (
    CandidateAnalysis,
    CompanyFactors,
    CompanyFactorsRequest,
    FeatureLabels,
    FeatureLabelsRequest,
    TalentFit,
    TalentFitRequest,
)
from hiremate_ai.db.analysis_store import DbAnalysisArtifacts
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
        latest = await store.latest(
            request.applicant.info.application_id,
            company_id=request.rubric.company_id,
            recruitment_id=request.rubric.recruitment_id,
        )
        if latest is None:
            raise HTTPException(status_code=503, detail="분석이 아직 끝나지 않았다") from error
        review = latest
    return to_candidate_analysis(review, request.applicant.documents)


def get_artifacts() -> DbAnalysisArtifacts:
    """인재상 판정을 다시 쓰려고 저장하는 곳. 테스트는 dependency_overrides로 바꾼다."""
    return DbAnalysisArtifacts(session_factory())


ArtifactsDep = Annotated[DbAnalysisArtifacts, Depends(get_artifacts)]


@router.post("/agents/candidate-analyst/labels")
async def labels(request: FeatureLabelsRequest, llm: LlmDep) -> FeatureLabels:
    """표 보기의 열 이름. 평가 기준 · 인재상 문장을 짧은 키워드로 바꾼다."""
    return FeatureLabels(labels=await feature_labels(llm, request.texts))


@router.post("/agents/candidate-analyst/factors")
async def factors(request: CompanyFactorsRequest, llm: LlmDep) -> CompanyFactors:
    """회사 소개 · 조직 문화 글에서 인재상 요소를 뽑는다. 설정의 인재상과 합쳐 표 · 판정에 쓴다."""
    return await company_factors(llm, request.text)


@router.post("/agents/candidate-analyst/talents")
async def talents(request: TalentFitRequest, llm: LlmDep, store: StoreDep, artifacts: ArtifactsDep) -> TalentFit:
    """지원자 한 명의 인재상 판정. 저장된 분석과 인재상이 같으면 지난 판정을 돌려준다."""
    scope = {
        "company_id": request.company_id,
        "recruitment_id": request.recruitment_id,
        "application_id": request.application_id,
    }
    review = await store.latest(
        request.application_id, company_id=request.company_id, recruitment_id=request.recruitment_id
    )
    recipe = talent_recipe(llm)
    if review is None or recipe is None:
        return await judge_talents(llm, review, request.talents)
    source = talent_source(review, request.talents)
    saved = await artifacts.find_talents(**scope, source_hash=source, recipe_hash=recipe)
    if saved is not None:
        return saved
    fit = await judge_talents(llm, review, request.talents)
    await artifacts.save_talents(fit, **scope, source_hash=source, recipe_hash=recipe)
    return fit
