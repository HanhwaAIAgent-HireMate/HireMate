from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from application_context import COMPANY_ID, DESIGN, UNITS, make_posting, make_rubric
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.graph import REVIEW_VERSION
from hiremate_ai.agents.analysis.application.ncs import criteria_of
from hiremate_ai.agents.analysis.application.store import DbReviewStore, Sessions, input_hash
from hiremate_ai.agents.analysis.application.types import ApplicationReview, Note
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.db.ncs_store import load_ncs
from hiremate_ai.db.profile import CandidateProfile, ProfileStatus
from hiremate_ai.tools.ncs import NcsData, NcsDuty


def sessions_of(session: AsyncSession) -> Sessions:
    """테스트 세션을 그대로 빌려준다. 닫지 않아야 테스트가 끝날 때 한꺼번에 되돌릴 수 있다."""

    @asynccontextmanager
    async def borrow() -> AsyncIterator[AsyncSession]:
        yield session

    return borrow


def review_of(applicant: ApplicantDetail, digest: str, **values: object) -> ApplicationReview:
    return ApplicationReview(
        version=REVIEW_VERSION, input_hash=digest, application_id=applicant.info.application_id, readable=True, **values
    )


def test_input_hash_changes_only_with_inputs_that_change_results(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    applicant, posting, rubric = sample_applicants["정유민"], make_posting(sample_posting), make_rubric()
    digest = input_hash(applicant, posting, rubric, UNITS, REVIEW_VERSION)

    assert (
        input_hash(applicant, posting.model_copy(update={"title": "새 제목"}), rubric, UNITS, REVIEW_VERSION) == digest
    )
    assert (
        input_hash(applicant, posting.model_copy(update={"qualifications": ["Git"]}), rubric, UNITS, REVIEW_VERSION)
        != digest
    )
    assert input_hash(applicant, posting, rubric, {}, REVIEW_VERSION) != digest
    assert input_hash(applicant, posting, rubric, UNITS, "다음 버전") != digest


async def test_saves_review_and_profile_then_finds_them(
    db_session: AsyncSession, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["정유민"]
    store = DbReviewStore(sessions_of(db_session))
    review = review_of(applicant, "a" * 64, career_years=4, last_company="한빛카드", passed=True, document_score=31)

    await store.save(review, applicant, make_rubric())
    again = review.model_copy(
        update={"held": True, "document_score": None, "holds": [Note(text="보류", source="이력서")]}
    )
    await store.save(again, applicant, make_rubric())

    assert await store.find(applicant.info.application_id, "a" * 64) == again
    assert await store.find(applicant.info.application_id, "b" * 64) is None
    assert await store.latest(applicant.info.application_id) == again
    profile = await db_session.scalar(
        select(CandidateProfile).where(CandidateProfile.application_id == applicant.info.application_id)
    )
    assert profile is not None
    assert (profile.company_id, profile.status, profile.document_score) == (COMPANY_ID, ProfileStatus.CHECK, None)


async def test_reads_ncs_units_by_code(db_session: AsyncSession) -> None:
    unit = UNITS[DESIGN]
    duty = NcsDuty(code=unit.duty_code, name=unit.subdivision, definition="")
    await load_ncs(db_session, NcsData(source="테스트", retrieved_at="2026-10-21", duties=[duty], units=[unit]))
    store = DbReviewStore(sessions_of(db_session))

    units = await store.units([DESIGN, "2001020218_23v9", "9999999999_23v1"])

    assert set(units) == {DESIGN, "2001020218_23v9"}
    assert [criterion.no for criterion in criteria_of(units[DESIGN])] == ["1-1", "2-1", "3-1"]
    assert units["2001020218_23v9"].code == DESIGN
