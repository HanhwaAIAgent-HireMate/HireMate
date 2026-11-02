from fastapi import APIRouter

from hiremate_ai.agents.analysis.application.router import StoreDep
from hiremate_ai.agents.generation.report import (
    ComposedReport,
    DistributionFacts,
    DistributionNote,
    ReportBundle,
    compose_report,
    enrich,
    explain_distribution,
)
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


class ExplainRequest(ContractModel):
    """ReportAgent.explain(ReportDistribution distribution)의 매개변수. 지원자 이름 없이 숫자와 항목 글만 온다."""

    distribution: DistributionFacts


@router.post("/explain")
async def explain(request: ExplainRequest, llm: LlmDep) -> DistributionNote:
    """서류 전형 분포 해설. 화면이 기다리는 요청이라 워커를 거치지 않고 바로 답한다."""
    return await explain_distribution(request.distribution, llm)
