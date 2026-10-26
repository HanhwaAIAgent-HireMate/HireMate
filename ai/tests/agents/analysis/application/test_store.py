from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from application_context import COMPANY_ID, make_posting, make_rubric
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.graph import REVIEW_VERSION
from hiremate_ai.agents.analysis.application.store import DbReviewStore, Sessions, input_hash
from hiremate_ai.agents.analysis.application.types import ApplicationReview, Note, ScreeningRubric
from hiremate_ai.contract import ApplicantDetail, CriterionType, PostingContent, QualificationStatus, ScoreStatus
from hiremate_ai.db.application_review import ApplicationReviewRecord
from hiremate_ai.db.profile import CandidateProfile, ProfileStatus


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
    digest = input_hash(applicant, posting, rubric, REVIEW_VERSION)

    def other(
        posting: PostingContent = posting,
        rubric: ScreeningRubric = rubric,
        version: str = REVIEW_VERSION,
    ) -> str:
        return input_hash(applicant, posting, rubric, version)

    assert other(posting=posting.model_copy(update={"title": "새 제목"})) == digest
    assert other(posting=posting.model_copy(update={"qualifications": ["Git"]})) != digest
    # 평가 기준(버전 · 유형)이 바뀌면 저장된 결과를 다시 쓰지 않는다
    assert other(rubric=rubric.model_copy(update={"criteria_version": "test-2"})) != digest
    single = [criterion.model_copy(update={"criterion_type": CriterionType.SINGLE}) for criterion in rubric.criteria]
    assert other(rubric=rubric.model_copy(update={"criteria": single})) != digest
    assert other(version="다음 버전") != digest


async def test_saves_review_and_profile_then_finds_them(
    db_session: AsyncSession, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["정유민"]
    store = DbReviewStore(sessions_of(db_session))
    review = review_of(
        applicant,
        "a" * 64,
        career_years=4,
        last_company="한빛카드",
        qualification_status=QualificationStatus.PASSED,
        score_status=ScoreStatus.CONFIRMED,
        document_score=73.3,
    )

    await store.save(review, applicant, make_rubric())
    again = review.model_copy(
        update={"score_status": ScoreStatus.HELD, "document_score": None, "holds": [Note(text="보류", source="이력서")]}
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


async def test_reviews_saved_in_an_older_shape_are_analyzed_again(
    db_session: AsyncSession, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["정유민"]
    store = DbReviewStore(sessions_of(db_session))
    await store.save(review_of(applicant, "a" * 64), applicant, make_rubric())
    record = await db_session.scalar(select(ApplicationReviewRecord))
    assert record is not None
    # 우대사항을 NCS 수행준거별로 매기던 때의 원본 모양 (항목에 판정 칸이 없다)
    record.review = {**record.review, "criteria": [{"number": 1, "content_no": "1-1", "level": "MET"}]}
    await db_session.flush()

    assert await store.find(applicant.info.application_id, "a" * 64) is None
    assert await store.latest(applicant.info.application_id) is None
