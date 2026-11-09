from datetime import date
from uuid import uuid4

import pytest
from application_context import make_posting, make_rubric, scripted, yumin_script
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.extract import ExtractedFact, ExtractedFacts
from hiremate_ai.agents.analysis.application.reading import DocumentReading, reading_recipe, reading_type
from hiremate_ai.agents.analysis.application.review import ClaimReview, ReviewJudgement
from hiremate_ai.agents.analysis.application.service import analyze_application, review_application_documents
from hiremate_ai.agents.analysis.application.store import DbReviewStore
from hiremate_ai.agents.analysis.interview.types import (
    AnsweredQuestion,
    FindingDraft,
    InterviewAnalysis,
    InterviewAnalysisInput,
    InterviewDraft,
    PreviousInterview,
)
from hiremate_ai.api.interview import analyze_and_save
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.db.analysis_artifact import AnalysisArtifactRecord
from hiremate_ai.db.analysis_store import session_artifacts
from hiremate_ai.db.profile import ItemAgent, ItemCategory, ProfileStatus
from hiremate_ai.db.profile_store import NewItem, ProfileScopeError, save_profile
from hiremate_ai.llm.fake import FakeLlm


async def test_document_artifacts_require_same_original_recipe_and_scope(
    db_session: AsyncSession, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    artifacts = session_artifacts(db_session)
    applicant = sample_applicants["정유민"]
    document = applicant.documents[0]
    scope = {
        "company_id": uuid4(),
        "recruitment_id": applicant.info.recruitment_id,
        "application_id": applicant.info.application_id,
    }
    extracted = ExtractedFacts(
        facts=[
            ExtractedFact(
                kind="EXPERIENCE", statement="근무했어요.", actor="TEAM", evidence=[document.text.splitlines()[0]]
            )
        ]
    )
    await artifacts.save_extraction(**scope, document=document, recipe_hash="a" * 64, extracted=extracted)
    assert await artifacts.find_extraction(**scope, document=document, recipe_hash="a" * 64) == extracted
    assert await artifacts.find_extraction(**scope, document=document, recipe_hash="b" * 64) is None
    assert (
        await artifacts.find_extraction(**{**scope, "company_id": uuid4()}, document=document, recipe_hash="a" * 64)
        is None
    )

    assert (
        await artifacts.find_extraction(
            **scope, document=document.model_copy(update={"text": "new"}), recipe_hash="a" * 64
        )
        is None
    )


async def test_independent_artifact_writer_rejects_existing_profile_of_other_company(
    db_session: AsyncSession, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["정유민"]
    company_id = uuid4()
    await save_profile(
        db_session,
        company_id=company_id,
        recruitment_id=applicant.info.recruitment_id,
        application_id=applicant.info.application_id,
        agent=ItemAgent.APPLICATION,
        items=[],
    )
    with pytest.raises(ProfileScopeError):
        await session_artifacts(db_session).save_extraction(
            company_id=uuid4(),
            recruitment_id=applicant.info.recruitment_id,
            application_id=applicant.info.application_id,
            document=applicant.documents[0],
            recipe_hash="a" * 64,
            extracted=ExtractedFacts(),
        )


async def test_reused_extraction_still_reviews_all_claims_without_persisting_root_output(
    db_session: AsyncSession, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    document = sample_applicants["정유민"].documents[0]
    extracted = ExtractedFacts(
        facts=[
            ExtractedFact(
                kind="EXPERIENCE",
                statement="팀과 함께 근무했어요.",
                actor="TEAM",
                evidence=[document.text.splitlines()[0]],
            )
        ]
    )
    llm = FakeLlm(ReviewJudgement(reviews=[ClaimReview(id="F1", verdict="SUPPORTED")]))
    facts = await review_application_documents(llm, [document], extracted=[extracted])
    assert len(llm.calls) == 1
    assert facts[0].supported is True
    assert facts[0].actor == "TEAM"
    assert await db_session.scalar(select(func.count()).select_from(AnalysisArtifactRecord)) == 0


def interview() -> InterviewAnalysisInput:
    return InterviewAnalysisInput(
        company_id=uuid4(),
        recruitment_id=uuid4(),
        stage_id=uuid4(),
        application_id=uuid4(),
        stage_name="면접",
        previous=[],
        questions=[AnsweredQuestion(text="경험은?", answer="API 캐시를 직접 설계했습니다.")],
    )


async def test_interview_artifacts_revalidate_original_evidence_and_completion(db_session: AsyncSession) -> None:
    artifacts = session_artifacts(db_session)
    data = interview()
    analysis = InterviewAnalysis(
        status=ProfileStatus.DONE,
        dropped=0,
        items=[
            NewItem(
                category=ItemCategory.STRENGTH,
                content="API 캐시를 설계했다.",
                evidence=data.questions[0].answer,
                source="면접 답변",
            )
        ],
    )
    await artifacts.save_interview(data, analysis, recipe_hash="a" * 64)
    assert await artifacts.find_interview(data, recipe_hash="a" * 64) == analysis
    assert await artifacts.find_interview(data.model_copy(update={"stage_id": uuid4()}), recipe_hash="a" * 64) is None
    assert await artifacts.find_interview(data, recipe_hash="b" * 64) is None
    previous = PreviousInterview(stage_name="이전 면접", questions=data.questions)
    assert (
        await artifacts.find_interview(data.model_copy(update={"previous": [previous]}), recipe_hash="a" * 64) is None
    )
    record = await db_session.scalar(select(AnalysisArtifactRecord))
    assert record is not None
    record.payload = {**record.payload, "output": analysis.model_copy(update={"dropped": 1}).model_dump(mode="json")}
    await db_session.flush()
    assert await artifacts.find_interview(data, recipe_hash="a" * 64) is None
    await artifacts.save_interview(data, analysis, recipe_hash="a" * 64)
    db_session.expire_all()
    assert await artifacts.find_interview(data, recipe_hash="a" * 64) == analysis


@pytest.mark.parametrize("change", [{"interrupted": True}, {"status": ProfileStatus.FAILED}, {"dropped": 1}])
async def test_incomplete_interview_results_are_not_saved(db_session: AsyncSession, change: dict[str, object]) -> None:
    artifacts = session_artifacts(db_session)
    data = interview()
    analysis = InterviewAnalysis(status=ProfileStatus.DONE, dropped=0, items=[]).model_copy(update=change)
    await artifacts.save_interview(data, analysis, recipe_hash="a" * 64)
    assert await db_session.scalar(select(func.count()).select_from(AnalysisArtifactRecord)) == 0


async def test_independent_interview_wrapper_reuses_saved_analysis_and_invalidates_context(
    db_session: AsyncSession,
) -> None:
    data = interview()
    draft = InterviewDraft(
        findings=[FindingDraft(kind="CONFIRMED", content="API 캐시를 설계했다.", evidence=data.questions[0].answer)]
    )
    first = FakeLlm(draft)
    await analyze_and_save(data, first, db_session)
    second = FakeLlm()
    await analyze_and_save(data, second, db_session)
    assert len(first.calls) == 1 and not second.calls
    changed = FakeLlm(draft)
    await analyze_and_save(data.model_copy(update={"stage_name": "다른 면접"}), changed, db_session)
    assert len(changed.calls) == 1


async def test_independent_application_saves_document_artifacts_for_readonly_reuse(
    db_session: AsyncSession, sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def borrow() -> AsyncIterator[AsyncSession]:
        yield db_session

    applicant = sample_applicants["정유민"]
    llm = scripted(yumin_script())
    store = DbReviewStore(borrow)
    await analyze_application(
        llm, store, applicant, make_posting(sample_posting), make_rubric(), budget_seconds=20, today=date(2026, 10, 27)
    )
    recipe = reading_recipe(llm)
    assert recipe is not None
    artifacts = session_artifacts(db_session)
    for document in applicant.documents:
        assert (
            await artifacts.find_reading(
                reading_type(document),
                company_id=make_rubric().company_id,
                recruitment_id=applicant.info.recruitment_id,
                application_id=applicant.info.application_id,
                document=document,
                recipe_hash=recipe,
            )
            is not None
        )
    another = scripted(yumin_script())
    await analyze_application(
        another,
        store,
        applicant,
        make_posting(sample_posting),
        make_rubric(),
        budget_seconds=20,
        today=date(2026, 10, 28),
    )
    # 날짜가 바뀌어 다시 분석해도 서류는 다시 읽지 않는다
    assert not any(issubclass(call.output, DocumentReading) for call in another.calls)
