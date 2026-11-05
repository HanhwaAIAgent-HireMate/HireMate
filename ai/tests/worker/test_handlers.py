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
from hiremate_ai.agents.generation.report import ComposedReport, ReportBundle
from hiremate_ai.api import interview
from hiremate_ai.api.assessment import AnalyzeResult
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.db.analysis_store import AnalysisArtifactStore
from hiremate_ai.db.profile import ProfileStatus
from hiremate_ai.db.profile_store import ProfileScopeError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.worker import handlers as worker_handlers
from hiremate_ai.worker.handlers import PermanentError, job_handlers

CONTRACT_DIR = Path(__file__).resolve().parents[3] / "contract"
# DB에 붙지 않는 세션. Assessment 처리 함수는 저장 함수를 바꿔 끼워 세션을 쓰지 않는다
SESSIONS: async_sessionmaker[AsyncSession] = async_sessionmaker()
REPORT_BUNDLE_JSON = (CONTRACT_DIR / "ReportBundle.json").read_text(encoding="utf-8")
COMPOSED_REPORT_JSON = (CONTRACT_DIR / "ComposedReport.json").read_text(encoding="utf-8")


class MemoryStore:
    def __init__(self) -> None:
        self.artifacts: AnalysisArtifactStore | None = None
        self.reviews: dict[tuple[UUID, str], ApplicationReview] = {}

    async def find(
        self, application_id: UUID, input_hash: str, *, company_id: UUID, recruitment_id: UUID
    ) -> ApplicationReview | None:
        return self.reviews.get((application_id, input_hash))

    async def latest(self, application_id: UUID, *, company_id: UUID, recruitment_id: UUID) -> ApplicationReview | None:
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


async def test_only_application_uses_the_dedicated_batch_model(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    instant = FakeLlm()
    batch = scripted(yumin_script())
    handle = job_handlers(instant, MemoryStore(), SESSIONS, application_llm=batch)["application/analyze"]

    result = await handle(payload(sample_applicants["정유민"], sample_posting, make_rubric()))

    assert result == YUMIN_SUMMARY
    assert not instant.calls


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


async def test_report_compose_reads_only_the_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    """backend가 넣는 리포트 작업: 요청 본문은 POST /agents/report/compose와 같고, 결과는 ComposedReport다."""
    composed = ComposedReport.model_validate_json(COMPOSED_REPORT_JSON)
    received: list[ReportBundle] = []

    async def compose_report(data: ReportBundle, llm: LlmClient) -> ComposedReport:
        received.append(data)
        return composed

    monkeypatch.setattr(worker_handlers, "compose_report", compose_report)
    result = await job_handlers(FakeLlm(), MemoryStore(), SESSIONS)["report/compose"](
        {"bundle": json.loads(REPORT_BUNDLE_JSON)}
    )

    assert received[0].targets == ["A-0017", "A-0026"]
    assert result["spec"]["sections"][0]["blocks"][0]["type"] == "rings"
    assert result["fallback"] is False


async def test_interview_questions_returns_questions_made_by_the_agent(
    monkeypatch: pytest.MonkeyPatch, sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    """면접 전형이 시작될 때 backend가 넣는 작업: 요청 본문은 POST /agents/interview/questions와 같다."""
    received: list[dict[str, Any]] = []

    async def generate_questions(llm: LlmClient, **kwargs: Any) -> list[str]:
        received.append(kwargs)
        from hiremate_ai.agents.generation.interview.types import InterviewQuestionDraft

        texts = ["1분 자기소개 부탁드립니다.", "결제 승인 API에서 맡은 역할을 말해 주세요."]
        kwargs["drafts"].extend(InterviewQuestionDraft(text=text, reason="생성 시 선택한 근거") for text in texts)
        return texts

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

    assert [question["text"] for question in result["questions"]] == [
        "1분 자기소개 부탁드립니다.",
        "결제 승인 API에서 맡은 역할을 말해 주세요.",
    ]
    assert all(question["reason"] == "생성 시 선택한 근거" for question in result["questions"])
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


async def test_application_worker_reviews_each_extracted_document(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    from hiremate_ai.agents.analysis.application.extract import ExtractionCorrections
    from hiremate_ai.llm.fake import LlmCall

    script = yumin_script()

    def response(call: LlmCall) -> Any:
        if call.output is ExtractionCorrections:
            return ExtractionCorrections()
        return script(call)

    llm = FakeLlm(*([response] * 60))
    handle = job_handlers(llm, MemoryStore(), SESSIONS)["application/analyze"]
    applicant = sample_applicants["정유민"]

    await handle(payload(applicant, sample_posting, make_rubric()))

    reviewed = [call for call in llm.calls if call.output is ExtractionCorrections]
    assert len(reviewed) == len([document for document in applicant.documents if document.text.strip()])


async def test_worker_indexes_profile_after_analysis(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    indexed: list[tuple[UUID, UUID, UUID]] = []

    async def index(company_id: UUID, recruitment_id: UUID, application_id: UUID) -> None:
        indexed.append((company_id, recruitment_id, application_id))

    applicant = sample_applicants["정유민"]
    rubric = make_rubric()
    handle = job_handlers(scripted(yumin_script()), MemoryStore(), SESSIONS, profile_indexer=index)[
        "application/analyze"
    ]

    await handle(payload(applicant, sample_posting, rubric))

    assert indexed == [(rubric.company_id, rubric.recruitment_id, applicant.info.application_id)]


async def test_assessment_worker_indexes_updated_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    async def analyze_and_save(data: AssessmentInput, llm: LlmClient, session: AsyncSession) -> AnalyzeResult:
        return AnalyzeResult(status=ProfileStatus.DONE, saved=1, dropped=0)

    indexed: list[tuple[UUID, UUID, UUID]] = []

    async def index(company_id: UUID, recruitment_id: UUID, application_id: UUID) -> None:
        indexed.append((company_id, recruitment_id, application_id))

    monkeypatch.setattr(worker_handlers.assessment, "analyze_and_save", analyze_and_save)
    handle = job_handlers(FakeLlm(), MemoryStore(), SESSIONS, profile_indexer=index)["assessment/analyze"]
    await handle({"input": ASSESSMENT_JSON})

    assert indexed == [
        (
            UUID(ASSESSMENT_JSON["companyId"]),
            UUID(ASSESSMENT_JSON["recruitmentId"]),
            UUID(ASSESSMENT_JSON["applicationId"]),
        )
    ]
