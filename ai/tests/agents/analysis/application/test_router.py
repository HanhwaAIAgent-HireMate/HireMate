from collections.abc import Iterator
from uuid import UUID

import pytest
from application_context import YUMIN_SUMMARY, make_posting, make_rubric, scripted, yumin_script
from fastapi.testclient import TestClient

from hiremate_ai.agents.analysis.application.router import get_profile_indexer, get_store
from hiremate_ai.agents.analysis.application.types import ApplicationReview, ScreeningRubric
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.db.analysis_store import AnalysisArtifactStore
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.main import app


class MemoryStore:
    """DB 대신 쓰는 저장소. 저장한 결과와 저장 횟수를 들고 있다."""

    def __init__(self) -> None:
        self.artifacts: AnalysisArtifactStore | None = None
        self.reviews: dict[tuple[UUID, str], ApplicationReview] = {}
        self.saved = 0

    async def find(
        self, application_id: UUID, input_hash: str, *, company_id: UUID, recruitment_id: UUID
    ) -> ApplicationReview | None:
        return self.reviews.get((application_id, input_hash))

    async def latest(self, application_id: UUID, *, company_id: UUID, recruitment_id: UUID) -> ApplicationReview | None:
        found = [review for (owner, _), review in self.reviews.items() if owner == application_id]
        return found[-1] if found else None

    async def save(self, review: ApplicationReview, applicant: ApplicantDetail, rubric: ScreeningRubric) -> None:
        self.reviews[(review.application_id, review.input_hash)] = review
        self.saved += 1


@pytest.fixture
def store() -> Iterator[MemoryStore]:
    memory = MemoryStore()

    async def no_index(company_id: UUID, recruitment_id: UUID, application_id: UUID) -> None:
        pass

    app.dependency_overrides[get_store] = lambda: memory
    app.dependency_overrides[get_profile_indexer] = lambda: no_index
    yield memory
    app.dependency_overrides.clear()


def body(applicant: ApplicantDetail, posting: PostingContent, rubric: ScreeningRubric) -> dict[str, object]:
    return {
        "applicant": applicant.model_dump(mode="json"),
        "posting": make_posting(posting).model_dump(mode="json"),
        "rubric": rubric.model_dump(mode="json"),
    }


def yumin_llm() -> FakeLlm:
    return scripted(yumin_script())


def test_analyze_returns_summary_and_reuses_saved_result(
    store: MemoryStore, sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    llm = yumin_llm()
    app.dependency_overrides[get_llm] = lambda: llm
    request = body(sample_applicants["정유민"], sample_posting, make_rubric())
    client = TestClient(app)

    first = client.post("/agents/application/analyze", json=request)
    calls = len(llm.calls)
    second = client.post("/agents/application/analyze", json=request)

    assert first.status_code == 200
    assert first.json() == YUMIN_SUMMARY
    assert second.json() == first.json()
    assert len(llm.calls) == calls
    assert store.saved == 1


def test_candidate_analyst_returns_card_with_holds(
    store: MemoryStore, sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    app.dependency_overrides[get_llm] = lambda: FakeLlm()
    request = body(sample_applicants["윤태오"], sample_posting, make_rubric())

    response = TestClient(app).post("/agents/candidate-analyst/analyze", json=request)

    assert response.status_code == 200
    card = response.json()
    assert card["agent"] == "Application Agent" and card["stub"] is False
    assert card["holds"][0]["source"] == "제출 문서"


def test_rubric_of_another_recruitment_is_rejected(
    store: MemoryStore, sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    app.dependency_overrides[get_llm] = lambda: FakeLlm()
    other = make_rubric().model_copy(update={"recruitment_id": UUID("00000000-0000-4000-8000-000000000001")})

    response = TestClient(app).post(
        "/agents/application/analyze", json=body(sample_applicants["정유민"], sample_posting, other)
    )

    assert response.status_code == 400
    assert store.saved == 0


def test_candidate_card_reuses_worker_review(
    store: MemoryStore, sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    import asyncio

    from hiremate_ai.agents.analysis.application.service import analyze_application

    llm = yumin_llm()
    applicant = sample_applicants["정유민"]
    rubric = make_rubric()
    asyncio.run(
        analyze_application(
            llm,
            store,
            applicant,
            make_posting(sample_posting),
            rubric,
            budget_seconds=20,
            review_extraction=True,
        )
    )
    calls = len(llm.calls)
    app.dependency_overrides[get_llm] = lambda: llm

    response = TestClient(app).post("/agents/candidate-analyst/analyze", json=body(applicant, sample_posting, rubric))

    assert response.status_code == 200
    assert len(llm.calls) == calls
    assert store.saved == 1


def test_application_route_indexes_saved_profile(
    store: MemoryStore, sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    from hiremate_ai.agents.analysis.application import router

    assert hasattr(router, "get_profile_indexer")
    indexed: list[tuple[UUID, UUID, UUID]] = []

    async def index(company_id: UUID, recruitment_id: UUID, application_id: UUID) -> None:
        indexed.append((company_id, recruitment_id, application_id))

    app.dependency_overrides[get_llm] = yumin_llm
    app.dependency_overrides[router.get_profile_indexer] = lambda: index
    applicant = sample_applicants["정유민"]
    rubric = make_rubric()

    response = TestClient(app).post("/agents/application/analyze", json=body(applicant, sample_posting, rubric))

    assert response.status_code == 200
    assert indexed == [(rubric.company_id, rubric.recruitment_id, applicant.info.application_id)]
