"""LLM_EVAL=true일 때 실제 모델로 Chat 면접 질문의 NCS 참고를 검사한다.

NCS 표(scripts/ncs_load.py로 적재)와 질의 임베딩 서비스(uv run --group ncs python -m hiremate_ai.ncs_search)가 필요하다.
지원자는 tests/samples의 가상 지원자, 공고는 가상 결제 백엔드 공고다.
"""

import re
import time
from uuid import uuid4

import httpx
import pytest

from hiremate_ai.agents.generation.interview import generate_questions
from hiremate_ai.agents.generation.interview import ncs as interview_ncs
from hiremate_ai.agents.generation.interview.types import CitedQuestionDraft, InterviewQuestionDraft
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CandidateAnalysis, Finding, InterviewView, PostingContent
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm
from hiremate_ai.ncs_search.reference import get_ncs


def _ready() -> str | None:
    """평가를 돌릴 수 없는 이유. 돌릴 수 있으면 None이다."""
    if not settings.llm_eval:
        return "LLM_EVAL=true일 때 실제 모델로 평가한다"
    try:
        httpx.get(f"{settings.ncs_embed_url}/health", timeout=3).raise_for_status()
    except httpx.HTTPError:
        return "NCS 질의 임베딩 서비스가 꺼져 있다"
    return None


pytestmark = [
    pytest.mark.skipif((reason := _ready()) is not None, reason=reason or ""),
    pytest.mark.asyncio(loop_scope="module"),
]

REQUESTS = (
    "배치 처리 쪽 직무 지식 질문",
    "외부 시스템과 연동하는 인터페이스 설계 지식 질문",
    "서버 프로그램의 예외 처리 판단 기준을 묻는 질문",
)
# 지원자가 그 일을 했다고 전제하는 말투 (판정 모델과 별도로 한 번 더 본다)
PAST = re.compile(r"하셨|했던|했을\s*때|당시|그때|맡으셨|겪으셨")
NUMBER = re.compile(r"\d+")


class MemoryLog:
    async def record(self, record: CallRecord) -> None:
        print({"agent": record.agent, "status": record.status})


def analysis() -> CandidateAnalysis:
    return CandidateAnalysis(
        conditions=[],
        notable=[Finding(text="Spring Boot로 결제 승인 · 정산 API를 개발했습니다.", source="이력서")],
        checks=[],
        holds=[],
        criteria_version=None,
        criteria=[],
        summaries=[],
        highlights=[],
        agent="Application Agent",
        stub=False,
    )


async def test_interview_ncs_questions(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    interview_ncs.clear_cache()
    llm = build_llm(MemoryLog())
    rows: list[tuple[str, bool, str, str]] = []
    for request in REQUESTS:
        drafts: list[InterviewQuestionDraft] = []
        started = time.monotonic()
        await generate_questions(
            llm,
            applicant=sample_applicants["정유민"],
            posting=sample_posting,
            analysis=analysis(),
            interview=InterviewView(application_id=uuid4(), schedule=None, questions=[], previous=[]),
            focus=request,
            question_count=1,
            drafts=drafts,
            ncs="HELPFUL",
            ncs_reference=get_ncs(),
        )
        cited = [draft for draft in drafts if isinstance(draft, CitedQuestionDraft) and draft.ncs_cited]
        problems = []
        for draft in cited:
            source = (draft.reason or "").split("원문: ", 1)[-1]
            if PAST.search(draft.text):
                problems.append("경험 전제")
            if any(number not in source for number in NUMBER.findall(draft.text)):
                problems.append("없는 수치")
        text = cited[0].text if cited else "-"
        rows.append((request, bool(cited) and not problems, f"{time.monotonic() - started:.1f}s", "; ".join(problems)))
        print("\n", request, "→", text, "\n", cited[0].reason if cited else "(인용 없음)")
    print("\n| 요청 | 통과 | 시간 | 어긋난 점 |\n|---|---|---|---|")
    for request, passed, seconds, missed in rows:
        print(f"| {request} | {'O' if passed else 'X'} | {seconds} | {missed} |")
    # 인용한 질문은 경험을 전제하거나 수치를 만들면 안 된다. 인용 자체는 검색 품질에 따라 빠질 수 있어 2/3 이상을 본다
    assert all(not missed for *_, missed in rows)
    assert sum(passed for _, passed, *_ in rows) >= 2
