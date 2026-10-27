"""명시적인 선택 편집 명령의 실행 가능 여부를 확인한다. 실행은 backend가 담당한다."""

from collections.abc import Sequence
from uuid import UUID

from hiremate_ai.agents.root.types import CandidateRow, ChatContext, ChatItem, ChatPlan, Decision, EditAction, Intent
from hiremate_ai.contract import StageType

NO_TARGET = "누구를 말씀하시는지 모르겠어요. @로 지원자를 골라 다시 말씀해 주세요."
ADDED = "{names} 님을 선택 지원자에 넣었어요."
REMOVED = "{names} 님을 선택 지원자에서 뺐어요."
CLEARED = "선택 지원자를 비웠어요. [되돌리기]로 돌아갈 수 있어요."
RESTORED = "이전 선택 지원자로 되돌렸어요."
DECIDED = "{names} 님은 이미 {decided} 지원자라 선택 지원자에 넣을 수 없어요. 리스트의 {tabs} 탭에서 모아 볼 수 있어요."
BELOW_LINE = "{names} 님은 기준선 아래라 선택 지원자에 넣을 수 없어요. 먼저 기준선 위로 올려 주세요."
_DECIDED_WORDS = {
    frozenset({Decision.PASS}): ("합격 처리한", "'합격'"),
    frozenset({Decision.FAIL}): ("불합격 처리한", "'불합격'"),
    frozenset({Decision.PASS, Decision.FAIL}): ("합격과 불합격을 정한", "'합격', '불합격'"),
}


def plan_edit(action: EditAction, context: ChatContext, rows: Sequence[CandidateRow]) -> ChatPlan:
    """모델이 정한 대상만 사용한다. 넣을 수 없는 지원자는 명령에서 빼고 이유를 설명한다."""
    if action is EditAction.CLEAR:
        return _edit(EditAction.CLEAR, [], CLEARED)
    if action is EditAction.RESTORE:
        return _edit(EditAction.RESTORE, [], RESTORED)
    if not rows:
        return ChatPlan.answer(Intent.CLARIFY, NO_TARGET)
    if action is EditAction.REMOVE:
        return _edit(EditAction.REMOVE, [row.application_id for row in rows], REMOVED.format(names=_names(rows)))
    selectable = [row for row in rows if _selectable(context, row)]
    reasons = _unselectable(context, [row for row in rows if row not in selectable])
    if not selectable:
        return ChatPlan.answer(Intent.CLARIFY, " ".join(reasons))
    message = " ".join([ADDED.format(names=_names(selectable)), *reasons])
    return _edit(EditAction.ADD, [row.application_id for row in selectable], message, reasons)


def _selectable(context: ChatContext, row: CandidateRow) -> bool:
    """backend가 선택 지원자에 넣는 지원자: 미결정이고, 서류 전형이면 기준선 위(올린 지원자 포함)다."""
    return row.decision is Decision.PENDING and (context.stage_type is not StageType.DOCUMENT or row.above_line)


def _unselectable(context: ChatContext, rows: Sequence[CandidateRow]) -> list[str]:
    decided = [row for row in rows if row.decision is not Decision.PENDING]
    below = [row for row in rows if row not in decided]
    reasons = []
    if decided:
        words, tabs = _DECIDED_WORDS[frozenset(row.decision for row in decided)]
        reasons.append(DECIDED.format(names=_names(decided), decided=words, tabs=tabs))
    if below:
        reasons.append(BELOW_LINE.format(names=_names(below)))
    return reasons


def _names(rows: Sequence[CandidateRow]) -> str:
    return ", ".join(row.name for row in rows)


def _edit(action: EditAction, targets: list[UUID], message: str, reasons: Sequence[str] = ()) -> ChatPlan:
    return ChatPlan(
        intent=Intent.EDIT,
        mode=None,
        edit=action,
        targets=targets,
        message=message,
        items=[ChatItem(application_id=None, label="선택 불가", text=reason, status="CHECK") for reason in reasons],
        sources=[],
        agents=[],
        question_targets=[],
        question_focus={},
    )
