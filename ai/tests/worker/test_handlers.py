from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest
from application_context import PREFERRED, UNITS, Script, criterion, judged, make_posting, make_rubric, met, scripted

from hiremate_ai.agents.analysis.application.judge import QualificationJudgement
from hiremate_ai.agents.analysis.application.types import ApplicationReview, ScreeningRubric
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.tools.ncs import NcsUnit
from hiremate_ai.worker.handlers import PermanentError, job_handlers

API = "카드 결제 승인 · 정산 API를 Java와 Spring Boot로 개발했습니다."


class MemoryStore:
    def __init__(self) -> None:
        self.reviews: dict[tuple[UUID, str], ApplicationReview] = {}

    async def units(self, codes: Sequence[str]) -> dict[str, NcsUnit]:
        return {code: UNITS[code] for code in codes if code in UNITS}

    async def find(self, application_id: UUID, input_hash: str) -> ApplicationReview | None:
        return self.reviews.get((application_id, input_hash))

    async def latest(self, application_id: UUID) -> ApplicationReview | None:
        return None

    async def save(self, review: ApplicationReview, applicant: ApplicantDetail, rubric: ScreeningRubric) -> None:
        self.reviews[(review.application_id, review.input_hash)] = review


def payload(applicant: ApplicantDetail, posting: PostingContent, rubric: ScreeningRubric) -> dict[str, object]:
    """backend가 작업에 넣는 요청 본문 (contract/Job.json의 payload)."""
    return {
        "applicant": applicant.model_dump(mode="json"),
        "posting": make_posting(posting).model_dump(mode="json"),
        "rubric": rubric.model_dump(mode="json"),
    }


async def test_application_analyze_returns_backend_summary(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    llm = scripted(
        Script(
            qualify=QualificationJudgement(verdicts=[met(1, API), met(2, API), met(3, API), met(4, API)]),
            prefer={PREFERRED[0]: judged(criterion(1, "MET", API), criterion(2, "MET", API), criterion(3, "NONE"))},
        )
    )
    handle = job_handlers(llm, MemoryStore())["application/analyze"]

    result = await handle(payload(sample_applicants["정유민"], sample_posting, make_rubric()))

    assert result == {
        "careerYears": 0,
        "lastCompany": None,
        "documentScore": 25,
        "passed": True,
        "held": False,
        "shortfalls": ["신입"],
    }


async def test_rubric_of_another_recruitment_is_permanent(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    rubric = make_rubric().model_copy(update={"recruitment_id": uuid4()})
    handle = job_handlers(FakeLlm(), MemoryStore())["application/analyze"]

    with pytest.raises(PermanentError):
        await handle(payload(sample_applicants["정유민"], sample_posting, rubric))
