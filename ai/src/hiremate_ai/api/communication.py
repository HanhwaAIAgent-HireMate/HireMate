"""Communication Agent 라우터. backend의 CommunicationAgent 메서드와 같은 계약이다."""

from fastapi import APIRouter, HTTPException

from hiremate_ai.agents.generation.communication.writer import NoticeCheckError, NoticeDraftContext, write_notice
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
    try:
        written = await write_notice(llm, body.notice, body.request)
    except NoticeCheckError as error:
        # backend는 오류 응답을 502 AI_UNAVAILABLE로 바꾸고, HR은 본문을 직접 쓴다
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Draft(reply=written.reply, content=written.content)
