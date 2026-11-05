from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from application_context import make_posting, make_rubric
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.service import analyze_application
from hiremate_ai.agents.analysis.application.store import DbReviewStore, input_hash
from hiremate_ai.agents.analysis.application.types import ApplicationReview
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.llm.fake import FakeLlm

from .test_store import sessions_of


def test_hash_invalidates_date_actual_recipe_and_scope(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    applicant = sample_applicants["정유민"]
    rubric = make_rubric()
    posting = make_posting(sample_posting)

    def digest(**overrides: Any) -> str:
        options = {"today": date(2026, 10, 27), "recipe": {"model": "one"}, **overrides}
        return input_hash(applicant, posting, rubric, "version", **options)

    first = digest()
    assert digest(today=date(2026, 10, 28)) != first
    assert digest(recipe={"model": "two"}) != first
    assert digest(review_extraction=True) != first
    assert (
        input_hash(
            applicant,
            posting,
            rubric.model_copy(update={"company_id": uuid4()}),
            "version",
            today=date(2026, 10, 27),
            recipe={"model": "one"},
        )
        != first
    )


async def test_store_checks_scope_even_when_application_and_hash_match(
    db_session: AsyncSession, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["정유민"]
    rubric = make_rubric()
    store = DbReviewStore(sessions_of(db_session))
    review = ApplicationReview(
        version="current", input_hash="a" * 64, application_id=applicant.info.application_id, readable=True
    )
    await store.save(review, applicant, rubric)
    scope = {"company_id": rubric.company_id, "recruitment_id": rubric.recruitment_id}
    assert await store.find(review.application_id, review.input_hash, **scope) == review
    assert await store.find(review.application_id, review.input_hash, **{**scope, "company_id": uuid4()}) is None
    assert await store.latest(review.application_id, **{**scope, "recruitment_id": uuid4()}) is None


async def test_independent_application_reuses_only_matching_date_and_model(
    db_session: AsyncSession, sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    applicant = sample_applicants["정유민"].model_copy(update={"documents": []})
    store = DbReviewStore(sessions_of(db_session))
    rubric = make_rubric()
    posting = make_posting(sample_posting)
    first = await analyze_application(
        FakeLlm(), store, applicant, posting, rubric, budget_seconds=20, today=date(2026, 10, 27)
    )
    same = await analyze_application(
        FakeLlm(), store, applicant, posting, rubric, budget_seconds=20, today=date(2026, 10, 27)
    )
    later = await analyze_application(
        FakeLlm(), store, applicant, posting, rubric, budget_seconds=20, today=date(2026, 10, 28)
    )
    other = await analyze_application(
        FakeLlm(recipe={"model": "two"}), store, applicant, posting, rubric, budget_seconds=20, today=date(2026, 10, 27)
    )
    assert first == same
    assert len({first.input_hash, later.input_hash, other.input_hash}) == 3


async def test_unknown_model_identity_never_reuses_review(
    db_session: AsyncSession,
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = FakeLlm()
    monkeypatch.setattr(llm, "analysis_recipe", lambda: None)
    applicant = sample_applicants["정유민"].model_copy(update={"documents": []})
    store = DbReviewStore(sessions_of(db_session))
    first = await analyze_application(llm, store, applicant, sample_posting, make_rubric(), budget_seconds=20)
    second = await analyze_application(llm, store, applicant, sample_posting, make_rubric(), budget_seconds=20)
    assert first.input_hash != second.input_hash


def test_review_cache_changes_when_extraction_recipe_changes(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    applicant = sample_applicants["정유민"]
    rubric = make_rubric()
    options: dict[str, Any] = {"today": date(2026, 10, 27), "recipe": {"model": "one"}, "review_extraction": True}

    first = input_hash(applicant, sample_posting, rubric, "version", extraction_version="first", **options)
    second = input_hash(applicant, sample_posting, rubric, "version", extraction_version="second", **options)

    assert first != second


async def test_application_does_not_reuse_review_after_extraction_policy_changes(
    db_session: AsyncSession,
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hiremate_ai.agents.analysis.application import service

    applicant = sample_applicants["정유민"].model_copy(update={"documents": []})
    store = DbReviewStore(sessions_of(db_session))
    monkeypatch.setattr(service, "extraction_recipe", lambda llm, *, review: "first", raising=False)
    first = await analyze_application(FakeLlm(), store, applicant, sample_posting, make_rubric(), budget_seconds=20)
    monkeypatch.setattr(service, "extraction_recipe", lambda llm, *, review: "second")
    second = await analyze_application(FakeLlm(), store, applicant, sample_posting, make_rubric(), budget_seconds=20)

    assert first.input_hash != second.input_hash
