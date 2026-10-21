"""B 분석 · 생성. 모델이 조회 도구를 골라 부르며 자료를 확인하고(도구 루프), 코드가 근거를 원문과 맞춰 본다 (기획 §11).

선택 지원자나 채용 상태는 바꾸지 않고 대화로만 답한다. 근거가 원문에 없으면 버리고 확인 필요로 둔다 (규칙 7).
"""

import asyncio
import re
from collections.abc import Mapping, Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.assessment.checks import NOTE_SOURCE, SUBMISSION_SOURCE
from hiremate_ai.agents.analysis.assessment.checks import RESULT_SOURCE as SCORE_SOURCE
from hiremate_ai.agents.guardrails import evidence_source
from hiremate_ai.agents.root.edit import SAME_NAME
from hiremate_ai.agents.root.route import RootRoute
from hiremate_ai.agents.root.targets import Targets, checked
from hiremate_ai.agents.root.toolkit import (
    AgentEvidence,
    RootToolContext,
    RootToolkit,
    candidate_ref,
    cited_agents,
    company_text,
    posting_text,
    recorded_evidence,
    resolve_ref,
    scope_of,
)
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, ChatItem, ChatPlan, Decision, Intent
from hiremate_ai.contract import DocumentType, StageType
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

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
RESULT_SOURCE = "전형 결과"
COMPANY_SOURCE = "회사 소개"
POSTING_SOURCE = "공고"
# 대상이 이 인원까지면 도구 루프 대신 지원자별 정리와 종합으로 답한다 (기획 17절)
MULTI_LIMIT = 5
# 지원자별 정리와 종합에 쓰는 시간. 정리가 늦은 지원자는 확인하지 못한 것으로 두고 나머지로 답한다.
# 합이 ANSWER_TIMEOUT_SECONDS 안에 들어야 한다 (backend는 60초 기다린다)
NOTES_SECONDS = 33.0
SUMMARY_SECONDS = 10.0
NOT_CHECKED = "자료를 확인하지 못했어요"
MULTI_FALLBACK = "{names}의 근거를 지원자별로 정리했어요."
# 평가 전형 자료. 원문이 ChatContext에 없어 Assessment Agent가 프로필에 남긴 근거와 맞춰 본다
PROFILE_SOURCES = (SUBMISSION_SOURCE, NOTE_SOURCE)

_DOCUMENT_LABELS = {document.label: document for document in DocumentType}
_REF = re.compile(r"(?<![A-Za-z0-9])[Cc](\d+)(?![0-9])")
_REF_WITH_NAME = re.compile(r"(?<![A-Za-z0-9])[Cc](\d+)\s+([^\s,.!?·]+)")
_STAGE_LABELS = {StageType.DOCUMENT: "서류", StageType.ASSESSMENT: "평가", StageType.INTERVIEW: "면접"}

ANSWER_SYSTEM = """너는 채용 담당자의 질문에 지원자 자료를 확인해 답한다.
도구로 필요한 자료만 골라 읽고, 근거가 모이면 답한다.

- 근거가 있는 내용만 말한다. 자료가 없거나 확인하지 못한 점은 status=CHECK로 나눈다.
- 서류와 평가 · 면접을 함께 묻는 질문이면 그 자료를 모두 확인한다.
- 지원자는 C1 같은 번호로만 가리킨다. 도구 인자와 답의 candidate 모두 번호를 쓴다.
- 지원자에 관한 항목은 candidate에 반드시 그 지원자 번호를 적는다. 여러 지원자를 비교하면 지원자마다 항목을 따로 만든다.
- 근거 문장(evidence.sentence)은 도구 결과의 문장을 글자 그대로 옮기고, 출처(source)를 적는다.
  출처는 이력서, 자기소개서, 포트폴리오, 자격증, 면접 기록, 전형 결과, 평가 제출물, 평가 메모, 회사 소개, 공고
  가운데 하나다.
  지원자 프로필 항목은 '근거:' 뒤 따옴표 안 문장을 근거 문장으로, 끝 괄호 안을 출처로 옮긴다.
- 앞 대화나 이전에 만든 면접 질문의 이유를 물으면 get_previous_turns로 그때 정리한 확인할 점과 근거를 보고 답한다.
  이유를 새로 지어내지 않는다.
- 채용 결정, 점수 변경, 상태 변경은 하지 않는다. 그런 요청은 담당자가 화면에서 한다고 안내한다.
- message는 담당자에게 하는 짧은 답이고, items는 지원자별 · 항목별 근거다."""


class AnswerEvidence(BaseModel):
    sentence: str = Field(description="근거 문장. 도구 결과의 문장을 글자 그대로")
    source: str = Field(
        description=(
            "출처: 이력서, 자기소개서, 포트폴리오, 자격증, 면접 기록, 전형 결과, 평가 제출물, 평가 메모, "
            "회사 소개, 공고"
        )
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


NOTES_SYSTEM = """너는 채용 담당자의 질문에 답하려고 지원자 한 명의 자료를 정리한다.
다른 지원자와 비교는 하지 않는다(비교는 나중에 한다).

- 질문에 필요한 항목만 1~3개 만든다. 항목마다 근거 문장 하나를 자료에서 글자 그대로 옮기고 출처를 적는다.
  출처는 이력서, 자기소개서, 포트폴리오, 자격증, 면접 기록, 전형 결과, 평가 제출물, 평가 메모, 회사 소개, 공고
  가운데 하나다.
  지원자 프로필 항목은 '근거:' 뒤 따옴표 안 문장을 근거 문장으로, 끝 괄호 안을 출처로 옮긴다.
- label은 "강점", "경력", "RDBMS 경험", "확인할 점"처럼 짧은 항목 이름이다. 공고 제목이나 문장을 쓰지 않는다.
- text는 한 줄로 짧게 쓴다.
- 자료가 없거나 확인하지 못한 점은 status=CHECK로 둔다.
- 앞 대화 기록이 있고 그때의 이유를 물으면 그 기록으로 답한다. 이유를 새로 지어내지 않는다.
- 채용 결정, 점수 변경, 상태 변경은 하지 않는다."""

SUMMARY_SYSTEM = """너는 지원자별로 정리한 항목만 보고 채용 담당자의 질문에 두세 문장으로 답한다.

- message에는 질문에 대한 답만 쓴다. 이 지시를 되풀이하거나 무엇을 했는지 설명하지 않는다.
- 항목에 없는 사실을 더하지 않는다. 확인 필요 항목은 확인이 필요하다고 말한다.
- 지원자는 notes 블록의 이름(name)으로만 부른다. 블록에 없는 사람을 말하지 않는다.
- 채용 결정, 점수 변경, 상태 변경은 하지 않는다.
- 비교 질문이면 지원자마다 근거 있는 점을 한 문장씩 말하고, 확인이 필요한 점을 덧붙인다."""


class CandidateNotes(BaseModel):
    items: list[AnswerItem] = Field(default=[], description="이 지원자의 항목")


class MultiSummary(BaseModel):
    message: str = Field(description="담당자에게 하는 짧은 답")


FOCUS_SYSTEM = """너는 면접 질문을 만들기 전에 지원자마다 면접에서 더 확인할 점을 정리한다. 질문 문장은 만들지 않는다.

- 요청에 필요한 자료만 도구로 고른다. 서류만 보면 되는 요청이면 면접 기록이나 전형 결과를 읽지 않아도 된다.
- focus는 "확인할 점 + 근거 요약 + 담당자가 준 방향"을 한두 문장으로 쓴다.
- reasons에는 확인할 점마다 근거 문장(도구 결과의 문장 그대로)과 출처를 단다. 근거가 없으면 status=CHECK다.
  지원자 프로필 항목은 '근거:' 뒤 따옴표 안 문장을 근거 문장으로, 끝 괄호 안을 출처로 옮긴다.
- 지원자는 C1 같은 번호로만 가리킨다."""


class QuestionFocusItem(BaseModel):
    candidate: str = Field(description="지원자 번호(C1 같은)")
    focus: str = Field(description="면접에서 확인할 점과 근거 요약, 담당자가 준 방향. 한두 문장")
    reasons: list[AnswerItem] = Field(default=[], description="확인할 점마다의 근거")


class RootQuestionFocus(BaseModel):
    items: list[QuestionFocusItem]


async def plan_answer(
    llm: LlmClient,
    route: RootRoute,
    context: ChatContext,
    targets: Targets,
    toolkit: RootToolkit,
    turns: Sequence[Turn] = (),
) -> ChatPlan:
    if targets.ambiguous and not targets.rows:
        return ChatPlan.answer(Intent.CLARIFY, SAME_NAME.format(names=", ".join(targets.ambiguous)))
    # 멘션 · 이름이 없으면 체크한 지원자를 대상으로 본다
    rows = targets.rows or checked(context)
    if 2 <= len(rows) <= MULTI_LIMIT:
        return await plan_multi(llm, context, rows, toolkit, turns)
    scope = scope_of(context, turns)
    agent = llm.tool_agent(
        RootAnswer, agent="root", system=ANSWER_SYSTEM, tools=toolkit.answer_tools, context=RootToolContext
    )
    try:
        async with asyncio.timeout(ANSWER_TIMEOUT_SECONDS):
            answered = await agent.run(answer_prompt(context, Targets(rows=rows, ambiguous=[])), context=scope)
    except (LlmOutputError, TimeoutError):
        return ChatPlan.answer(Intent.CLARIFY, NOT_FINISHED)
    only = rows[0] if len(rows) == 1 else None
    recorded = await _recorded(toolkit, scope, context, answered.items, rows)
    items, sources, agents = verify_items(answered.items, context, only, recorded)
    message = readable(answered.message, context)
    return ChatPlan.answer(Intent.ANSWER, message, items, sources, agents)


async def plan_multi(
    llm: LlmClient,
    context: ChatContext,
    rows: Sequence[CandidateRow],
    toolkit: RootToolkit,
    turns: Sequence[Turn] = (),
) -> ChatPlan:
    """대상이 여럿인 분석. 코드가 지원자마다 자료를 모아 지원자별로 정리하고(동시에), 확인된 항목만으로 답을 쓴다.

    도구 루프가 지원자 자료를 한 명씩 부르다 호출 상한에 걸리거나, 여러 지원자의 근거가 한 항목에 섞이지 않게 한다.
    항목의 지원자는 코드가 붙이고 근거는 원문과 맞춰 본다 (규칙 7). 정리가 늦거나 실패한 지원자는 확인 필요로 둔다.
    """
    scope = scope_of(context, turns)
    shared = f"공고:\n{posting_text(context)}\n\n회사:\n{company_text(context)}"
    tasks = [asyncio.create_task(_notes(llm, context, row, shared, toolkit, scope)) for row in rows]
    try:
        done, pending = await asyncio.wait(tasks, timeout=NOTES_SECONDS)
    finally:
        # 시간이 다 됐거나 요청이 취소되면 남은 정리 호출을 멈춘다. 모델 서버를 붙잡아 두지 않게 한다
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    for task in done:
        error = task.exception()
        if error is not None and not isinstance(error, LlmOutputError):
            raise error

    recorded = await toolkit.evidence(scope, [row.application_id for row in rows]) if done else {}
    items: list[ChatItem] = []
    sources: list[str] = []
    agents: list[str] = []
    finished = 0
    for row, task in zip(rows, tasks, strict=True):
        if task not in done or task.exception() is not None:
            items.append(
                ChatItem(application_id=row.application_id, label="확인할 점", text=NOT_CHECKED, status="CHECK")
            )
            continue
        finished += 1
        ref = candidate_ref(context, row.application_id)
        own = [item.model_copy(update={"candidate": ref}) for item in task.result().items]
        verified, found, used = verify_items(own, context, row, recorded)
        items += verified
        sources += [source for source in found if source not in sources]
        agents += [agent for agent in used if agent not in agents]
    if not finished:
        return ChatPlan.answer(Intent.CLARIFY, NOT_FINISHED)
    return ChatPlan.answer(Intent.ANSWER, await _summary(llm, context, rows, items), items, sources, agents)


async def _notes(
    llm: LlmClient, context: ChatContext, row: CandidateRow, shared: str, toolkit: RootToolkit, scope: RootToolContext
) -> CandidateNotes:
    user = (
        f"질문: {context.message}\n"
        f"정리할 지원자: {candidate_ref(context, row.application_id)} {row.name}\n\n"
        f"{shared}\n\n지원자 자료:\n{await toolkit.brief(scope, row)}"
    )
    return await llm.structured(CandidateNotes, agent="root", system=f"{NOTES_SYSTEM}\n\n{UNTRUSTED_RULE}", user=user)


async def _summary(llm: LlmClient, context: ChatContext, rows: Sequence[CandidateRow], items: list[ChatItem]) -> str:
    """지원자별로 확인된 항목만 보고 답을 쓴다. 실패하거나 늦으면 정리했다는 말로 답한다."""
    blocks = []
    for row in rows:
        lines = [
            f"[{item.label}] {item.text} ({'근거 있음' if item.status == 'OK' else '확인 필요'})"
            for item in items
            if item.application_id == row.application_id
        ]
        blocks.append(data_block("notes", "\n".join(lines) or "정리한 항목 없음", name=row.name))
    user = f"질문: {context.message}\n\n" + "\n\n".join(blocks)
    fallback = MULTI_FALLBACK.format(names=", ".join(row.name for row in rows))
    try:
        async with asyncio.timeout(SUMMARY_SECONDS):
            summary = await llm.structured(
                MultiSummary, agent="root", system=f"{SUMMARY_SYSTEM}\n\n{UNTRUSTED_RULE}", user=user
            )
    except (LlmOutputError, TimeoutError):
        return fallback
    message = readable(summary.message.strip(), context)
    # 대상이 아닌 지원자를 말하면 항목에 없는 내용을 지어낸 것이다
    targets = {row.application_id for row in rows}
    if any(row.name in message for row in context.candidates if row.application_id not in targets):
        return fallback
    return message or fallback


async def plan_questions(
    llm: LlmClient,
    route: RootRoute,
    context: ChatContext,
    targets: Targets,
    toolkit: RootToolkit,
    turns: Sequence[Turn] = (),
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

    scope = scope_of(context, turns)
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
    recorded = await _recorded(toolkit, scope, context, reasons, rows)
    items, sources, used = verify_items(reasons, context, recorded=recorded)
    agents = list(dict.fromkeys([*used, INTERVIEW_AGENT]))
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


async def _recorded(
    toolkit: RootToolkit,
    scope: RootToolContext,
    context: ChatContext,
    items: Sequence[AnswerItem],
    rows: Sequence[CandidateRow],
) -> dict[UUID, list[AgentEvidence]]:
    """대상과 항목이 가리키는 지원자의 프로필 근거. 근거를 단 항목이 없으면 읽지 않는다."""
    if not any(item.evidence for item in items):
        return {}
    ids = [row.application_id for row in rows]
    ids += [row.application_id for item in items if item.candidate and (row := resolve_ref(context, item.candidate))]
    return await toolkit.evidence(scope, ids)


def answer_prompt(context: ChatContext, targets: Targets) -> str:
    previous = ", ".join(_STAGE_LABELS[stage] for stage in context.previous_types) or "없음"
    return (
        f"질문: {context.message}\n"
        f"대상 지원자: {_refs(context, targets.rows) or '지정 없음 (전형 지원자 전체)'}\n"
        f"현재 전형: {context.stage_name} ({_STAGE_LABELS[context.stage_type]})\n"
        f"끝난 전형: {previous}"
    )


def verify_items(
    items: Sequence[AnswerItem],
    context: ChatContext,
    only: CandidateRow | None = None,
    recorded: Mapping[UUID, Sequence[AgentEvidence]] | None = None,
) -> tuple[list[ChatItem], list[str], list[str]]:
    """번호를 지원자로 바꾸고 근거를 원문과 맞춰 본다. (항목, 남은 근거의 출처, 근거를 낸 분석 Agent)를 돌려준다.

    없는 번호의 항목은 버린다. 번호를 비운 항목은 글에 번호가 하나만 있으면 그 지원자로,
    근거를 단 항목이고 대상이 한 명이면 그 대상으로 본다(근거는 지원자 문서와 맞춰 봐야 한다).
    근거를 댔지만 하나도 확인되지 않았거나, 근거 없이 지원자를 OK라 한 항목은 CHECK다.
    recorded는 분석 Agent가 프로필에 남긴 근거다. 평가 자료 근거를 여기서 확인하고, 같은 문장을 낸 Agent를 알린다.
    """
    recorded = recorded or {}
    verified: list[ChatItem] = []
    sources: list[str] = []
    cited: list[tuple[UUID, str]] = []
    for item in items:
        if item.candidate is not None:
            row = resolve_ref(context, item.candidate)
            if row is None:
                continue
        else:
            row = _mentioned_row(context, f"{item.label} {item.text}", only if item.evidence else None)
        checked = [(evidence, _verified_source(context, row, evidence, recorded)) for evidence in item.evidence]
        kept = [source for _, source in checked if source]
        unsupported = item.status == "OK" and not kept and (bool(item.evidence) or row is not None)
        status = "CHECK" if unsupported else item.status
        sources += [source for source in kept if source not in sources]
        if row is not None:
            cited += [(row.application_id, evidence.sentence) for evidence, source in checked if source]
        verified.append(
            ChatItem(
                application_id=row.application_id if row else None,
                label=readable(item.label, context),
                text=_shorten(readable(item.text, context)),
                status=status,
            )
        )
    return verified, sources, cited_agents(recorded, cited)


def readable(text: str, context: ChatContext) -> str:
    """담당자가 읽을 글의 지원자 번호(C2)를 이름으로 바꾼다. "C2 김하늘"처럼 이름이 뒤따르면 번호만 뺀다."""

    def with_name(match: re.Match[str]) -> str:
        row = resolve_ref(context, match.group(1))
        return match.group(2) if row is not None and match.group(2).startswith(row.name) else match.group(0)

    def name_only(match: re.Match[str]) -> str:
        row = resolve_ref(context, match.group(1))
        return row.name if row is not None else match.group(0)

    return _REF.sub(name_only, _REF_WITH_NAME.sub(with_name, text))


def _mentioned_row(context: ChatContext, text: str, only: CandidateRow | None) -> CandidateRow | None:
    refs = {row.application_id: row for match in _REF.finditer(text) if (row := resolve_ref(context, match.group(1)))}
    if len(refs) == 1:
        return next(iter(refs.values()))
    return only if not refs else None


def _verified_source(
    context: ChatContext,
    row: CandidateRow | None,
    evidence: AnswerEvidence,
    recorded: Mapping[UUID, Sequence[AgentEvidence]],
) -> str | None:
    """근거가 원문에 있으면 출처 이름(문서는 실제 문서로 고친다), 없으면 None.

    출처는 정해 둔 이름으로 맞춘다("이력서 경력란" → 이력서). 맞출 수 없는 출처의 근거는 버린다.
    전형 결과 · 평가 결과(점수 · 결정)는 backend가 준 값이라 그대로 둔다.
    평가 제출물 · 메모는 Assessment Agent가 원문과 맞춰 프로필에 남긴 근거에 있어야 한다.
    """
    source = _canonical_source(evidence.source)
    if source in PROFILE_SOURCES:
        saved = recorded_evidence(recorded, row.application_id, evidence.sentence) if row is not None else None
        return saved.source if saved else None
    if source in _DOCUMENT_LABELS:
        if row is None:
            return None
        found = evidence_source(evidence.sentence, context.documents.get(row.application_id, []))
        return found.label if found else None
    if source == INTERVIEW_SOURCE:
        return INTERVIEW_SOURCE if row is not None and _in_interviews(context, row, evidence.sentence) else None
    if source == COMPANY_SOURCE:
        return source if _contains(_company_text(context), evidence.sentence) else None
    if source == POSTING_SOURCE:
        return source if _contains(_posting_text(context), evidence.sentence) else None
    return source if source in (RESULT_SOURCE, SCORE_SOURCE) else None


def _canonical_source(source: str) -> str | None:
    compact = "".join(source.split())
    for label in ("자기소개서", "이력서", "포트폴리오", "자격증"):
        if label in compact:
            return label
    if "자소서" in compact:
        return "자기소개서"
    if "면접" in compact:
        return INTERVIEW_SOURCE
    if "제출물" in compact:
        return SUBMISSION_SOURCE
    if "메모" in compact:
        return NOTE_SOURCE
    for label in (RESULT_SOURCE, SCORE_SOURCE, COMPANY_SOURCE, POSTING_SOURCE):
        if "".join(label.split()) in compact:
            return label
    return None


def _company_text(context: ChatContext) -> str:
    company = context.company
    talents = " ".join(f"{talent.title} {talent.description}" for talent in company.talents)
    return " ".join([company.name, company.intro, company.culture, talents, *company.benefits])


def _posting_text(context: ChatContext) -> str:
    posting = context.posting
    return " ".join(
        [posting.title, posting.intro, *posting.duties, *posting.qualifications, *posting.preferred, *posting.benefits]
    )


def _contains(text: str, sentence: str) -> bool:
    needle = "".join(sentence.split())
    return bool(needle) and needle in "".join(text.split())


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
