"""최종 합격자의 지원자 프로필 읽기. 평가 · 면접 분석 Agent가 남긴 항목을 리포트 근거로 쓴다 (v8 Report 입력).

읽기만 한다. 다른 기업 · 채용의 프로필은 읽지 않는다 (아키텍처 규칙 4). 지원서 분석은 backend가 notable로 따로 보낸다.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.generation.report.types import ProfileNote, ReportInput
from hiremate_ai.db.profile import CandidateProfile, ItemAgent, ItemCategory

STAGE_AGENTS = (ItemAgent.ASSESSMENT, ItemAgent.INTERVIEW)
"""리포트가 프로필에서 더 읽는 분석 Agent. 전형을 거치며 쌓인 평가 · 면접 근거다."""


async def load_profiles(session: AsyncSession, data: ReportInput) -> dict[UUID, list[ProfileNote]]:
    """합격자마다 평가 · 면접 분석 항목을 돌려준다. 프로필이 없는 합격자는 빠진다."""
    ids = [finalist.application_id for finalist in data.finalists]
    if not ids:
        return {}
    profiles = await session.scalars(
        select(CandidateProfile).where(
            CandidateProfile.application_id.in_(ids),
            CandidateProfile.company_id == data.company_id,
            CandidateProfile.recruitment_id == data.recruitment_id,
        )
    )
    return {
        profile.application_id: [
            ProfileNote(
                agent=ItemAgent(item.agent),
                category=ItemCategory(item.category),
                content=item.content,
                evidence=item.evidence,
                source=item.source,
            )
            for item in profile.items
            if item.agent in STAGE_AGENTS
        ]
        for profile in profiles
    }
