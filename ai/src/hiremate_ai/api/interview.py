from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.interview import InterviewAnalysisInput, analyze_interview
from hiremate_ai.agents.analysis.interview.store import interview_recipe
from hiremate_ai.contract import ContractModel
from hiremate_ai.db.analysis_store import session_artifacts
from hiremate_ai.db.profile import ItemAgent, ProfileStatus
from hiremate_ai.db.profile_store import ProfileScopeError, save_profile
from hiremate_ai.db.session import SessionDep
from hiremate_ai.llm.client import LlmClient, LlmDep

router = APIRouter(prefix="/agents/interview-analyst")


class AnalyzeRequest(ContractModel):
    """InterviewAnalyst.analyze(InterviewAnalysisInput input)의 매개변수."""

    input: InterviewAnalysisInput


class AnalyzeResult(ContractModel):
    """InterviewAnalyst.AnalyzeResult. 결과는 프로필에만 저장하고 화면에는 따로 보여 주지 않는다 (PRD Agent 표).

    saved: 이 전형의 면접 항목으로 프로필에 남은 수. dropped: 검사를 통과하지 못해 버린 항목 수.
    """

    status: ProfileStatus
    saved: int
    dropped: int


async def analyze_and_save(data: InterviewAnalysisInput, llm: LlmClient, session: AsyncSession) -> AnalyzeResult:
    """면접 기록을 정리해 지원자 프로필에 저장한다. ai 서버 경로와 AI 워커가 같이 쓴다.

    이 전형의 면접 항목만 바꾼다. 다른 기업 · 채용의 프로필이면 ProfileScopeError다 (아키텍처 규칙 4).
    """
    artifacts = session_artifacts(session)
    recipe = interview_recipe(llm)
    analysis = await artifacts.find_interview(data, recipe_hash=recipe) if recipe is not None else None
    if analysis is None:
        analysis = await analyze_interview(data, llm)
    profile = await save_profile(
        session,
        company_id=data.company_id,
        recruitment_id=data.recruitment_id,
        application_id=data.application_id,
        agent=ItemAgent.INTERVIEW,
        items=analysis.items,
        stage_id=data.stage_id,
    )
    if recipe is not None:
        await artifacts.save_interview(data, analysis, recipe_hash=recipe)
    await session.commit()
    saved = sum(1 for item in profile.items if item.agent == ItemAgent.INTERVIEW and item.stage_id == data.stage_id)
    return AnalyzeResult(status=analysis.status, saved=saved, dropped=analysis.dropped)


@router.post("/analyze")
async def analyze(request: AnalyzeRequest, llm: LlmDep, session: SessionDep) -> AnalyzeResult:
    try:
        return await analyze_and_save(request.input, llm, session)
    except ProfileScopeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
