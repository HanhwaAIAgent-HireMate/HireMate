"""작업 유형별 처리 함수. 유형은 ai 서버 경로와 같은 '{agent}/{method}'이고, 처리 함수는 Agent가 공개한 함수를 부른다.

처리 함수는 payload(요청 본문)를 받아 결과(응답 본문)를 돌려준다. 다시 해도 같은 결과일 실패는 PermanentError로 알린다.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.analysis.application import analyze_application
from hiremate_ai.agents.analysis.application.present import to_analysis
from hiremate_ai.agents.analysis.application.service import RubricScopeError
from hiremate_ai.agents.analysis.application.store import ReviewStore
from hiremate_ai.agents.analysis.application.types import AnalyzeRequest
from hiremate_ai.agents.generation.report import write_report
from hiremate_ai.api import assessment, report
from hiremate_ai.config import settings
from hiremate_ai.db.profile_store import ProfileScopeError
from hiremate_ai.llm.client import LlmClient

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class PermanentError(Exception):
    """다시 시도해도 같은 결과인 실패. 워커가 재시도하지 않고 바로 FAILED 결과를 보낸다."""


def job_handlers(
    llm: LlmClient, store: ReviewStore, sessions: async_sessionmaker[AsyncSession]
) -> Mapping[str, Handler]:
    """워커가 처리하는 작업 유형. 자료가 들어올 때 미리 돌리는 분석만 둔다.

    Chat과 화면에서 기다리는 요청은 워커를 거치지 않고 ai 서버 경로로 바로 받는다.
    """

    async def application_analyze(payload: dict[str, Any]) -> dict[str, Any]:
        request = AnalyzeRequest.model_validate(payload)
        try:
            review = await analyze_application(
                llm,
                store,
                request.applicant,
                request.posting,
                request.rubric,
                budget_seconds=settings.application_timeout_seconds,
            )
        except RubricScopeError as error:
            raise PermanentError(str(error)) from error
        return to_analysis(review).model_dump(mode="json")

    async def assessment_analyze(payload: dict[str, Any]) -> dict[str, Any]:
        request = assessment.AnalyzeRequest.model_validate(payload)
        async with sessions() as session:
            try:
                result = await assessment.analyze_and_save(request.input, llm, session)
            except ProfileScopeError as error:
                raise PermanentError(str(error)) from error
        return result.model_dump(mode="json")

    async def report_write(payload: dict[str, Any]) -> dict[str, Any]:
        request = report.WriteRequest.model_validate(payload)
        return (await write_report(request.input, llm)).model_dump(mode="json")

    return {
        "application/analyze": application_analyze,
        "assessment/analyze": assessment_analyze,
        "report/write": report_write,
    }
