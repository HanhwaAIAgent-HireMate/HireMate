"""B 분석 · 생성. 모델이 조회 도구를 골라 부르며 자료를 확인하고(도구 루프), 코드가 근거를 원문과 맞춰 본다 (기획 §11).

선택 지원자나 채용 상태는 바꾸지 않고 대화로만 답한다. 근거가 원문에 없으면 버리고 확인 필요로 둔다 (규칙 7).
"""

import asyncio
import re
from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hiremate_ai.agents.guardrails import evidence_source
from hiremate_ai.agents.root.edit import SAME_NAME
from hiremate_ai.agents.root.route import RootRoute
from hiremate_ai.agents.root.targets import Targets, checked
from hiremate_ai.agents.root.toolkit import RootToolContext, RootToolkit, candidate_ref, resolve_ref, scope_of
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, ChatItem, ChatPlan, Decision, Intent
from hiremate_ai.contract import DocumentType, StageType
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient

# backend는 ai 응답을 60초 기다리고 분류 호출이 앞에 있다
ANSWER_TIMEOUT_SECONDS = 45.0
TEXT_LENGTH = 120
NOT_FINISHED = "자료를 다 확인하지 못했어요. 질문을 좁혀 다시 물어봐 주세요."
# 면접 질문: 이 인원까지는 지원자마다 확인할 점을 정리하고, 넘으면 HR 문장으로 한꺼번에 만든다
FOCUS_LIMIT = 3
BULK_LIMIT = 20
NO_QUESTION_TARGET = "누구의 면접 질문을 만들까요? @로 고르거나 체크해 주세요."
FOCUSED = "{count}명의 맞춤 질문을 만들어 카드에 넣었어요. 질문을 만든 이유는 아래와 같아요."
BULK = (
    "{count}명은 한 번에 자세히 살펴보기 어려워 지원 서류를 기준으로 질문을 만들었어요. "
    "특정 지원자는 @로 골라 물어보면 이전 전형까지 확인해 만들어요."
)
INTERVIEW_AGENT = "Interview Agent"
INTERVIEW_SOURCE = "면접 기록"
# 하위 Agent를 감싼 도구. 부르면 답의 agents에 이 이름이 들어간다
SUB_AGENT_TOOLS = {"analyze_application": "Application Agent", "analyze_assessment": "Assessment Agent"}

_DOCUMENT_LABELS = {document.label: document for document in DocumentType}
_REF = re.compile(r"(?<![A-Za-z0-9])[Cc](\d+)(?![0-9])")
_REF_WITH_NAME = re.compile(r"(?<![A-Za-z0-9])[Cc](\d+)\s+([가-힣A-Za-z]+)")
_STAGE_LABELS = {StageType.DOCUMENT: "서류", StageType.ASSESSMENT: "평가", StageType.INTERVIEW: "면접"}

ANSWER_SYSTEM = """너는 채용 담당자의 질문에 지원자 자료를 확인해 답한다.
도구로 필요한 자료만 골라 읽고, 근거가 모이면 답한다.

- 근거가 있는 내용만 말한다. 자료가 없거나 확인하지 못한 점은 status=CHECK로 나눈다.
- 서류와 평가 · 면접을 함께 묻는 질문이면 그 자료를 모두 확인한다.
- 지원자는 C1 같은 번호로만 가리킨다. 도구 인자와 답의 candidate 모두 번호를 쓴다.
- 지원자에 관한 항목은 candidate에 반드시 그 지원자 번호를 적는다. 여러 지원자를 비교하면 지원자마다 항목을 따로 만든다.
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


FOCUS_SYSTEM = """너는 면접 질문을 만들기 전에 지원자마다 면접에서 더 확인할 점을 정리한다. 질문 문장은 만들지 않는다.

- 요청에 필요한 자료만 도구로 고른다. 서류만 보면 되는 요청이면 면접 기록이나 전형 결과를 읽지 않아도 된다.
- focus는 "확인할 점 + 근거 요약 + 담당자가 준 방향"을 한두 문장으로 쓴다.
- reasons에는 확인할 점마다 근거 문장(도구 결과의 문장 그대로)과 출처를 단다. 근거가 없으면 status=CHECK다.
- 지원자는 C1 같은 번호로만 가리킨다."""


class QuestionFocusItem(BaseModel):
    candidate: str = Field(description="지원자 번호(C1 같은)")
    focus: str = Field(description="면접에서 확인할 점과 근거 요약, 담당자가 준 방향. 한두 문장")
    reasons: list[AnswerItem] = Field(default=[], description="확인할 점마다의 근거")


class RootQuestionFocus(BaseModel):
    items: list[QuestionFocusItem]


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
    only = targets.rows[0] if len(targets.rows) == 1 else None
    items, sources = verify_items(answered.items, context, only)
    message = readable(answered.message, context)
    return ChatPlan.answer(Intent.ANSWER, message, items, sources, sub_agents(scope.called))


async def plan_questions(
    llm: LlmClient, route: RootRoute, context: ChatContext, targets: Targets, toolkit: RootToolkit
) -> ChatPlan:
    """면접 전형의 면접 질문 요청. 질문은 backend가 Interview Agent로 만들고, Root는 대상과 확인할 점만 정한다.

    3명 이하는 도구 루프로 지원자마다 확인할 점(question_focus)과 이유를 정리한다.
    4명 이상은 HR 문장으로 한꺼번에 만든다.
    """
    if targets.ambiguous:
        return ChatPlan.answer(Intent.CLARIFY, SAME_NAME.format(names=", ".join(targets.ambiguous)))
    rows = targets.rows or checked(context)
    if not rows and route.all_candidates:
        rows = [row for row in context.candidates if row.decision is Decision.PENDING][:BULK_LIMIT]
    if not rows:
        return ChatPlan.answer(Intent.CLARIFY, NO_QUESTION_TARGET)
    ids = [row.application_id for row in rows]
    if len(rows) > FOCUS_LIMIT:
        return _questions_plan(BULK.format(count=len(rows)), ids, {}, [], [], [INTERVIEW_AGENT])

    scope = scope_of(context)
    agent = llm.tool_agent(
        RootQuestionFocus, agent="root", system=FOCUS_SYSTEM, tools=toolkit.answer_tools, context=RootToolContext
    )
    prompt = answer_prompt(context, Targets(rows=rows, ambiguous=[]))
    try:
        async with asyncio.timeout(ANSWER_TIMEOUT_SECONDS):
            result = await agent.run(prompt, context=scope)
    except (LlmOutputError, TimeoutError):
        return ChatPlan.answer(Intent.CLARIFY, NOT_FINISHED)
    focus: dict[UUID, str] = {}
    reasons: list[AnswerItem] = []
    for item in result.items:
        row = resolve_ref(context, item.candidate)
        if row is None or row.application_id not in ids:
            continue
        if item.focus.strip():
            focus[row.application_id] = readable(item.focus.strip(), context)
        reasons += [reason.model_copy(update={"candidate": item.candidate}) for reason in item.reasons]
    items, sources = verify_items(reasons, context)
    agents = [*sub_agents(scope.called), INTERVIEW_AGENT]
    return _questions_plan(FOCUSED.format(count=len(rows)), ids, focus, items, sources, agents)


def _questions_plan(
    message: str, ids: list[UUID], focus: dict[UUID, str], items: list[ChatItem], sources: list[str], agents: list[str]
) -> ChatPlan:
    return ChatPlan(
        intent=Intent.ANSWER,
        mode=None,
        edit=None,
        targets=[],
        message=message,
        items=items,
        sources=sources,
        agents=agents,
        question_targets=ids,
        question_focus=focus,
    )


def answer_prompt(context: ChatContext, targets: Targets) -> str:
    previous = ", ".join(_STAGE_LABELS[stage] for stage in context.previous_types) or "없음"
    return (
        f"질문: {context.message}\n"
        f"대상 지원자: {_refs(context, targets.rows) or '지정 없음 (전형 지원자 전체)'}\n"
        f"현재 전형: {context.stage_name} ({_STAGE_LABELS[context.stage_type]})\n"
        f"끝난 전형: {previous}"
    )


def verify_items(
    items: Sequence[AnswerItem], context: ChatContext, only: CandidateRow | None = None
) -> tuple[list[ChatItem], list[str]]:
    """번호를 지원자로 바꾸고 근거를 원문과 맞춰 본다.

    없는 번호의 항목은 버린다. 번호를 비운 항목은 글에 번호가 하나만 있으면 그 지원자로,
    근거를 단 항목이고 대상이 한 명이면 그 대상으로 본다(근거는 지원자 문서와 맞춰 봐야 한다).
    근거를 댔지만 하나도 확인되지 않았거나, 근거 없이 지원자를 OK라 한 항목은 CHECK다.
    """
    verified: list[ChatItem] = []
    sources: list[str] = []
    for item in items:
        if item.candidate is not None:
            row = resolve_ref(context, item.candidate)
            if row is None:
                continue
        else:
            row = _mentioned_row(context, f"{item.label} {item.text}", only if item.evidence else None)
        kept = [source for source in (_verified_source(context, row, evidence) for evidence in item.evidence) if source]
        unsupported = item.status == "OK" and not kept and (bool(item.evidence) or row is not None)
        status = "CHECK" if unsupported else item.status
        sources += [source for source in kept if source not in sources]
        verified.append(
            ChatItem(
                application_id=row.application_id if row else None,
                label=readable(item.label, context),
                text=_shorten(readable(item.text, context)),
                status=status,
            )
        )
    return verified, sources


def readable(text: str, context: ChatContext) -> str:
    """담당자가 읽을 글의 지원자 번호(C2)를 이름으로 바꾼다. "C2 김하늘"처럼 이름이 뒤따르면 번호만 뺀다."""

    def with_name(match: re.Match[str]) -> str:
        row = resolve_ref(context, match.group(1))
        return match.group(2) if row is not None and match.group(2).startswith(row.name) else match.group(0)

    def name_only(match: re.Match[str]) -> str:
        row = resolve_ref(context, match.group(1))
        return row.name if row is not None else match.group(0)

    return _REF.sub(name_only, _REF_WITH_NAME.sub(with_name, text))


def sub_agents(called: Sequence[str]) -> list[str]:
    return [SUB_AGENT_TOOLS[name] for name in dict.fromkeys(called) if name in SUB_AGENT_TOOLS]


def _mentioned_row(context: ChatContext, text: str, only: CandidateRow | None) -> CandidateRow | None:
    refs = {row.application_id: row for match in _REF.finditer(text) if (row := resolve_ref(context, match.group(1)))}
    if len(refs) == 1:
        return next(iter(refs.values()))
    return only if not refs else None


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
