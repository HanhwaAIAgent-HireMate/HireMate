"""대화방에 남기는 턴 기록. 질문, 답, 대상 순서, 답 항목, 면접 질문의 확인할 점만 남긴다 (기획 15절).

지원자 문서 본문은 넣지 않는다. 값은 JSON으로 저장할 수 있는 글자와 숫자만 쓴다.
"""

from collections.abc import Sequence
from typing import Any, TypedDict
from uuid import UUID

from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Intent, SelectionMode


class TurnItem(TypedDict):
    application_id: str | None
    label: str
    text: str


class Turn(TypedDict):
    message: str
    kind: str  # 분류한 요청 종류 (FIND, EDIT, ANSWER 등). 차단하거나 분류하지 못했으면 빈 값
    intent: str
    targets: list[str]  # 이 턴이 다룬 지원자 순서. 찾기 결과, 편집 대상, 면접 질문 대상, 답의 지원자 순
    answer: str  # 답 메시지 ({count}, {total} 자리 그대로)
    items: list[TurnItem]
    focus: dict[str, str]
    total: int  # 그때 전형 인원
    plan: dict[str, Any]  # 화면에 다시 보여 줄 계획 (ChatPlan JSON)


def turn_of(context: ChatContext, targets: Sequence[UUID] | None, plan: ChatPlan, kind: str = "") -> Turn:
    """찾기 턴은 찾은 결과만 남긴다. 아무도 못 찾았으면 비워 둔다.

    합격 · 불합격한 지원자 안에서 찾았으면 선택 지원자를 바꾸지 않아 찾은 사람은 답 항목에만 있다.
    """
    answered = list(dict.fromkeys(item.application_id for item in plan.items if item.application_id))
    subject: list[UUID] = (list(plan.targets) or answered) if kind == "FIND" else plan.targets or plan.question_targets
    if not subject and kind != "FIND":
        subject = answered
    if not subject and kind != "FIND" and targets is not None:
        subject = list(targets)
    return Turn(
        message=context.message,
        kind=kind,
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
        plan=plan.model_dump(mode="json"),
    )


def remember(turns: list[Turn], turn: Turn, limit: int) -> list[Turn]:
    return [*turns, turn][-limit:]


def next_result(result: list[str] | None, kind: str, mode: SelectionMode | None, plan: ChatPlan) -> list[str] | None:
    """지금 결과 목록. 찾기와 면접 질문 만들기만 바꾼다. None은 아직 결과 목록을 만든 적이 없다는 뜻이다.

    새로 찾았는데 아무도 없으면 비운다. 좁히기 · 추가가 비면 화면의 선택 지원자처럼 그대로 둔다.
    합격 · 불합격한 지원자 안에서 찾은 답이면 선택 지원자는 그대로지만 답 항목의 지원자를 결과 목록으로 둔다.
    """
    if plan.question_targets:
        return [str(application_id) for application_id in plan.question_targets]
    if kind != "FIND":
        return result
    ids = [str(application_id) for application_id in plan.targets]
    if plan.intent is Intent.FIND:
        if mode is SelectionMode.ADD:
            kept = result or []
            return kept + [application_id for application_id in ids if application_id not in kept]
        return ids
    answered = [str(item.application_id) for item in plan.items if item.application_id]
    if plan.intent is Intent.ANSWER and answered:
        return list(dict.fromkeys(answered))
    if plan.intent is Intent.ANSWER and mode in (None, SelectionMode.REPLACE):
        return []
    return result
