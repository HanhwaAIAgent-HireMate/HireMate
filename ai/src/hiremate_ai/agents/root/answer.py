"""B 분석 · 생성. 모델이 조회 도구를 골라 부르며 자료를 확인하고(도구 루프), 코드가 근거를 원문과 맞춰 본다 (기획 §11).

선택 지원자나 채용 상태는 바꾸지 않고 대화로만 답한다. 근거가 원문에 없으면 버리고 확인 필요로 둔다 (규칙 7).
"""

import asyncio
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.agents.guardrails import evidence_source
from hiremate_ai.agents.root.route import RootRoute
from hiremate_ai.agents.root.targets import Targets
from hiremate_ai.agents.root.toolkit import RootToolContext, RootToolkit, candidate_ref, resolve_ref, scope_of
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, ChatItem, ChatPlan, Intent
from hiremate_ai.contract import DocumentType, StageType
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient

# backend는 ai 응답을 60초 기다리고 분류 호출이 앞에 있다
ANSWER_TIMEOUT_SECONDS = 45.0
TEXT_LENGTH = 120
NOT_FINISHED = "자료를 다 확인하지 못했어요. 질문을 좁혀 다시 물어봐 주세요."
INTERVIEW_SOURCE = "면접 기록"
# 하위 Agent를 감싼 도구. 부르면 답의 agents에 이 이름이 들어간다
SUB_AGENT_TOOLS = {"analyze_application": "Application Agent", "analyze_assessment": "Assessment Agent"}

_DOCUMENT_LABELS = {document.label: document for document in DocumentType}
_STAGE_LABELS = {StageType.DOCUMENT: "서류", StageType.ASSESSMENT: "평가", StageType.INTERVIEW: "면접"}

ANSWER_SYSTEM = """너는 채용 담당자의 질문에 지원자 자료를 확인해 답한다.
도구로 필요한 자료만 골라 읽고, 근거가 모이면 답한다.

- 근거가 있는 내용만 말한다. 자료가 없거나 확인하지 못한 점은 status=CHECK로 나눈다.
- 서류와 평가 · 면접을 함께 묻는 질문이면 그 자료를 모두 확인한다.
- 지원자는 C1 같은 번호로만 가리킨다. 도구 인자와 답의 candidate 모두 번호를 쓴다.
- 근거 문장(evidence.sentence)은 도구 결과의 문장을 글자 그대로 옮기고, 출처(source)를 적는다.
  출처는 이력서, 자기소개서, 포트폴리오, 자격증, 면접 기록, 전형 결과, 회사 소개, 공고 가운데 하나다.
- 채용 결정, 점수 변경, 상태 변경은 하지 않는다. 그런 요청은 담당자가 화면에서 한다고 안내한다.
- message는 담당자에게 하는 짧은 답이고, items는 지원자별 · 항목별 근거다."""


class AnswerEvidence(BaseModel):
    sentence: str = Field(description="근거 문장. 도구 결과의 문장을 글자 그대로")
    source: str = Field(
        description="출처: 이력서, 자기소개서, 포트폴리오, 자격증, 면접 기록, 전형 결과, 회사 소개, 공고"
    )


class AnswerItem(BaseModel):
    candidate: str | None = Field(default=None, description="지원자 번호(C1 같은). 특정 지원자가 아니면 비운다")
    label: str = Field(description="항목 이름. 예: 강점, 확인할 점, 인재상")
    text: str = Field(description="한 줄 설명")
    status: Literal["OK", "CHECK"] = Field(description="근거가 충분하면 OK, 확인이 필요하면 CHECK")
    evidence: list[AnswerEvidence] = Field(default=[], description="근거 문장과 출처")


class RootAnswer(BaseModel):
    message: str = Field(description="담당자에게 하는 답")
    items: list[AnswerItem] = Field(default=[], description="지원자별 · 항목별 근거")


async def plan_answer(
    llm: LlmClient, route: RootRoute, context: ChatContext, targets: Targets, toolkit: RootToolkit
) -> ChatPlan:
    scope = scope_of(context)
    agent = llm.tool_agent(
        RootAnswer, agent="root", system=ANSWER_SYSTEM, tools=toolkit.answer_tools, context=RootToolContext
    )
    try:
        async with asyncio.timeout(ANSWER_TIMEOUT_SECONDS):
            answered = await agent.run(answer_prompt(context, targets), context=scope)
    except (LlmOutputError, TimeoutError):
        return ChatPlan.answer(Intent.CLARIFY, NOT_FINISHED)
    items, sources = verify_items(answered.items, context)
    return ChatPlan.answer(Intent.ANSWER, answered.message, items, sources, sub_agents(scope.called))


def answer_prompt(context: ChatContext, targets: Targets) -> str:
    previous = ", ".join(_STAGE_LABELS[stage] for stage in context.previous_types) or "없음"
    return (
        f"질문: {context.message}\n"
        f"대상 지원자: {_refs(context, targets.rows) or '지정 없음 (전형 지원자 전체)'}\n"
        f"현재 전형: {context.stage_name} ({_STAGE_LABELS[context.stage_type]})\n"
        f"끝난 전형: {previous}"
    )


def verify_items(items: Sequence[AnswerItem], context: ChatContext) -> tuple[list[ChatItem], list[str]]:
    """번호를 지원자로 바꾸고 근거를 원문과 맞춰 본다.

    없는 번호의 항목은 버리고, 근거 없이 지원자를 OK라 한 항목은 CHECK다.
    """
    verified: list[ChatItem] = []
    sources: list[str] = []
    for item in items:
        row = None
        if item.candidate is not None:
            row = resolve_ref(context, item.candidate)
            if row is None:
                continue
        kept = [source for source in (_verified_source(context, row, evidence) for evidence in item.evidence) if source]
        status = "CHECK" if row is not None and item.status == "OK" and not kept else item.status
        sources += [source for source in kept if source not in sources]
        verified.append(
            ChatItem(
                application_id=row.application_id if row else None,
                label=item.label,
                text=_shorten(item.text),
                status=status,
            )
        )
    return verified, sources


def sub_agents(called: Sequence[str]) -> list[str]:
    return [SUB_AGENT_TOOLS[name] for name in dict.fromkeys(called) if name in SUB_AGENT_TOOLS]


def _verified_source(context: ChatContext, row: CandidateRow | None, evidence: AnswerEvidence) -> str | None:
    """근거가 원문에 있으면 출처 이름(문서는 실제 문서로 고친다), 없으면 None. 문서 · 면접이 아닌 출처는 그대로 둔다."""
    source = evidence.source.strip()
    if source in _DOCUMENT_LABELS:
        if row is None:
            return None
        found = evidence_source(evidence.sentence, context.documents.get(row.application_id, []))
        return found.label if found else None
    if source in (INTERVIEW_SOURCE, "면접 답변"):
        if row is None:
            return None
        return INTERVIEW_SOURCE if _in_interviews(context, row, evidence.sentence) else None
    return source


def _in_interviews(context: ChatContext, row: CandidateRow, sentence: str) -> bool:
    view = context.interviews.get(row.application_id)
    if view is None:
        return False
    questions = [*view.questions, *(question for previous in view.previous for question in previous.questions)]
    text = "".join("".join(f"{question.text}{question.answer}".split()) for question in questions)
    needle = "".join(sentence.split())
    return bool(needle) and needle in text


def _refs(context: ChatContext, rows: Sequence[CandidateRow]) -> str:
    return ", ".join(f"{candidate_ref(context, row.application_id)} {row.name}" for row in rows)


def _shorten(text: str) -> str:
    trimmed = " ".join(text.split())
    return trimmed if len(trimmed) <= TEXT_LENGTH else trimmed[: TEXT_LENGTH - 1] + "…"
