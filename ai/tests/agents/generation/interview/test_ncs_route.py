import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from ncs_context import UNIT, FakeNcs
from pydantic import BaseModel

from hiremate_ai.agents.analysis.application.router import get_store
from hiremate_ai.agents.analysis.application.types import ApplicationReview
from hiremate_ai.agents.generation.interview import ncs as interview_ncs
from hiremate_ai.agents.generation.interview.agent import QuestionDraft, _DraftQuestion
from hiremate_ai.agents.generation.interview.ncs import NcsCheck, NcsVerdict
from hiremate_ai.contract import ApplicantDetail, CandidateAnalysis, Finding, InterviewView, PostingContent
from hiremate_ai.llm.client import get_llm
from hiremate_ai.llm.fake import FakeLlm, LlmCall
from hiremate_ai.main import app
from hiremate_ai.ncs_search.cite import NcsQuery
from hiremate_ai.ncs_search.reference import get_ncs
from hiremate_ai.ncs_search.types import NcsTask

GOOD = (
    "하위 시스템끼리 연동하는 배치 프로그램이 중간에 실패한다면, "
    "다시 돌릴 때 같은 데이터가 두 번 처리되지 않게 하는 기준을 설명해 주세요."
)
OTHER = "결제 승인 API를 만들며 맡으신 부분과 테스트로 확인한 결과를 구체적으로 설명해 주세요."
BATCH = NcsTask(
    chunk_id="chunk:batch",
    duty_name="응용SW엔지니어링",
    unit_code=UNIT,
    unit_name="서버프로그램 구현",
    task_name="배치 프로그램 구현하기",
    sentences=["하위 시스템 간의 연동 시, 안정적이고 안전하게 동작할 수 있는 배치 프로그램을 구현 한다"],
)


class NoReview:
    async def latest(
        self, application_id: object, *, company_id: UUID, recruitment_id: UUID
    ) -> ApplicationReview | None:
        return None


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    interview_ncs.clear_cache()
    yield
    interview_ncs.clear_cache()
    app.dependency_overrides.clear()


def reply(call: LlmCall) -> BaseModel:
    if call.output is NcsQuery:
        return NcsQuery(tasks=["배치 프로그램을 구현 한다"], units=[UNIT])
    if call.output is NcsCheck:
        return NcsCheck(verdicts=[NcsVerdict(index=0, verdict="supports", assumes_experience=False)])
    drafts = [
        _DraftQuestion(gap_id=gap_id, question=GOOD, purpose="재처리 기준", source_id="N1")
        if "[N1]" in call.user and gap_id == "G1"
        else _DraftQuestion(gap_id=gap_id, question=OTHER, purpose="본인 역할")
        for gap_id in re.findall(r"gap_id: (G\d+)", call.user)
    ]
    return QuestionDraft(questions=drafts)


def body(applicant: ApplicantDetail, posting: PostingContent, interview: InterviewView, **extra: Any) -> dict[str, Any]:
    analysis = CandidateAnalysis(
        conditions=[],
        notable=[Finding(text="Spring Boot와 MySQL로 결제 승인 · 취소 API를 만들었습니다.", source="이력서")],
        checks=[],
        holds=[],
        criteria_version=None,
        criteria=[],
        summaries=[],
        highlights=[],
        agent="Application Agent",
        stub=False,
    )
    return {
        "applicant": applicant.model_dump(mode="json"),
        "posting": posting.model_dump(mode="json"),
        "analysis": analysis.model_dump(mode="json"),
        "interview": interview.model_dump(mode="json"),
        "focus": "배치 처리 쪽 직무 지식 질문",
        "questionCount": 1,
        **extra,
    }


async def post(payload: dict[str, Any], ncs: FakeNcs | None = None) -> httpx.Response:
    app.dependency_overrides[get_llm] = lambda: FakeLlm(*([reply] * 20))
    app.dependency_overrides[get_store] = lambda: NoReview()
    if ncs is not None:
        app.dependency_overrides[get_ncs] = lambda: ncs
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/agents/interview/questions", json=payload)


async def test_skip_route_response_unchanged(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    interview = InterviewView(application_id=uuid4(), schedule=None, questions=[], previous=[])
    applicant = sample_applicants["이도윤"]
    reference = FakeNcs(found=[BATCH])

    plain = await post(body(applicant, sample_posting, interview), reference)
    skipped = await post(body(applicant, sample_posting, interview, ncs="SKIP"), reference)

    assert plain.status_code == skipped.status_code == 200
    assert skipped.json() == plain.json()
    assert all("ncsCited" not in item for item in plain.json())
    assert reference.searches == []


async def test_ncs_route_marks_cited(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    interview = InterviewView(application_id=uuid4(), schedule=None, questions=[], previous=[])

    response = await post(
        body(sample_applicants["이도윤"], sample_posting, interview, ncs="HELPFUL"), FakeNcs(found=[BATCH])
    )

    assert response.status_code == 200
    items = response.json()
    assert [item["text"] for item in items if item["ncsCited"]] == [GOOD]
    assert all(set(item) == {"text", "reason", "interviewerRole", "ncsCited"} for item in items)
    assert "출처: NCS 응용SW엔지니어링 › 서버프로그램 구현 › 배치 프로그램 구현하기" in next(
        item["reason"] for item in items if item["ncsCited"]
    )


async def test_requested_without_match_marks_none(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    interview = InterviewView(application_id=uuid4(), schedule=None, questions=[], previous=[])

    response = await post(
        body(sample_applicants["이도윤"], sample_posting, interview, ncs="REQUESTED"), FakeNcs(found=[])
    )

    assert response.status_code == 200
    assert response.json() and not any(item.get("ncsCited") for item in response.json())


async def test_null_ncs_is_skip(sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent) -> None:
    """backend는 값이 없는 칸을 null로 보낸다. null은 SKIP이고 응답이 지금과 같다."""
    interview = InterviewView(application_id=uuid4(), schedule=None, questions=[], previous=[])
    applicant = sample_applicants["이도윤"]
    reference = FakeNcs(found=[BATCH])

    plain = await post(body(applicant, sample_posting, interview), reference)
    nulled = await post(body(applicant, sample_posting, interview, ncs=None), reference)

    assert nulled.status_code == 200
    assert nulled.json() == plain.json()
    assert reference.searches == []


def test_worker_payload_with_null_ncs_validates() -> None:
    from hiremate_ai.agents.generation.interview.router import QuestionsRequest

    sample = json.loads((Path(__file__).resolve().parents[5] / "contract/InterviewQuestionsRequest.json").read_text())
    sample["ncs"] = None

    assert QuestionsRequest.model_validate(sample).ncs == "SKIP"
