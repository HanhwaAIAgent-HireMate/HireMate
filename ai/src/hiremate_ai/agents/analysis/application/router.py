"""backend 연동: POST /agents/application/analyze, POST /agents/candidate-analyst/analyze.

요청 본문은 Java 메서드의 매개변수 이름(applicant, posting, rubric)을 키로 한 JSON이다.
- application/analyze: 지원 접수 때 분석해 저장하고 요약(ApplicationAnalysis)을 돌려준다. backend가 180초 기다린다.
- candidate-analyst/labels · factors · talents: 표 보기의 열 이름, 회사 글의 인재상 요소,
  지원자별 인재상 판정 (table.py).
- candidate-analyst/analyze: 카드를 열 때 부른다. 평가 기준이 같은 저장 결과가 있으면 날짜와 상관없이 바로 돌려주고,
  없으면 분석한다. 시간 안에 끝나지 않으면 지난 결과를 돌려주고, 그것도 없으면 503이다.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from hiremate_ai.agents.analysis.application.normalize import normalize_document
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
    DocumentNormalizationRequest,
    FeatureLabels,
    FeatureLabelsRequest,
    NormalizedDocument,
    TalentFit,
    TalentFitRequest,
)
from hiremate_ai.db.analysis_store import DbAnalysisArtifacts
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmDep
from hiremate_ai.tools.profile_search import ProfileIndexer, get_profile_embedder, index_profile_safely, profile_indexer

router = APIRouter(tags=["application"])


@router.post("/agents/application/normalize")
async def normalize(request: DocumentNormalizationRequest, llm: LlmDep) -> NormalizedDocument:
    try:
        return await normalize_document(llm, request)
    except LlmOutputError as error:
        raise HTTPException(status_code=503, detail="문서 정제를 완료하지 못했습니다. 다시 요청해 주세요.") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail="문서 정제 결과의 형식을 확인하지 못했습니다.") from error


def get_store() -> ReviewStore:
    """FastAPI 의존성. 테스트는 app.dependency_overrides[get_store]로 메모리 저장소를 넣는다."""
    return DbReviewStore(session_factory())


StoreDep = Annotated[ReviewStore, Depends(get_store)]


def get_profile_indexer() -> ProfileIndexer:
    return profile_indexer(session_factory(), get_profile_embedder())


IndexerDep = Annotated[ProfileIndexer, Depends(get_profile_indexer)]


@router.post("/agents/application/analyze")
async def analyze(request: AnalyzeRequest, llm: LlmDep, store: StoreDep, indexer: IndexerDep) -> ApplicationAnalysis:
    try:
        review = await analyze_application(
            llm,
            store,
            request.applicant,
            request.posting,
            request.rubric,
            budget_seconds=settings.application_timeout_seconds,
            review_extraction=True,
        )
    except RubricScopeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    await index_profile_safely(
        indexer,
        request.rubric.company_id,
        request.rubric.recruitment_id,
        review.application_id,
        budget_seconds=settings.ncs_embed_timeout_seconds,
    )
    return to_analysis(review)


@router.post("/agents/candidate-analyst/analyze")
async def candidate(
    request: AnalyzeRequest, llm: LlmDep, store: StoreDep, indexer: IndexerDep, tasks: BackgroundTasks
) -> CandidateAnalysis:
    # 분석 캐시는 날짜별이라 어제 분석을 찾지 못한다. 다시 분석하면 프로필 임베딩이 지워지므로 저장 결과를 읽는다
    latest = await store.latest(
        request.applicant.info.application_id,
        company_id=request.rubric.company_id,
        recruitment_id=request.rubric.recruitment_id,
    )
    if latest is not None and latest.criteria_version == request.rubric.criteria_version:
        return to_candidate_analysis(latest, request.applicant.documents)
    try:
        review = await analyze_application(
            llm,
            store,
            request.applicant,
            request.posting,
            request.rubric,
            budget_seconds=settings.application_card_timeout_seconds,
            review_extraction=True,
        )
    except RubricScopeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except TimeoutError as error:
        if latest is None:
            raise HTTPException(status_code=503, detail="분석이 아직 끝나지 않았다") from error
        return to_candidate_analysis(latest, request.applicant.documents)
    # 임베딩은 CPU에서 오래 걸릴 수 있어 카드 응답을 붙잡지 않는다
    tasks.add_task(
        index_profile_safely, indexer, request.rubric.company_id, request.rubric.recruitment_id, review.application_id
    )
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
