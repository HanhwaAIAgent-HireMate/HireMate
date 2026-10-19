"""C 선택 지원자 편집. 지시를 명령(동작, 대상)으로만 바꾸고, 실행은 backend가 대상과 권한을 검증한 뒤 한다 (규칙 2).

빼기는 불합격 처리가 아니다. 결정 상태는 바꾸지 않는다.
"""

from uuid import UUID

from hiremate_ai.agents.root.route import NOT_UNDERSTOOD, RootRoute
from hiremate_ai.agents.root.targets import Targets, checked
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, EditAction, Intent

NO_TARGET = "누구를 말씀하시는지 모르겠어요. @로 지원자를 골라 다시 말씀해 주세요."
NO_CHECKED = "체크한 지원자가 없어요. 리스트에서 체크한 뒤 다시 말씀해 주세요."
SAME_NAME = "{names} 이름의 지원자가 여러 명이에요. @로 골라 주세요."
ADDED = "{names} 님을 선택 지원자에 넣었어요."
REMOVED = "{names} 님을 선택 지원자에서 뺐어요."
CLEARED = "선택 지원자를 비웠어요. [되돌리기]로 돌아갈 수 있어요."
RESTORED = "이전 선택 지원자로 되돌렸어요."


def plan_edit(route: RootRoute, context: ChatContext, targets: Targets) -> ChatPlan:
    """대상이 분명하지 않으면 실행하지 않고 되묻는다. 동명이인이 하나라도 있으면 아무도 바꾸지 않는다.

    멘션이나 이름으로 가리킨 지원자가 있으면 체크한 지원자보다 앞선다.
    """
    match route.edit:
        case None:
            return ChatPlan.answer(Intent.CLARIFY, NOT_UNDERSTOOD)
        case EditAction.CLEAR:
            return _edit(EditAction.CLEAR, [], CLEARED)
        case EditAction.RESTORE:
            return _edit(EditAction.RESTORE, [], RESTORED)
    if route.uses_checked and not targets.rows and not targets.ambiguous:
        rows = checked(context)
        if not rows:
            return ChatPlan.answer(Intent.CLARIFY, NO_CHECKED)
    else:
        if targets.ambiguous:
            return ChatPlan.answer(Intent.CLARIFY, SAME_NAME.format(names=", ".join(targets.ambiguous)))
        rows = targets.rows
        if not rows:
            return ChatPlan.answer(Intent.CLARIFY, NO_TARGET)
    names = ", ".join(row.name for row in rows)
    message = (ADDED if route.edit is EditAction.ADD else REMOVED).format(names=names)
    return _edit(route.edit, [row.application_id for row in rows], message)


def _edit(action: EditAction, targets: list[UUID], message: str) -> ChatPlan:
    return ChatPlan(
        intent=Intent.EDIT,
        mode=None,
        edit=action,
        targets=targets,
        message=message,
        items=[],
        sources=[],
        agents=[],
        question_targets=[],
    )
