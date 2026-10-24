"""지원자 프로필 저장 (FR-08).

분석 Agent(지원서 · 평가 · 면접)가 분석을 마치면 save_profile을 불러 결과를 프로필에 넣는다.

규칙
- 받은 값을 그대로 저장한다. 점수를 다시 매기거나 문장을 고치지 않는다 (다른 역할의 결과를 재해석하지 않음).
- 같은 Agent가 같은 전형을 다시 분석하면 그 Agent · 전형의 항목만 새 결과로 바꾸고 다른 항목은 그대로 둔다.
- 제출 문서를 함께 주면 근거 문장이 원문에 있는지 확인하고, 없으면 그 항목을 버린다 (아키텍처 규칙 7).
- 항목마다 확인 상태를 적는다. 넘기지 않으면 근거 문장이 있으면 근거 있음, 없으면 미확인이다.
  근거 문장이 없는 항목은 무엇을 넘겼든 미확인이다 ("근거가 없으면 '미확인'").
- 커밋은 부르는 쪽이 한다 (db.session 규칙). 이 함수는 flush까지만 한다.

사용 예 (지원서 분석 Agent)
    profile = await save_profile(
        session,
        company_id=company_id,
        recruitment_id=applicant.info.recruitment_id,
        application_id=applicant.info.application_id,
        agent=ItemAgent.APPLICATION,
        fields=ProfileFields(status=ProfileStatus.DONE, career_years=4, ...),
        items=[NewItem(category=ItemCategory.DOMAIN, content="금융 (카드 결제)", evidence="...", source="이력서")],
        documents=applicant.documents,
    )
    await session.commit()
"""

import logging
from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.guardrails import evidence_source
from hiremate_ai.contract import ApplicantDocument
from hiremate_ai.db.profile import CandidateProfile, ItemAgent, ItemCategory, ProfileItem, ProfileStatus, Verification

logger = logging.getLogger(__name__)


class _Input(BaseModel):
    """필드는 snake_case, JSON 이름은 camelCase다 (contract.py와 같은 규칙)."""

    model_config = ConfigDict(
        alias_generator=to_camel, validate_by_name=True, validate_by_alias=True, serialize_by_alias=True, frozen=True
    )


class ProfileFields(_Input):
    """지원서 분석이 정하는 지원자 요약 값. 평가 · 면접 분석은 넘기지 않는다."""

    status: ProfileStatus
    career_years: int | None
    last_company: str | None
    document_score: float | None
    passed: bool | None  # AI 기준 통과 여부
    summary: str = ""


class NewItem(_Input):
    """프로필에 넣을 항목 한 줄."""

    category: ItemCategory
    content: str
    evidence: str | None = None  # 원문 근거 문장. 근거가 없는 항목(확인 필요 등)은 None
    source: str  # 출처 (이력서, 자기소개서, 평가 결과, 면접 답변 등)
    # 확인 상태. 평가 · 면접 분석이 확인됨 · 상충을 알 때 넘긴다. 비우면 근거 문장으로 정한다
    verification: Verification | None = None


class ProfileScopeError(ValueError):
    """이미 있는 프로필과 기업 · 채용이 다를 때. 다른 기업의 프로필을 덮어쓰지 않게 막는다 (아키텍처 규칙 4)."""


async def save_profile(
    session: AsyncSession,
    *,
    company_id: UUID,
    recruitment_id: UUID,
    application_id: UUID,
    agent: ItemAgent,
    items: Sequence[NewItem],
    fields: ProfileFields | None = None,
    stage_id: UUID | None = None,
    documents: Sequence[ApplicantDocument] = (),
) -> CandidateProfile:
    """분석 결과를 지원자 프로필에 저장하고 저장된 프로필을 돌려준다.

    agent: 결과를 낸 분석 Agent. 이 Agent가 stage_id 전형에서 쓴 이전 항목만 바뀐다.
    fields: 지원서 분석이면 넘긴다. 없으면 요약 값은 그대로 둔다.
    stage_id: 평가 · 면접 분석이면 그 전형 ID. 지원서 분석은 None.
    documents: 근거 문장을 확인할 제출 문서. 비우면 확인하지 않는다 (평가 결과 · 면접 답변처럼 문서가 아닌 자료).
    """
    profile = await session.scalar(select(CandidateProfile).where(CandidateProfile.application_id == application_id))
    if profile is None:
        # 지원서 분석 전에 다른 결과가 먼저 오면 요약 값 없이 '확인 필요'로 만들어 둔다
        profile = CandidateProfile(
            application_id=application_id,
            company_id=company_id,
            recruitment_id=recruitment_id,
            status=ProfileStatus.CHECK,
            summary="",
            items=[],
        )
        session.add(profile)
    elif profile.company_id != company_id or profile.recruitment_id != recruitment_id:
        raise ProfileScopeError(f"지원서 {application_id}의 프로필은 다른 기업 · 채용에 속한다")

    if fields is not None:
        profile.status = fields.status
        profile.career_years = fields.career_years
        profile.last_company = fields.last_company
        profile.document_score = fields.document_score
        profile.passed = fields.passed
        profile.summary = fields.summary

    checked = [item for item in (_checked(item, documents) for item in items) if item is not None]
    if len(checked) < len(items):
        logger.info("근거 문장을 원문에서 찾지 못한 항목 %d개를 버렸다 (%s)", len(items) - len(checked), application_id)

    # 같은 Agent · 같은 전형의 이전 항목은 빼고(삭제됨) 새 항목을 더한다
    kept = [item for item in profile.items if not (item.agent == agent and item.stage_id == stage_id)]
    new = [
        ProfileItem(
            category=item.category,
            agent=agent,
            content=item.content,
            evidence=item.evidence,
            verification=_verification(item),
            source=item.source,
            stage_id=stage_id,
        )
        for item in checked
    ]
    profile.items = kept + new
    await session.flush()
    return profile


def _checked(item: NewItem, documents: Sequence[ApplicantDocument]) -> NewItem | None:
    """근거 문장이 원문에 있으면 실제 문서 이름으로 출처를 맞춰 돌려주고, 없으면 None."""
    if item.evidence is None or not documents:
        return item
    found = evidence_source(item.evidence, documents)
    if found is None:
        return None
    return item.model_copy(update={"source": found.label})


def _verification(item: NewItem) -> Verification:
    """항목의 확인 상태를 정한다."""
    # 1) 근거 문장이 없으면 무엇을 넘겼든 미확인 (근거 없이 '확인됨'을 적지 못하게)
    if item.evidence is None:
        return Verification.UNCONFIRMED
    # 2) 분석 Agent가 넘긴 값이 있으면 그대로, 없으면 근거 있음
    return item.verification or Verification.EVIDENCED
