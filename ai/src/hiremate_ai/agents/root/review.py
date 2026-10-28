"""근거 검토. 분석 루프가 낸 항목을 근거 번호표와 맞춰 상태를 정하고, 문장이 근거보다 세게 말하는지 한 번에 판정한다.

코드: 항목 상태는 인용한 근거의 최고 상태 이하다. 팀 사실을 본인 성과로 올릴 수 없다.
모델: 지원자 항목이 있을 때만 한 번 부른다. 과장은 확인 필요로 낮추고 관계없는 근거를 단 항목은 버린다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from hiremate_ai.agents.root.analysis import FocusDraft, ItemDraft
from hiremate_ai.agents.root.answer import FOCUS_WITH_REQUEST, INTERVIEW_AGENT, readable, shorten
from hiremate_ai.agents.root.handlers import QUESTIONS_REQUESTED
from hiremate_ai.agents.root.ledger import Evidence, Ledger
from hiremate_ai.agents.root.plan import QuestionsPlan
from hiremate_ai.agents.root.stages import without_later_gaps
from hiremate_ai.agents.root.toolkit import resolve_ref
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, ChatItem, ChatPlan, Intent
from hiremate_ai.contract import InterviewerMemo
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

MESSAGE_FALLBACK = "확인한 내용을 정리했어요."
NO_EVIDENCE = "근거를 확인하지 못했어요. 조건을 좁혀 다시 말씀해 주세요."
FOCUS_LABEL = "확인할 점"

REVIEW_SYSTEM = """채용 담당자에게 보여 줄 답의 문장이 함께 적은 근거로 뒷받침되는지 판정한다.
- SUPPORTED: 근거가 문장의 주장을 그대로 받쳐 준다.
- OVERSTATED: 근거와 같은 내용이지만 문장이 더 세게 말한다. 팀 성과를 본인 성과로, 참여를 주도로,
  계획을 실적으로, 확인 필요를 확정으로 쓴 경우다.
- UNRELATED: 근거가 문장의 내용과 관계없다.
문장마다 id와 판정 하나를 낸다."""


class ClaimVerdict(BaseModel):
    id: str
    verdict: Literal["SUPPORTED", "OVERSTATED", "UNRELATED"]


class ClaimJudgement(BaseModel):
    verdicts: list[ClaimVerdict]


@dataclass(frozen=True)
class Checked:
    item: ChatItem
    evidence: list[Evidence]


async def review_items(
    llm: LlmClient, context: ChatContext, ledger: Ledger, message: str, drafts: Sequence[ItemDraft]
) -> tuple[str, list[Checked]]:
    """(보여 줄 답, 검토를 통과한 항목)을 돌려준다. 호출 예산이 남지 않았으면 지원자 항목을 확인 필요로 둔다."""
    checked = [each for draft in drafts if (each := _capped(context, ledger, draft)) is not None]
    message = readable(message, context)
    owned = [index for index, each in enumerate(checked) if each.item.application_id is not None]
    if not owned:
        return message, checked
    claims = [(f"I{number}", checked[index]) for number, index in enumerate(owned, start=1)]
    listing = [f"{key}. 문장: {each.item.text}\n   근거: {_quotes(each.evidence)}" for key, each in claims]
    listing.append(f"M. 문장: {message}\n   근거: {_quotes([e for each in checked for e in each.evidence])}")
    claims_text = data_block("claims", "\n".join(listing))
    try:
        judgement = await llm.structured(
            ClaimJudgement,
            agent="root",
            system=f"{REVIEW_SYSTEM}\n\n{UNTRUSTED_RULE}",
            user=f"{claims_text}\n\n문장마다 근거가 받쳐 주는지 판정해 줘.",
        )
    except LlmOutputError:
        return message, [_lowered(each) if each.item.application_id is not None else each for each in checked]
    verdicts = {verdict.id: verdict.verdict for verdict in judgement.verdicts}
    kept: list[Checked] = []
    by_index = {index: key for key, index in zip((key for key, _ in claims), owned, strict=True)}
    for index, each in enumerate(checked):
        verdict = verdicts.get(by_index[index]) if index in by_index else "SUPPORTED"
        if verdict == "UNRELATED":
            continue
        kept.append(_lowered(each) if verdict == "OVERSTATED" else each)
    if verdicts.get("M") == "OVERSTATED":
        message = MESSAGE_FALLBACK
    return message, kept


def answer_plan(message: str, checked: Sequence[Checked]) -> ChatPlan | None:
    """남은 항목이 없으면 None이다. 출처와 근거를 낸 분석 Agent는 처음 나온 순서다."""
    if not checked:
        return None
    return ChatPlan.answer(Intent.ANSWER, message, [each.item for each in checked], _sources(checked), _agents(checked))


def questions_plan(
    context: ChatContext, rows: Sequence[CandidateRow], form: QuestionsPlan, checked: Sequence[Checked]
) -> ChatPlan | None:
    """지원자별 확인할 점을 면접 질문 생성 요청으로 바꾼다. 메모 근거가 있으면 그 메모 원본도 넘긴다."""
    if not checked:
        return None
    focus: dict[UUID, str] = {}
    memos: dict[UUID, InterviewerMemo] = {}
    for row in rows:
        own = [each for each in checked if each.item.application_id == row.application_id]
        if not own:
            continue
        details = " ".join(
            f"{each.item.label} ({'근거 확인' if each.item.status == 'OK' else '추가 확인 필요'}): {each.item.text}"
            for each in own
        )
        focus[row.application_id] = FOCUS_WITH_REQUEST.format(focus=details, request=context.message)
        memo = next((evidence.memo for each in own for evidence in each.evidence if evidence.memo), None)
        if memo is not None:
            memos[row.application_id] = memo
    plan = ChatPlan.answer(
        Intent.ANSWER,
        QUESTIONS_REQUESTED.format(count=len(rows)),
        [each.item for each in checked],
        _sources(checked),
        list(dict.fromkeys([*_agents(checked), INTERVIEW_AGENT])),
    )
    update = {
        "question_targets": [row.application_id for row in rows],
        "question_focus": focus,
        "question_memos": memos,
        "question_replace": form.replace,
    }
    return plan.model_copy(update=update)


def focus_drafts(focus: Sequence[FocusDraft]) -> list[ItemDraft]:
    """확인할 점을 검토할 항목으로 바꾼다. 상태는 인용한 근거가 정한다."""
    return [
        ItemDraft(candidate=each.candidate, label=FOCUS_LABEL, text=each.text, status="OK", refs=each.refs)
        for each in focus
    ]


def _capped(context: ChatContext, ledger: Ledger, draft: ItemDraft) -> Checked | None:
    row = resolve_ref(context, draft.candidate) if draft.candidate is not None else None
    if draft.candidate is not None and row is None:
        return None
    owner = row.application_id if row is not None else None
    # 지원자 항목은 그 지원자와 공통 자료의 근거만, 공통 항목(전형 집계 등)은 지원자별 줄도 근거로 남긴다
    evidence = [
        found
        for ref in dict.fromkeys(ref.strip().upper() for ref in draft.refs)
        if (found := ledger.get(ref)) is not None and (owner is None or found.application_id in (None, owner))
    ]
    text = shorten(without_later_gaps(context, readable(draft.text, context)))
    if not text:
        return None
    status: str | None
    if row is None and not evidence:
        status = None
    else:
        status = "OK" if draft.status == "OK" and evidence and all(each.cap == "OK" for each in evidence) else "CHECK"
    item = ChatItem(application_id=owner, label=readable(draft.label, context), text=text, status=status)
    return Checked(item, evidence)


def _lowered(each: Checked) -> Checked:
    return Checked(each.item.model_copy(update={"status": "CHECK"}), each.evidence)


def _quotes(evidence: Sequence[Evidence]) -> str:
    return " / ".join(f"{each.quote or each.text} ({each.source})" for each in evidence) or "(근거 없음)"


def _sources(checked: Sequence[Checked]) -> list[str]:
    return list(dict.fromkeys(evidence.source for each in checked for evidence in each.evidence))


def _agents(checked: Sequence[Checked]) -> list[str]:
    return list(dict.fromkeys(evidence.agent for each in checked for evidence in each.evidence if evidence.agent))
