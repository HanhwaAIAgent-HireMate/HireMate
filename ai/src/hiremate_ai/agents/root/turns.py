"""대화방에 남기는 턴 기록. 질문, 답, 대상 순서, 답 항목, 면접 질문의 확인할 점만 남긴다 (기획 15절).

지원자 문서 본문은 넣지 않는다. 값은 JSON으로 저장할 수 있는 글자와 숫자만 쓴다.
"""

from typing import TypedDict
from uuid import UUID

from hiremate_ai.agents.root.targets import Targets
from hiremate_ai.agents.root.types import ChatContext, ChatPlan


class TurnItem(TypedDict):
    application_id: str | None
    label: str
    text: str


class Turn(TypedDict):
    message: str
    intent: str
    targets: list[str]  # 이 턴이 다룬 지원자 순서. 찾기 결과, 편집 대상, 면접 질문 대상, 답의 지원자 순
    answer: str  # 답 메시지 ({count}, {total} 자리 그대로)
    items: list[TurnItem]
    focus: dict[str, str]
    total: int  # 그때 전형 인원


def turn_of(context: ChatContext, targets: Targets | None, plan: ChatPlan) -> Turn:
    subject: list[UUID] = plan.targets or plan.question_targets
    if not subject:
        subject = list(dict.fromkeys(item.application_id for item in plan.items if item.application_id))
    if not subject and targets is not None:
        subject = [row.application_id for row in targets.rows]
    return Turn(
        message=context.message,
        intent=plan.intent.value,
        targets=[str(application_id) for application_id in subject],
        answer=plan.message,
        items=[
            TurnItem(
                application_id=str(item.application_id) if item.application_id else None,
                label=item.label,
                text=item.text,
            )
            for item in plan.items
        ],
        focus={str(application_id): focus for application_id, focus in plan.question_focus.items()},
        total=len(context.candidates),
    )


def remember(turns: list[Turn], turn: Turn, limit: int) -> list[Turn]:
    return [*turns, turn][-limit:]
