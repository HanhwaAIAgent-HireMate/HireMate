"""지원자 프로필 테이블 테스트. Docker로 띄운 PostgreSQL에 실제로 넣고 읽어 본다."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.db.profile import CandidateProfile, ItemAgent, ItemCategory, ProfileItem, ProfileStatus


def jung_yumin_profile() -> CandidateProfile:
    """가상 지원자 1번 정유민을 지원서 분석이 정리했다고 가정한 프로필 (tests/samples/README.md)."""
    return CandidateProfile(
        application_id=uuid4(),
        company_id=uuid4(),
        recruitment_id=uuid4(),
        status=ProfileStatus.DONE,
        career_years=4,
        last_company="한빛카드",
        document_score=85,
        passed=True,
        summary="카드 결제 승인 · 정산 4년",
        items=[
            ProfileItem(
                category=ItemCategory.DOMAIN,
                agent=ItemAgent.APPLICATION,
                content="금융 (카드 결제 · 정산)",
                evidence="한빛카드에서 카드 결제 승인 시스템을 개발했습니다.",
                source="이력서",
            ),
            ProfileItem(
                category=ItemCategory.CHECK,
                agent=ItemAgent.APPLICATION,
                content="대용량 트래픽 처리 수치 확인 필요",
                evidence=None,
                source="이력서",
            ),
        ],
    )


async def test_saves_profile_with_items(db_session: AsyncSession) -> None:
    profile = jung_yumin_profile()
    db_session.add(profile)
    await db_session.commit()
    db_session.expunge_all()  # 메모리에 남은 객체를 비우고 DB에서 다시 읽는다

    saved = await db_session.scalar(
        select(CandidateProfile).where(CandidateProfile.application_id == profile.application_id)
    )

    assert saved is not None
    assert saved.career_years == 4
    assert saved.passed is True
    # 한 번에 저장한 항목은 저장 시각이 같아 순서가 정해지지 않으므로 분류로 찾아 본다
    items = {item.category: item for item in saved.items}
    assert set(items) == {ItemCategory.DOMAIN, ItemCategory.CHECK}
    assert items[ItemCategory.DOMAIN].evidence == "한빛카드에서 카드 결제 승인 시스템을 개발했습니다."
    assert items[ItemCategory.CHECK].evidence is None


async def test_one_profile_per_application(db_session: AsyncSession) -> None:
    first = jung_yumin_profile()
    second = jung_yumin_profile()
    second.application_id = first.application_id
    db_session.add_all([first, second])

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_deleting_profile_deletes_items(db_session: AsyncSession) -> None:
    profile = jung_yumin_profile()
    db_session.add(profile)
    await db_session.flush()

    await db_session.delete(profile)
    await db_session.flush()

    assert await db_session.scalar(select(ProfileItem).where(ProfileItem.profile_id == profile.id)) is None
