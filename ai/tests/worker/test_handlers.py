from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest
from application_context import PREFERRED, UNITS, Script, criterion, judged, make_posting, make_rubric, met, scripted
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.analysis.application.judge import QualificationJudgement
from hiremate_ai.agents.analysis.application.types import ApplicationReview, ScreeningRubric
from hiremate_ai.agents.analysis.assessment import AssessmentInput
from hiremate_ai.agents.generation.report import ReportContent, ReportInput
from hiremate_ai.api.assessment import AnalyzeResult
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.db.profile import ProfileStatus
from hiremate_ai.db.profile_store import ProfileScopeError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.tools.ncs import NcsUnit
from hiremate_ai.worker import handlers as worker_handlers
from hiremate_ai.worker.handlers import PermanentError, job_handlers

API = "카드 결제 승인 · 정산 API를 Java와 Spring Boot로 개발했습니다."
# DB에 붙지 않는 세션. Assessment 처리 함수는 저장 함수를 바꿔 끼워 세션을 쓰지 않는다
SESSIONS: async_sessionmaker[AsyncSession] = async_sessionmaker()


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
    handle = job_handlers(llm, MemoryStore(), SESSIONS)["application/analyze"]

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
    handle = job_handlers(FakeLlm(), MemoryStore(), SESSIONS)["application/analyze"]

    with pytest.raises(PermanentError):
        await handle(payload(sample_applicants["정유민"], sample_posting, rubric))


ASSESSMENT_JSON: dict[str, Any] = {
    "companyId": str(uuid4()),
    "recruitmentId": str(uuid4()),
    "stageId": str(uuid4()),
    "applicationId": str(uuid4()),
    "stageName": "직무역량 평가",
    "total": 82.5,
    "areas": {"의사소통능력": 80, "수리능력": None},
    "grade": "B",
    "submission": None,
    "url": None,
    "note": "코드 구조 설명이 명확했음",
}


async def test_assessment_analyze_saves_through_the_route_function(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[AssessmentInput] = []

    async def analyze_and_save(data: AssessmentInput, llm: LlmClient, session: AsyncSession) -> AnalyzeResult:
        received.append(data)
        return AnalyzeResult(status=ProfileStatus.DONE, saved=2, dropped=1)

    monkeypatch.setattr(worker_handlers.assessment, "analyze_and_save", analyze_and_save)
    handle = job_handlers(FakeLlm(), MemoryStore(), SESSIONS)["assessment/analyze"]

    result = await handle({"input": ASSESSMENT_JSON})

    assert result == {"status": "DONE", "saved": 2, "dropped": 1}
    assert str(received[0].application_id) == ASSESSMENT_JSON["applicationId"]
    assert received[0].areas["수리능력"] is None


async def test_assessment_of_another_company_is_permanent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def analyze_and_save(data: AssessmentInput, llm: LlmClient, session: AsyncSession) -> AnalyzeResult:
        raise ProfileScopeError("다른 채용의 프로필이다")

    monkeypatch.setattr(worker_handlers.assessment, "analyze_and_save", analyze_and_save)
    handle = job_handlers(FakeLlm(), MemoryStore(), SESSIONS)["assessment/analyze"]

    with pytest.raises(PermanentError):
        await handle({"input": ASSESSMENT_JSON})


async def test_report_write_returns_report_content(monkeypatch: pytest.MonkeyPatch) -> None:
    stage = {"name": "서류 전형", "target": 8, "pass": 4, "fail": 4}
    received: list[ReportInput] = []

    async def write_report(data: ReportInput, llm: LlmClient) -> ReportContent:
        received.append(data)
        return ReportContent.model_validate(
            {"summary": "요약", "applicantCount": 8, "finalCount": 0, "stages": [stage], "finalists": [], "notes": []}
        )

    monkeypatch.setattr(worker_handlers, "write_report", write_report)
    handle = job_handlers(FakeLlm(), MemoryStore(), SESSIONS)["report/write"]
    report_input = {
        "title": "응용 소프트웨어 엔지니어",
        "applicantCount": 8,
        "stages": [stage],
        "finalists": [],
        "undecided": [0],
    }

    result = await handle({"input": report_input})

    assert received[0].applicant_count == 8
    assert result["applicantCount"] == 8 and result["stages"] == [stage]
