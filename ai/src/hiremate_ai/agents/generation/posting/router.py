"""공고 Agent 연동: 본문 수정 /agents/posting/revise, 포스터 대화 /agents/posting/design.

요청 본문은 Java 메서드의 매개변수 이름을 키로 한 JSON이다.
revise는 SSE로 응답한다. 처리 단계(status)를 먼저 보내고 마지막 done 이벤트에 RevisionResult를 담는다.
"""

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import Field

from hiremate_ai.agents.generation.posting import design_poster
from hiremate_ai.agents.generation.posting.poster import PosterContext, PosterProposal
from hiremate_ai.agents.generation.posting.poster_canvas import (
    CanvaMapping,
    CanvaRegion,
    LayoutRegion,
    TemplateLayout,
    map_canva,
    plan_template_layout,
)
from hiremate_ai.agents.generation.posting.reviser import revise_posting
from hiremate_ai.agents.generation.posting.types import (
    PostingDraftContext,
    PostingFocus,
    RevisionResult,
    RevisionStep,
)
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmDep, get_poster_llm
from hiremate_ai.ncs_search.reference import NcsDep

router = APIRouter(prefix="/agents/posting", tags=["posting"])


class ReviseRequest(ContractModel):
    """PostingAgent.revise(posting, writingStyle, request, focus)의 매개변수. 줄을 고르지 않으면 focus가 null이다."""

    posting: PostingDraftContext
    writing_style: str
    request: str
    focus: PostingFocus | None = None


@router.post("/revise", response_class=EventSourceResponse)
async def revise(body: ReviseRequest, llm: LlmDep, ncs: NcsDep) -> AsyncIterator[ServerSentEvent]:
    steps: asyncio.Queue[RevisionStep | None] = asyncio.Queue()

    def report(text: str, depth: int) -> None:
        steps.put_nowait(RevisionStep(text=text, depth=depth))

    async def run() -> RevisionResult:
        try:
            return await revise_posting(
                llm, body.posting, body.writing_style, body.request, body.focus, ncs=ncs, report=report
            )
        finally:
            steps.put_nowait(None)

    task = asyncio.create_task(run())
    try:
        while (step := await steps.get()) is not None:
            yield ServerSentEvent(event="status", raw_data=step.model_dump_json(by_alias=True))
        # 실패하면 done 없이 끝나고, backend는 AI 오류로 답한다
        result = await task
        yield ServerSentEvent(event="done", raw_data=result.model_dump_json(by_alias=True))
    finally:
        # 화면이 연결을 끊으면 수정안 만들기도 멈춘다
        task.cancel()


class DesignRequest(ContractModel):
    context: PosterContext
    request: str = Field(min_length=1, max_length=1000)
    generate_only: bool = False


@router.post("/design")
async def design(body: DesignRequest, llm: LlmDep) -> PosterProposal:
    return await design_poster(get_poster_llm() or llm, body.context, body.request, generate_only=body.generate_only)


class CanvaMapRequest(ContractModel):
    regions: list[CanvaRegion] = Field(max_length=100)


@router.post("/map-canva")
async def map_template(body: CanvaMapRequest, llm: LlmDep) -> CanvaMapping:
    return await map_canva(get_poster_llm() or llm, body.regions)


class TemplateLayoutRequest(ContractModel):
    regions: list[LayoutRegion] = Field(min_length=2, max_length=150)


@router.post("/template-layout")
async def template_layout(body: TemplateLayoutRequest, llm: LlmDep) -> TemplateLayout:
    return await plan_template_layout(get_poster_llm() or llm, body.regions)
