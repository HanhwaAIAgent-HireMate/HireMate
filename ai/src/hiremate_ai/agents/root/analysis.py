"""분석 루프. 계획이 answer나 확인할 점이 필요한 questions일 때만 쓰는 좁은 ReAct 도구 루프다.

자주 쓰는 자료(대상의 프로필, 전형 개요, 면접관 메모)는 미리 넣고, 나머지는 모델이 도구로 읽는다.
원문 해석은 AI 워커가 저장한 분석 Agent의 결과를 쓰고, 저장 결과로 답할 수 없을 때만 서류, 면접 Agent를 부른다.
도구가 돌려준 근거 한 줄마다 근거 번호(E번호)가 붙고, 모델은 원문을 옮겨 쓰지 않고 번호로 인용한다.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from hiremate_ai.agents.guardrails import blocked_attribute, blocked_reply
from hiremate_ai.agents.root.delegation import KEEP_CALLS, Delegation
from hiremate_ai.agents.root.find import SEARCH_STATUS, SearchQuery, plan_find, search_criteria
from hiremate_ai.agents.root.ledger import Ledger
from hiremate_ai.agents.root.plan import EMPTY_FIND, NO_MESSAGE, Form, has_condition
from hiremate_ai.agents.root.progress import Progress, names, nested
from hiremate_ai.agents.root.toolkit import (
    OUT_OF_SCOPE,
    RootToolContext,
    RootToolkit,
    application_block,
    candidate_ref,
    company_block,
    interview_block,
    memo_block,
    profile_block,
    resolve_ref,
    stage_block,
    summary_line,
    turns_block,
)
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, ChatPlan
from hiremate_ai.llm.chat import LlmFailureReason, LlmOutputError, record_interrupted_model_tool, reserve_model_calls
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import data_block

FEW_TARGETS = 5
THINKING = "요청에 맞는 답변을 준비하고 있어요"
# 분석 루프의 도구가 내는 단계. Root 단계(THINKING) 아래 한 칸 들여 보인다
READING = {
    "profile": "{names}의 프로필을 읽고 있어요",
    "application": "{names}의 서류 분석을 읽고 있어요",
    "interview": "{names}의 면접 기록을 읽고 있어요",
}
READING_STAGE = "전형 전체 현황을 읽고 있어요"
READING_COMPANY = "회사 소개와 공고 기준을 읽고 있어요"
SEARCHING_POOL = "후보 {count}명 안에서 조건에 맞는 지원자를 찾고 있어요"
UNKNOWN_REFS = "refs에는 자료에 나온 E번호만 쓰세요."
FOREIGN_REFS = "항목의 refs는 그 항목 지원자의 근거만 쓰세요."
UNKNOWN_CANDIDATE = "candidate에는 현재 전형 지원자의 C번호를 쓰세요."
BAD_FIND = "find에는 search_candidates가 돌려준 S번호를 쓰세요."
OUTSIDE_TARGETS = "확인할 점은 대상 지원자에게만 쓰세요."
NO_FOCUS = "확인할 점을 focus에 지원자별로 쓰세요."
NO_ITEMS = "근거 번호를 단 항목을 items에 하나 이상 쓰세요."
NO_TURNS = "앞 대화가 없어요."
SEARCH_BUDGET = "호출 한도가 남지 않아 검색 후보를 다시 확인하지 못했어요. 지금까지 읽은 자료로 답하세요."

ANALYSIS_SYSTEM = """[역할]
너는 Root Agent의 분석 단계다. 계획 단계가 정한 과제와 대상을 받아, 필요한 자료만 도구로 확인하고
최종 답 도구 하나로 답한다. 도구는 읽기만 한다. 원문 해석은 서류 Agent와 면접 Agent의 결과를 쓰고
문서를 새로 해석하지 않는다.

[자료]
- 각 줄 앞의 E번호가 근거 번호다. [근거 확인] 줄은 사실로 쓸 수 있고, [확인 필요] 줄은 확인 필요로만 쓴다.
- 미리 넣은 자료로 답할 수 있으면 도구를 부르지 않는다.
- 저장된 분석이 없거나, 담당자가 다시 검토해 달라고 했거나, 사실 전체의 근거를 봐야 할 때만
  review_documents나 review_interview를 부른다.
- 아직 진행하지 않은 전형의 자료는 생기기 전이다. 부족한 점으로 쓰지 않는다.

[답 쓰기]
- 항목마다 지원자 한 명과 그 지원자의 근거 번호를 refs에 적는다. 비교도 지원자마다 항목을 나눈다.
  항목에는 그 지원자의 사실만 쓰고, 다른 지원자와 견주는 말은 message에 쓴다.
- C번호와 E번호는 candidate와 refs에만, S번호는 find의 result에만, D번호는 review_interview의 previous에만 쓴다.
  message와 text에는 이름과 내용으로 쓴다.
- 근거가 말하는 만큼만 쓴다. 팀 성과, 교육, 개인 프로젝트, 역할이 불분명한 경험을 본인 실무로 올리지 않는다.
- 근거를 찾지 못한 것은 '없다'가 아니라 확인 필요다.
- 읽은 결과로 조건 검색이 필요하면 search_candidates로 찾은 뒤 find에 그 결과 번호를 낸다.
  find는 선택 지원자를 바꾸므로 담당자가 지원자를 더 찾아 달라고 한 요청에만 낸다.
  앞에서 찾은 이유나 결과 설명을 묻는 질문은 previous_turns를 읽고 answer로 답한다.
- questions에는 지원자별 확인할 점과 그 근거 번호를 낸다.
- 대상이나 조건을 정할 수 없으면 clarify로 묻는다.
- message는 물은 것에 먼저 답하는 한두 문장이다. 분석 내용은 items에 쓴다.
- 누가 더 나은지, 어느 쪽이 더 맞는지 물으면 message 첫 문장에 이름을 들어 어떤 기준에서 누가 앞서 보이는지와
  그 이유를 쓴다. 담당자가 기준을 말하지 않았으면 질문의 뜻에 가까운 기준을 네가 골라 밝히고 견준다.
  기준을 묻거나 판단을 미루지 않는다. 기준마다 앞서는 사람이 다르면 기준별로 누가 앞서는지 쓴다.
  합격이나 불합격을 권하지 않는다.
- message와 text는 '~요'로 끝나는 존댓말로 쓴다. 앞 대화에서 말투를 바꿔 달라고 했으면 그 말투를 쓴다."""


class ItemDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: str | None = Field(description="이 항목의 지원자 C번호. 지원자를 다루지 않는 공통 사실이면 null")
    label: str = Field(description="항목 이름")
    text: str = Field(description="한 줄 설명. 근거가 말하는 만큼만 쓴다")
    status: Literal["OK", "CHECK"] = Field(description="근거로 확인되면 OK, 추가 확인이 필요하면 CHECK")
    refs: list[str] = Field(description="이 항목을 받치는 근거 번호(E1 등). 그 지원자 또는 공통 자료의 번호만")


class FocusDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: str = Field(description="면접 질문을 만들 지원자 C번호")
    text: str = Field(description="면접에서 확인할 점 한 줄")
    refs: list[str] = Field(description="확인할 점의 근거 번호(E1 등)")


class AnswerOutput(Form):
    """자료에 근거한 사실, 분석, 비교 답. 지원자별 항목에 근거 번호를 단다."""

    message: str = Field(description="물은 것에 먼저 답하는 한두 문장. 비교 질문이면 누가 앞서 보이는지와 이유")
    items: list[ItemDraft] = Field(description="지원자별 항목. 비교도 지원자마다 나눈다")


class FindOutput(Form):
    """읽은 자료를 바탕으로 search_candidates로 찾은 결과를 선택 지원자에 반영한다. 후보와 순서는 바꿀 수 없다."""

    result: str = Field(description="search_candidates가 돌려준 결과 번호(S1 등)")


class QuestionsOutput(Form):
    """면접 질문을 만들 때 넘길 지원자별 확인할 점."""

    message: str = Field(description="한두 문장 요약")
    focus: list[FocusDraft] = Field(description="지원자별 확인할 점과 근거 번호")


class ClarifyOutput(Form):
    """대상이나 조건을 정할 수 없을 때만 묻는다."""

    message: str = Field(description="무엇이 불분명한지 밝힌 짧은 질문")


ANSWER_FORMS: dict[str, type[Form]] = {"answer": AnswerOutput, "find": FindOutput, "clarify": ClarifyOutput}
QUESTION_FORMS: dict[str, type[Form]] = {"questions": QuestionsOutput, "clarify": ClarifyOutput}
_FORMS = {**ANSWER_FORMS, **QUESTION_FORMS}


class AnalysisReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["answer", "find", "questions", "clarify"]
    form: AnswerOutput | FindOutput | QuestionsOutput | ClarifyOutput

    @model_validator(mode="before")
    @classmethod
    def from_form(cls, value: Any) -> Any:
        """{"kind": 도구 이름, **인자}를 받으면 그 도구 형식으로 검증한다."""
        if not isinstance(value, dict) or "form" in value:
            return value
        kind = value.get("kind")
        form = _FORMS.get(kind) if isinstance(kind, str) else None
        if form is None:
            raise ValueError(f"알 수 없는 분석 답 종류예요: {kind}")
        return {"kind": kind, "form": form.model_validate({key: arg for key, arg in value.items() if key != "kind"})}


@dataclass(frozen=True)
class AnalysisRun(RootToolContext):
    """요청 하나 동안의 분석 상태. 대화방 체크포인터에는 넣지 않는다."""

    ledger: Ledger = field(default_factory=Ledger)
    rows: list[CandidateRow] = field(default_factory=list)
    searches: dict[str, ChatPlan] = field(default_factory=dict)
    queries: dict[str, SearchQuery] = field(default_factory=dict)


def analysis_run(
    context: ChatContext,
    rows: Sequence[CandidateRow],
    turns: Sequence[Turn] = (),
    result: Sequence[str] | None = None,
    subject: Sequence[str] = (),
) -> AnalysisRun:
    return AnalysisRun(
        company_id=context.company.company_id,
        recruitment_id=context.recruitment_id,
        stage_id=context.stage_id,
        application_ids=frozenset(row.application_id for row in context.candidates),
        chat=context,
        turns=list(turns),
        previous_result=list(result) if result is not None else None,
        previous_subject=list(subject),
        rows=list(rows),
    )


async def run_analysis(
    llm: LlmClient,
    toolkit: RootToolkit,
    run: AnalysisRun,
    *,
    task: Literal["answer", "questions"],
    checks: Literal["none", "documents", "memos"],
    progress: Progress,
) -> AnalysisReply:
    """모델 호출은 요청의 호출 예산을 같이 쓴다. 답이 검증에 실패하면 같은 자료로 한 번 고쳐 쓰게 한다."""
    # 도구와 하위 Agent의 일은 Root 단계 아래에 들여 보인다
    inner = nested(progress)
    delegation = Delegation(llm, inner, artifacts=toolkit.artifacts, ledger=run.ledger)
    tools = [*_tools(llm, toolkit, inner), *delegation.review_tools()]
    forms = ANSWER_FORMS if task == "answer" else QUESTION_FORMS
    progress.status(THINKING)
    agent = llm.tool_agent(
        AnalysisReply, agent="root", system=ANALYSIS_SYSTEM, tools=tools, context=AnalysisRun, forms=forms
    )

    async def validate(reply: AnalysisReply) -> str | None:
        return check_reply(reply, run)

    user = await _prompt(toolkit, run, task, checks)
    # 근거 검토가 쓸 호출 한 번은 남긴다. 루프와 하위 Agent는 그 전까지만 쓴다
    with reserve_model_calls(1):
        return await agent.run(user, context=run, validate=validate)


def check_reply(reply: AnalysisReply, run: AnalysisRun) -> str | None:
    """모델이 고쳐 쓸 수 있는 실수만 찾는다. 근거의 강도는 근거 검토가 확인한다."""
    form = reply.form
    if isinstance(form, FindOutput):
        return None if form.result in run.searches else BAD_FIND
    if isinstance(form, ClarifyOutput):
        return None if form.message.strip() else NO_MESSAGE
    if isinstance(form, QuestionsOutput):
        if not form.focus:
            return NO_FOCUS
        targets = {row.application_id for row in run.rows}
        for focus in form.focus:
            row = resolve_ref(run.chat, focus.candidate)
            if row is None or row.application_id not in targets:
                return OUTSIDE_TARGETS
            problem = _refs_problem(run, row, focus.refs)
            if problem is not None:
                return problem
        return None
    if not form.message.strip():
        return NO_MESSAGE
    if not form.items:
        return NO_ITEMS
    for item in form.items:
        row = resolve_ref(run.chat, item.candidate) if item.candidate is not None else None
        if item.candidate is not None and row is None:
            return UNKNOWN_CANDIDATE
        problem = _refs_problem(run, row, item.refs)
        if problem is not None:
            return problem
    return None


def _refs_problem(run: AnalysisRun, row: CandidateRow | None, refs: Sequence[str]) -> str | None:
    """지원자 항목은 그 지원자와 공통 자료의 근거만 쓴다. 공통 항목(전형 집계 등)은 지원자별 줄도 근거로 쓸 수 있다."""
    for ref in refs:
        evidence = run.ledger.get(ref.strip().upper())
        if evidence is None:
            return UNKNOWN_REFS
        if row is not None and evidence.application_id not in (None, row.application_id):
            return FOREIGN_REFS
    return None


async def _prompt(toolkit: RootToolkit, run: AnalysisRun, task: Literal["answer", "questions"], checks: str) -> str:
    chat = run.chat
    rows = run.rows
    goal = (
        "답하기"
        if task == "answer"
        else f"면접 질문의 확인할 점 정하기 ({'면접관 메모' if checks == 'memos' else '서류'})"
    )
    targets = ", ".join(f"{candidate_ref(chat, row.application_id)} {row.name}" for row in rows)
    parts = [f"[과제] {goal}", f"[대상] {targets or '특정 지원자 없음'}"]
    if not rows:
        parts.append(stage_block(run.ledger, chat))
    elif len(rows) <= FEW_TARGETS:
        parts += [profile_block(run.ledger, chat, row, await toolkit.profile(run, row.application_id)) for row in rows]
    else:
        parts.append(data_block("candidates", "\n".join(summary_line(chat, row) for row in rows)))
    if checks == "memos":
        parts += [memo_block(run.ledger, chat, row) for row in rows]
    history = turns_block(run.ledger, chat, run.turns)
    if history:
        parts.append(history)
    parts.append(f"[현재 요청] {chat.message}")
    return "\n\n".join(parts)


def _tools(llm: LlmClient, toolkit: RootToolkit, progress: Progress) -> list[BaseTool]:
    @tool
    async def read_candidates(
        candidates: list[str], detail: Literal["profile", "application", "interview"], runtime: ToolRuntime[AnalysisRun]
    ) -> str:
        """지원자 자료를 읽는다. candidates는 C번호 목록이다.

        profile은 분석 Agent들이 정리한 프로필과 전형 결과, application은 서류 Agent의 분석 원본(사실별 본인 · 팀 구분과
        인용, 경력 기간, 공고 기준별 판정, 자기소개서 문항 요약, 학력과 자격), interview는 면접 질문과 답변 원문,
        면접 분석이다.
        """
        run = runtime.context
        rows = [resolve_ref(run.chat, ref) for ref in candidates]
        if not rows or any(row is None for row in rows):
            return OUT_OF_SCOPE
        progress.status(READING[detail].format(names=names([row for row in rows if row is not None])))
        texts = []
        for row in rows:
            if row is None:
                continue
            if detail == "application":
                texts.append(
                    application_block(run.ledger, run.chat, row, await toolkit.review(run, row.application_id))
                )
            elif detail == "interview":
                texts.append(interview_block(run.ledger, run.chat, row, await toolkit.profile(run, row.application_id)))
            else:
                texts.append(profile_block(run.ledger, run.chat, row, await toolkit.profile(run, row.application_id)))
        return "\n\n".join(texts)

    @tool
    async def stage_overview(runtime: ToolRuntime[AnalysisRun]) -> str:
        """전형 전체의 공식 집계(인원, 결정별 인원, 선택, 경력)와 지원자별 한 줄을 읽는다."""
        progress.status(READING_STAGE)
        return stage_block(runtime.context.ledger, runtime.context.chat)

    @tool
    async def company_and_posting(runtime: ToolRuntime[AnalysisRun]) -> str:
        """회사 소개, 문화, 인재상과 공고(담당 업무, 자격 요건, 우대 사항)를 읽는다."""
        progress.status(READING_COMPANY)
        return company_block(runtime.context.ledger, runtime.context.chat)

    @tool
    async def search_candidates(
        query: SearchQuery,
        runtime: ToolRuntime[AnalysisRun],
        pool: Annotated[
            list[str] | None, Field(description="query 밖의 인자. 전체 검색은 null, 제한 검색은 C번호 목록")
        ] = None,
    ) -> str:
        """읽은 자료를 바탕으로 조건 검색이 필요할 때 지원자를 찾는다. 결과 번호(S1 등)를 돌려준다.

        query에는 필수 mode, concepts, min_score와 필요한 선택 인자만 넣는다. 선택 지원자는 바꾸지 않는다.
        결과를 선택에 반영하려면 최종 답 find에 결과 번호를 낸다.
        """
        run = runtime.context
        if not has_condition(query):
            raise ToolException(EMPTY_FIND)
        if term := blocked_attribute(" ".join(search_criteria(query, run.chat)), blind=run.chat.posting.blind):
            return blocked_reply(term)
        rows = [resolve_ref(run.chat, ref) for ref in pool] if pool is not None else None
        if rows is not None and any(row is None for row in rows):
            return OUT_OF_SCOPE
        ids = [row.application_id for row in rows if row is not None] if rows is not None else None
        progress.status(SEARCH_STATUS if ids is None else SEARCHING_POOL.format(count=len(ids)))
        try:
            # 후보 재확인은 루프의 최종 답과 근거 검토가 쓸 호출을 남긴다
            with reserve_model_calls(KEEP_CALLS):
                found = await plan_find(llm, query, run.chat, toolkit, pool=ids, progress=nested(progress))
        except LlmOutputError as error:
            if error.reason is not LlmFailureReason.BUDGET:
                raise
            record_interrupted_model_tool("search_candidates")
            return SEARCH_BUDGET
        key = f"S{len(run.searches) + 1}"
        run.searches[key] = found
        run.queries[key] = query
        return json.dumps(
            {
                "result": key,
                "message": found.message,
                "candidates": [f"{candidate_ref(run.chat, value)}" for value in found.targets],
                "items": [
                    {
                        "candidate": candidate_ref(run.chat, item.application_id) if item.application_id else None,
                        "label": item.label,
                        "text": item.text,
                        "status": item.status,
                    }
                    for item in found.items
                ],
            },
            ensure_ascii=False,
        )

    search_candidates.handle_tool_error = True

    @tool
    async def previous_turns(runtime: ToolRuntime[AnalysisRun]) -> str:
        """앞 대화의 질문, 답과 그때 검증한 항목을 읽는다. 항목 상태는 그때 검증한 상태 그대로다."""
        run = runtime.context
        return turns_block(run.ledger, run.chat, run.turns) or NO_TURNS

    return [read_candidates, stage_overview, company_and_posting, search_candidates, previous_turns]
