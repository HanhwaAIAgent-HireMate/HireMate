import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from application_context import YUMIN_SUMMARY, make_posting, make_rubric, scripted, yumin_script
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.analysis.application.types import ApplicationReview, ScreeningRubric
from hiremate_ai.agents.analysis.assessment import AssessmentInput
from hiremate_ai.agents.analysis.interview import InterviewAnalysisInput
from hiremate_ai.agents.generation.report import ReportContent, ReportInput
from hiremate_ai.api import interview
from hiremate_ai.api.assessment import AnalyzeResult
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.db.profile import ProfileStatus
from hiremate_ai.db.profile_store import ProfileScopeError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.worker import handlers as worker_handlers
from hiremate_ai.worker.handlers import PermanentError, job_handlers

CONTRACT_DIR = Path(__file__).resolve().parents[3] / "contract"
# DB에 붙지 않는 세션. Assessment 처리 함수는 저장 함수를 바꿔 끼워 세션을 쓰지 않는다
SESSIONS: async_sessionmaker[AsyncSession] = async_sessionmaker()


class MemoryStore:
    def __init__(self) -> None:
        self.reviews: dict[tuple[UUID, str], ApplicationReview] = {}

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
    handle = job_handlers(scripted(yumin_script()), MemoryStore(), SESSIONS)["application/analyze"]

    result = await handle(payload(sample_applicants["정유민"], sample_posting, make_rubric()))

    assert result == YUMIN_SUMMARY


async def test_each_job_is_one_trace(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent, langsmith: MagicMock
) -> None:
    handle = job_handlers(scripted(yumin_script()), MemoryStore(), SESSIONS)["application/analyze"]

    await handle(payload(sample_applicants["정유민"], sample_posting, make_rubric()))

    created = [call.kwargs for call in langsmith.mock_calls if call[0] == "create_run"]
    root = created[0]
    assert root["name"] == "application/analyze"
    assert len(created) > 1
    assert all(run["trace_id"] == root["id"] for run in created)


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

    async def write_report(data: ReportInput, llm: LlmClient, profiles: object = None) -> ReportContent:
        received.append(data)
        return ReportContent.model_validate(
            {"summary": "요약", "applicantCount": 8, "finalCount": 0, "stages": [stage], "finalists": [], "notes": []}
        )

    monkeypatch.setattr(worker_handlers, "write_report", write_report)
    handle = job_handlers(FakeLlm(), MemoryStore(), SESSIONS)["report/write"]
    report_input = {
        "companyId": "3c1f5e2a-7b4d-4e8a-9f60-1a2b3c4d5e6f",
        "recruitmentId": "7a1e2b3c-4d5e-4f60-8a9b-0c1d2e3f4a51",
        "title": "응용 소프트웨어 엔지니어",
        "applicantCount": 8,
        "stages": [stage],
        "finalists": [],
        "undecided": [0],
    }

    result = await handle({"input": report_input})

    assert received[0].applicant_count == 8
    assert result["applicantCount"] == 8 and result["stages"] == [stage]


async def test_interview_questions_returns_questions_made_by_the_agent(
    monkeypatch: pytest.MonkeyPatch, sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    """면접 전형이 시작될 때 backend가 넣는 작업: 요청 본문은 POST /agents/interview/questions와 같다."""
    received: list[dict[str, Any]] = []

    async def generate_questions(llm: LlmClient, **kwargs: Any) -> list[str]:
        received.append(kwargs)
        return ["1분 자기소개 부탁드립니다.", "결제 승인 API에서 맡은 역할을 말해 주세요."]

    monkeypatch.setattr(worker_handlers, "generate_questions", generate_questions)
    handle = job_handlers(FakeLlm(), MemoryStore(), SESSIONS)["interview/questions"]
    analysis: dict[str, Any] = {
        "conditions": [],
        "notable": [],
        "checks": [],
        "holds": [],
        "criteriaVersion": None,
        "scoreStatus": "HELD",
        "documentScore": None,
        "qualificationStatus": "UNDETERMINED",
        "qualificationRate": None,
        "qualificationScore": None,
        "qualificationMax": 0,
        "preferenceScore": None,
        "preferenceMax": 0,
        "criteria": [],
        "summaries": [],
        "highlights": [],
    }
    interview: dict[str, Any] = {"applicationId": str(uuid4()), "schedule": None, "questions": [], "previous": []}

    result = await handle(
        {
            "applicant": sample_applicants["정유민"].model_dump(mode="json"),
            "posting": sample_posting.model_dump(mode="json"),
            "analysis": {**analysis, "agent": "Application Agent", "stub": False},
            "interview": interview,
            "company": None,
            "focus": None,
        }
    )

    assert result == {"questions": ["1분 자기소개 부탁드립니다.", "결제 승인 API에서 맡은 역할을 말해 주세요."]}
    assert received[0]["applicant"].info.name == "정유민"
    assert received[0]["focus"] is None and received[0]["company"] is None


async def test_interview_analyze_saves_through_the_route_function(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[InterviewAnalysisInput] = []

    async def analyze_and_save(
        data: InterviewAnalysisInput, llm: LlmClient, session: AsyncSession
    ) -> interview.AnalyzeResult:
        received.append(data)
        return interview.AnalyzeResult(status=ProfileStatus.DONE, saved=3, dropped=0)

    monkeypatch.setattr(worker_handlers.interview, "analyze_and_save", analyze_and_save)
    handle = job_handlers(FakeLlm(), MemoryStore(), SESSIONS)["interview-analyst/analyze"]
    sample = json.loads((CONTRACT_DIR / "InterviewAnalysisInput.json").read_text(encoding="utf-8"))

    result = await handle({"input": sample})

    assert result == {"status": "DONE", "saved": 3, "dropped": 0}
    assert received[0].stage_name == "2차 면접" and received[0].previous[0].stage_name == "1차 면접"


async def test_interview_of_another_company_is_permanent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def analyze_and_save(
        data: InterviewAnalysisInput, llm: LlmClient, session: AsyncSession
    ) -> interview.AnalyzeResult:
        raise ProfileScopeError("다른 채용의 프로필이다")

    monkeypatch.setattr(worker_handlers.interview, "analyze_and_save", analyze_and_save)
    handle = job_handlers(FakeLlm(), MemoryStore(), SESSIONS)["interview-analyst/analyze"]
    sample = json.loads((CONTRACT_DIR / "InterviewAnalysisInput.json").read_text(encoding="utf-8"))

    with pytest.raises(PermanentError):
        await handle({"input": sample})
