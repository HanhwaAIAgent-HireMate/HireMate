from fastapi import APIRouter

from hiremate_ai.agents.analysis.application.router import StoreDep
from hiremate_ai.agents.generation.report import ComposedReport, ReportBundle, compose_report, enrich
from hiremate_ai.agents.generation.report.enrich import DbStageItems
from hiremate_ai.contract import ContractModel
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.client import LlmDep

router = APIRouter(prefix="/agents/report")


class ComposeRequest(ContractModel):
    """ReportAgent.compose(ReportBundle bundle)의 매개변수. 묶음 밖 자료는 읽지 않는다."""

    bundle: ReportBundle


@router.post("/compose")
async def compose(request: ComposeRequest, llm: LlmDep, store: StoreDep) -> ComposedReport:
    bundle = await enrich(request.bundle, store, DbStageItems(session_factory()))
    return await compose_report(bundle, llm)
