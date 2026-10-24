"""지원자 프로필 조회 (화면용, STG-06 프로필 탭). backend가 지원자 카드를 그릴 때 부른다.

POST /agents/profile/read  요청 {"companyId", "recruitmentId", "applicationId"}  응답 CandidateProfileView

규칙
- 읽기만 한다. 프로필은 분석 Agent만 저장한다 (분석 Agent에 쓰기 도구를 주지 않음, 규칙 5).
- 기업 · 채용이 다른 프로필은 없는 것처럼 빈 결과를 돌려준다 (규칙 4). 권한과 전형 대상은 backend가 먼저 확인한다.
- 항목은 저장된 순서 그대로 돌려준다. 확인 상태로 거르거나 묶는 일은 화면이 한다.
"""

from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.contract import ContractModel
from hiremate_ai.db.profile import CandidateProfile, ProfileStatus, Verification
from hiremate_ai.db.session import SessionDep

router = APIRouter(prefix="/agents/profile")


class ReadRequest(ContractModel):
    """ProfileReader.read(companyId, recruitmentId, applicationId)의 매개변수."""

    company_id: UUID
    recruitment_id: UUID
    application_id: UUID


class ProfileItemView(ContractModel):
    """프로필 항목 한 줄 (ai.application.CandidateProfileView.ProfileItemView).

    category · agent는 db.profile의 ItemCategory · ItemAgent 값이다. 새 값이 더해져도 화면이 깨지지 않게 글로 보낸다.
    """

    category: str
    agent: str
    content: str
    evidence: str | None  # 원문 근거 문장. 없으면 null
    source: str
    verification: Verification  # 확인 상태
    stage_id: UUID | None  # 평가 · 면접 항목이면 그 전형 ID


class CandidateProfileView(ContractModel):
    """지원자 프로필 (ai.application.CandidateProfileView). 프로필이 아직 없으면 status가 null이고 항목이 비어 있다."""

    application_id: UUID
    status: ProfileStatus | None
    summary: str
    items: list[ProfileItemView]


async def read_profile_view(session: AsyncSession, request: ReadRequest) -> CandidateProfileView:
    """요청한 기업 · 채용 범위 안에서 지원자 프로필을 읽어 화면용으로 바꾼다."""
    # 1) 지원서 · 기업 · 채용이 모두 맞는 프로필만 찾는다 (다른 기업 프로필은 없는 것과 같다)
    profile = await session.scalar(
        select(CandidateProfile).where(
            CandidateProfile.application_id == request.application_id,
            CandidateProfile.company_id == request.company_id,
            CandidateProfile.recruitment_id == request.recruitment_id,
        )
    )
    if profile is None:
        return CandidateProfileView(application_id=request.application_id, status=None, summary="", items=[])
    # 2) 한 번에 저장한 항목은 저장 시각이 같으므로 id로 순서를 고정한다
    items = sorted(profile.items, key=lambda item: (item.created_at, str(item.id)))
    return CandidateProfileView(
        application_id=profile.application_id,
        status=ProfileStatus(profile.status),
        summary=profile.summary,
        items=[
            ProfileItemView(
                category=item.category,
                agent=item.agent,
                content=item.content,
                evidence=item.evidence,
                source=item.source,
                verification=Verification(item.verification),
                stage_id=item.stage_id,
            )
            for item in items
        ],
    )


@router.post("/read")
async def read(request: ReadRequest, session: SessionDep) -> CandidateProfileView:
    return await read_profile_view(session, request)
