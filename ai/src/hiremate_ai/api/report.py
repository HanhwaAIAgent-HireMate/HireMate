from fastapi import APIRouter

from hiremate_ai.agents.generation.report import ReportContent, ReportInput, write_report
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmDep

router = APIRouter(prefix="/agents/report")


class WriteRequest(ContractModel):
    """ReportAgent.write(ReportInput input)의 매개변수."""

    input: ReportInput


@router.post("/write")
async def write(request: WriteRequest, llm: LlmDep) -> ReportContent:
    return await write_report(request.input, llm)
