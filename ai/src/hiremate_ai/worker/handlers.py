"""작업 유형별 처리 함수. 유형은 ai 서버 경로와 같은 '{agent}/{method}'이고, 처리 함수는 Agent가 공개한 함수를 부른다.

처리 함수는 payload(요청 본문)를 받아 결과(응답 본문)를 돌려준다. 다시 해도 같은 결과일 실패는 PermanentError로 알린다.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.analysis.application import analyze_application
from hiremate_ai.agents.analysis.application.present import to_analysis
from hiremate_ai.agents.analysis.application.service import RubricScopeError
from hiremate_ai.agents.analysis.application.store import ReviewStore
from hiremate_ai.agents.analysis.application.types import AnalyzeRequest
from hiremate_ai.agents.generation.interview import generate_questions, load_review
from hiremate_ai.agents.generation.interview.router import QuestionsRequest
from hiremate_ai.agents.generation.interview.types import InterviewQuestionDraft
from hiremate_ai.agents.generation.report import compose_report, enrich
from hiremate_ai.agents.generation.report.enrich import DbStageItems
from hiremate_ai.api import assessment, interview, report
from hiremate_ai.config import settings
from hiremate_ai.db.profile_store import ProfileScopeError
from hiremate_ai.llm.batch_state import current_batch_job
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.tracing import traced

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class PermanentError(Exception):
    """다시 시도해도 같은 결과인 실패. 워커가 재시도하지 않고 바로 FAILED 결과를 보낸다."""


def job_handlers(
    llm: LlmClient,
    store: ReviewStore,
    sessions: async_sessionmaker[AsyncSession],
    *,
    application_llm: LlmClient | None = None,
) -> Mapping[str, Handler]:
    """워커가 처리하는 작업 유형. 자료가 들어오거나 전형이 시작될 때 미리 돌리는 분석 · 생성과 리포트를 둔다.

    Chat과 화면에서 기다리는 요청은 워커를 거치지 않고 ai 서버 경로로 바로 받는다.
    """

    # 지원서 하나의 분석 시간 한도는 기술 오류로 다시 시도한 시간까지 합친다 (시도마다 새로 주지 않는다)
    started: dict[str, float] = {}

    async def application_analyze(payload: dict[str, Any]) -> dict[str, Any]:
        request = AnalyzeRequest.model_validate(payload)
        key = str(request.applicant.info.application_id)
        now = asyncio.get_running_loop().time()
        batch = current_batch_job()
        remaining = (
            batch.deadline - time.time()
            if batch is not None
            else settings.application_timeout_seconds - (now - started.setdefault(key, now))
        )
        try:
            if remaining <= 0:
                raise PermanentError("지원서 분석 시간 한도를 다 썼다")
            review = await analyze_application(
                application_llm if application_llm is not None else llm,
                store,
                request.applicant,
                request.posting,
                request.rubric,
                budget_seconds=remaining,
                today=batch.today if batch is not None else None,
            )
        except RubricScopeError as error:
            started.pop(key, None)
            raise PermanentError(str(error)) from error
        except PermanentError:
            started.pop(key, None)
            raise
        started.pop(key, None)
        return to_analysis(review).model_dump(mode="json")

    async def assessment_analyze(payload: dict[str, Any]) -> dict[str, Any]:
        request = assessment.AnalyzeRequest.model_validate(payload)
        async with sessions() as session:
            try:
                result = await assessment.analyze_and_save(request.input, llm, session)
            except ProfileScopeError as error:
                raise PermanentError(str(error)) from error
        return result.model_dump(mode="json")

    async def interview_analyze(payload: dict[str, Any]) -> dict[str, Any]:
        request = interview.AnalyzeRequest.model_validate(payload)
        async with sessions() as session:
            try:
                result = await interview.analyze_and_save(request.input, llm, session)
            except ProfileScopeError as error:
                raise PermanentError(str(error)) from error
        return result.model_dump(mode="json")

    async def report_compose(payload: dict[str, Any]) -> dict[str, Any]:
        # 전형 결과 · 지원자 비교 · 최종 리포트. backend가 만든 묶음만 읽고 DB를 조회하지 않는다
        request = report.ComposeRequest.model_validate(payload)
        bundle = await enrich(request.bundle, store, DbStageItems(sessions))
        return (await compose_report(bundle, llm)).model_dump(mode="json")

    async def interview_questions(payload: dict[str, Any]) -> dict[str, Any]:
        # 면접 전형이 시작될 때 지원자마다 미리 만드는 맞춤 질문 (FR-27). Chat 요청은 ai 서버 경로로 바로 받는다
        request = QuestionsRequest.model_validate(payload)
        # 서류 전형 Agent가 저장한 상세 판정이 있으면 그것으로 빈틈을 고른다 (없으면 요청의 요약으로)
        review = await load_review(
            store, request.applicant, company_id=request.company.company_id if request.company else None
        )
        drafts: list[InterviewQuestionDraft] = []
        await generate_questions(
            llm,
            applicant=request.applicant,
            posting=request.posting,
            analysis=request.analysis,
            interview=request.interview,
            focus=request.focus,
            question_count=request.question_count,
            company=request.company,
            review=review,
            drafts=drafts,
        )
        return {"questions": [draft.model_dump(mode="json") for draft in drafts]}

    handlers: dict[str, Handler] = {
        "application/analyze": application_analyze,
        "interview/questions": interview_questions,
        "assessment/analyze": assessment_analyze,
        "interview-analyst/analyze": interview_analyze,
        "report/compose": report_compose,
    }
    return {job_type: _traced(job_type, handler) for job_type, handler in handlers.items()}


def _traced(job_type: str, handler: Handler) -> Handler:
    """작업 하나의 시도 한 번을 LangSmith 기록 하나로 묶는다 (추적을 켰을 때만)."""

    async def run(payload: dict[str, Any]) -> dict[str, Any]:
        with traced(job_type):
            return await handler(payload)

    return run
