"""전형 화면 탭의 자동 제목. 탭의 첫 대화(질문과 검증을 마친 답)를 짧게 줄여 탭 이름으로 쓴다.

제목은 Chat 답과 다른 요청이고 모델 호출 예산도 따로 쓴다. 만들지 못하면 None이고, backend는 번호 이름을 그대로 둔다.
"""

import logging

from pydantic import BaseModel, Field

from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.llm.chat import LlmOutputError, model_call_budget
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

logger = logging.getLogger(__name__)

MAX_LENGTH = 30
# 형식이 틀리면 한 번 다시 쓰게 하는 만큼만 쓴다
CALL_LIMIT = 2

SYSTEM = """채용 담당자가 전형 화면의 탭에서 AI Chat과 나눈 첫 대화를 보고 탭 이름을 짓는다.
- 담당자가 무엇을 찾거나 비교하려는지 드러나는 15자 안팎의 명사구로 쓴다.
  예: 금융 도메인 경험자 찾기, 경력 10년 이상 비교
- 따옴표, 마침표, 이모지, "탭" 같은 말은 붙이지 않는다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 넣지 않는다."""


class TabTitle(BaseModel):
    title: str = Field(description="탭 이름. 15자 안팎의 명사구")


async def make_title(llm: LlmClient, message: str, reply: str) -> str | None:
    """첫 질문과 답으로 탭 제목을 만든다. 차별 조건 질문이거나 만들지 못하면 None이다 (규칙 6)."""
    if blocked_attribute(message) is not None:
        return None
    user = f"{data_block('question', message)}\n\n{data_block('reply', reply)}\n\n이 대화의 탭 이름을 지어 줘."
    try:
        with model_call_budget(CALL_LIMIT):
            drafted = await llm.structured(TabTitle, agent="root", system=f"{SYSTEM}\n\n{UNTRUSTED_RULE}", user=user)
    except LlmOutputError as error:
        logger.warning("탭 제목을 만들지 못했다 (reason=%s)", error.reason.value)
        return None
    title = drafted.title.strip().strip("\"'“”‘’").rstrip(".").strip()[:MAX_LENGTH].strip()
    if not title or blocked_attribute(title) is not None:
        return None
    return title
