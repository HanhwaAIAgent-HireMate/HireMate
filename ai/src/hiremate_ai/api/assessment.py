from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.assessment import AssessmentInput, analyze_assessment
from hiremate_ai.contract import ContractModel
from hiremate_ai.db.profile import ItemAgent, ProfileStatus
from hiremate_ai.db.profile_store import ProfileScopeError, save_profile
from hiremate_ai.db.session import SessionDep
from hiremate_ai.llm.client import LlmClient, LlmDep

router = APIRouter(prefix="/agents/assessment")


class AnalyzeRequest(ContractModel):
    """AssessmentAgent.analyze(AssessmentInput input)의 매개변수."""

    input: AssessmentInput


class AnalyzeResult(ContractModel):
    """AssessmentAgent.AnalyzeResult. 결과는 프로필에만 저장하고 화면에는 따로 보여 주지 않는다 (PRD Agent 표).

    saved: 이 전형의 평가 항목으로 프로필에 남은 수. dropped: 검사를 통과하지 못해 버린 항목 수.
    """

    status: ProfileStatus
    saved: int
    dropped: int


async def analyze_and_save(data: AssessmentInput, llm: LlmClient, session: AsyncSession) -> AnalyzeResult:
    """평가 자료를 분석해 지원자 프로필에 저장한다. ai 서버 경로와 AI 워커가 같이 쓴다.

    다른 기업 · 채용의 프로필이면 ProfileScopeError다 (아키텍처 규칙 4).
    """
    analysis = await analyze_assessment(data, llm)
    profile = await save_profile(
        session,
        company_id=data.company_id,
        recruitment_id=data.recruitment_id,
        application_id=data.application_id,
        agent=ItemAgent.ASSESSMENT,
        items=analysis.items,
        stage_id=data.stage_id,
    )
    await session.commit()
    saved = sum(1 for item in profile.items if item.agent == ItemAgent.ASSESSMENT and item.stage_id == data.stage_id)
    return AnalyzeResult(status=analysis.status, saved=saved, dropped=analysis.dropped)


@router.post("/analyze")
async def analyze(request: AnalyzeRequest, llm: LlmDep, session: SessionDep) -> AnalyzeResult:
    try:
        return await analyze_and_save(request.input, llm, session)
    except ProfileScopeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
