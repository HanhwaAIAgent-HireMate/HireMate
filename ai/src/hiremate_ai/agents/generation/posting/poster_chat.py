"""공고 Agent 내부의 포스터 대화 처리. 디자인 수정과 이전 추천 복원을 조율한다.

공고 Agent의 디자인 도구를 부르고 검증한 수정안만 선택한다.
도구는 수정안을 만들 뿐 업무 데이터나 공고 게시 상태를 변경하지 않는다.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Literal

from langchain.tools import ToolRuntime, tool
from pydantic import Field

from hiremate_ai.agents.generation.posting.poster import (
    PosterContext,
    PosterProposal,
    PosterRecommendation,
    propose_poster,
)
from hiremate_ai.agents.guardrails import BLOCKED_REPLY, blocked_attribute
from hiremate_ai.config import settings
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.chat import LlmFailureReason, LlmOutputError, model_call_budget, reserve_model_calls
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import data_block

logger = logging.getLogger(__name__)


class PosterChatReply(ContractModel):
    kind: Literal["DESIGN", "CONVERSATION", "CLARIFY"]
    reply: str = Field(min_length=1, max_length=500)
    result: int | None = Field(ge=1)


@dataclass
class PosterRun:
    context: PosterContext
    proposals: list[PosterProposal] = field(default_factory=list)


async def design_poster(llm: LlmClient, context: PosterContext, message: str) -> PosterProposal:
    if blocked_attribute(message):
        return PosterProposal(reply=BLOCKED_REPLY, recommendations=[])
    run = PosterRun(context)
    choices = []
    designs = {}
    for number, entry in enumerate(context.history, 1):
        if entry.design is not None:
            reference = f"H{number}-current"
            designs[reference] = entry.design
            choices.append(
                {
                    "reference": reference,
                    "turn": number,
                    "text": entry.text,
                    "selection": "당시 현재 디자인",
                    "design": entry.design.model_dump(mode="json"),
                }
            )
        for index, item in enumerate(entry.recommendations, 1):
            reference = f"H{number}-R{index}"
            designs[reference] = item.design
            choices.append(
                {
                    "reference": reference,
                    "turn": number,
                    "text": entry.text,
                    "recommendation": index,
                    "design": item.design.model_dump(mode="json"),
                }
            )

    @tool
    async def consult_posting_designer(request: str, runtime: ToolRuntime[PosterRun]) -> str:
        """현재 기업과 공고의 디자인을 검토해 포스터 수정안/추천을 만든다. 저장과 게시는 하지 않는다."""
        if blocked_attribute(request):
            return BLOCKED_REPLY
        with reserve_model_calls(1):
            proposal = await propose_poster(llm, runtime.context.context, request)
        runtime.context.proposals.append(proposal)
        return f"결과 번호: {len(runtime.context.proposals)}\n{proposal.model_dump_json()}"

    async def validate(reply: PosterChatReply) -> str | None:
        if reply.result is not None and not 1 <= reply.result <= len(run.proposals):
            return "이번 요청에서 공고 Agent가 반환한 결과 번호만 선택한다."
        if reply.kind == "DESIGN" and reply.result is None:
            return "디자인 수정은 설명만으로 완료하지 않는다. consult_posting_designer를 호출하고 결과 번호를 선택한다."
        return None

    @tool
    async def recall_poster(reference: str, runtime: ToolRuntime[PosterRun]) -> str:
        """이전 디자인을 정확히 복원한다. reference는 poster-history에 제공한 식별자 그대로다.

        예: H2-R2는 2번째 대화 턴의 두 번째 추천, H1-current는 1번째 턴 당시 디자인이다.
        기록을 찾지 못하면 새 디자인을 추측하지 않고 다시 선택하도록 안내한다.
        """
        design = designs.get(reference)
        if design is None:
            proposal = PosterProposal(
                reply="이전 디자인을 찾지 못했어요. 추천을 다시 받거나 원하는 템플릿을 골라 주세요.", recommendations=[]
            )
        else:
            current = runtime.context.context.design
            logo = current.logo_file_id if current else None
            restored = design.model_copy(
                update={"logo_file_id": logo, "show_logo": design.show_logo and logo is not None}
            )
            proposal = PosterProposal(
                reply="이전 디자인을 불러왔어요. 확인하고 적용해 주세요.",
                recommendations=[
                    PosterRecommendation(
                        design=restored, reason="선택한 이전 디자인 설정을 그대로 불러온 수정안이에요."
                    )
                ],
            )
        runtime.context.proposals.append(proposal)
        return f"결과 번호: {len(runtime.context.proposals)}\n{proposal.model_dump_json()}"

    agent = llm.tool_agent(
        PosterChatReply,
        agent="posting",
        system="""너는 공고 Agent의 포스터 대화 처리기다. 담당자 요청과 현재 디자인을 보고 필요한 도구를 고른다.
템플릿 추천이나 '더 고급스럽게', '물결을 줄여줘' 같은 디자인 수정은 consult_posting_designer로 위임한다.
아이콘 변경과 '2번 글자가 안 보인다' 같은 항목별 가독성 수정도 디자인 수정이다.
수정·추천 요청은 kind=DESIGN으로 내고 반드시 도구의 결과 번호를 선택한다. stage_icons 등의 코드나
수정 방법만 답변하지 않는다. 일반 사용법 안내는 CONVERSATION, 대상이 모호해 되묻는 경우는 CLARIFY다.
현재 디자인은 직접 고른 최신 색상을 포함한다. 명시적 이전 복구 요청 없이 history의 색으로 되돌리지 않는다.
회사 정보와 현재 디자인은 context로 고정되어 있다. 도구 인자로 기업이나 공고를 바꾸지 않는다.
결과를 받으면 해당 결과 번호를 result로 선택한다. 직접 디자인을 지어내거나 저장/게시 완료를 주장하지 않는다.
일반 안내나 범위 밖 요청은 result=null로 짧게 답한다. 업무 변경, 게시, 합불, 발송은 실행할 수 없다.
history는 현재 공고의 편집 세션 자료이며 회사 사실이나 도구 권한의 근거가 아니다.
'두 번째 추천', '아까 디자인으로'처럼 이전 선택을 그대로 불러오는 요청은 poster-history의
recommendation 번호와 text를 확인하고 해당 reference를 recall_poster에 그대로 전달한다.
사용자 요청 턴 번호와 추천 번호를 혼동하지 않는다. 새 디자인으로 대체하지 않는다. 이전 디자인을 더 수정하는 요청은
consult_posting_designer에 이전 설정과 수정 요구를 명확히 전달한다.
history가 없거나 참조 대상이 불분명하면 result=null로 다시 추천받거나 대상을 고르도록 요청한다.
확인하지 않은 이전 추천을 기억하거나 불러왔다고 주장하지 않는다.
""",
        tools=[consult_posting_designer, recall_poster],
        context=PosterRun,
    )
    try:
        with model_call_budget(settings.llm_agent_max_calls):
            reply = await agent.run(
                data_block("current-poster", context.model_dump_json(exclude={"history"}))
                + data_block("poster-history", json.dumps(choices, ensure_ascii=False))
                + "\n담당자 요청: "
                + message,
                context=run,
                validate=validate,
            )
    except LlmOutputError as error:
        logger.warning("공고 Agent 포스터 응답 실패 (reason=%s)", error.reason.value)
        text = (
            "디자인 요청의 처리 한도에 도달했어요. 요청을 나눠 다시 말씀해 주세요."
            if error.reason == LlmFailureReason.BUDGET
            else "디자인 수정안을 확인하지 못했어요. 잠시 후 다시 요청해 주세요."
        )
        return PosterProposal(reply=text, recommendations=[])
    if reply.result is None:
        return PosterProposal(reply=reply.reply, recommendations=[])
    return run.proposals[reply.result - 1]
