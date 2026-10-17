"""Communication Agent 라우터. backend의 CommunicationAgent 메서드와 같은 계약이다."""

from fastapi import APIRouter

from hiremate_ai.agents.generation.communication.writer import NoticeDraftContext, write_notice
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmDep

router = APIRouter()


class WriteRequest(ContractModel):
    """CommunicationAgent.write(notice, request)의 매개변수. request는 HR의 수정 요청이고 처음 쓸 때는 null이다."""

    notice: NoticeDraftContext
    request: str | None = None


class Draft(ContractModel):
    """CommunicationAgent.Draft."""

    reply: str
    content: str


@router.post("/agents/communication/write")
async def write(body: WriteRequest, llm: LlmDep) -> Draft:
    written = await write_notice(llm, body.notice, body.request)
    return Draft(reply=written.reply, content=written.content)
