"""대화방에 남기는 턴 기록. 질문, 답, 대상 순서, 답 항목, 면접 질문의 확인할 점과 처리 단계 문구만 남긴다 (기획 15절).

지원자 문서 본문은 넣지 않는다. 값은 JSON으로 저장할 수 있는 글자와 숫자만 쓴다.
"""

from collections.abc import Sequence
from typing import Any, NotRequired, TypedDict
from uuid import UUID

from hiremate_ai.agents.root.progress import Step
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Intent, SelectionMode


class TurnItem(TypedDict):
    application_id: str | None
    label: str
    text: str
    status: NotRequired[str | None]  # 예전 체크포인트에는 없다. 읽을 때 검증된 계획과 대조한다


class Turn(TypedDict):
    message: str
    mentions: NotRequired[list[str]]  # 그때 멘션한 지원자. 답변 대상이 없는 되묻기에도 남긴다
    checked: NotRequired[list[str]]  # 그때 체크한 지원자. 예전 체크포인트에는 두 필드가 없다
    kind: str  # 분류한 요청 종류 (FIND, EDIT, ANSWER 등). 차단하거나 분류하지 못했으면 빈 값
    intent: str
    targets: list[str]  # 이 턴이 다룬 지원자 순서. 찾기 결과, 편집 대상, 면접 질문 대상, 답의 지원자 순
    answer: str  # 답 메시지 ({count}, {total} 자리 그대로)
    items: list[TurnItem]
    focus: dict[str, str]
    total: int  # 그때 전형 인원
    plan: dict[str, Any]  # 화면에 다시 보여 줄 계획 (ChatPlan JSON)
    mode: NotRequired[str | None]
    result_before: NotRequired[list[str] | None]
    subject_before: NotRequired[list[str]]
    proposed_plan: NotRequired[dict[str, Any]]  # 업무 서버가 보정하기 전 계획. 중복 응답을 구분한다
    # 그때 화면에 낸 단계 (코드 상수 문구와 깊이). 예전 체크포인트에는 없거나 문구만 있다
    steps: NotRequired[list[Step] | list[str]]
    seconds: NotRequired[int]  # 요청 확인부터 턴을 남기기까지 걸린 시간
    asker: NotRequired[dict[str, str] | None]  # 질문한 담당자 (member_id, name). 탭 대화방을 함께 쓴다


def turn_of(context: ChatContext, targets: Sequence[UUID] | None, plan: ChatPlan, kind: str = "") -> Turn:
    """찾기 턴은 찾은 결과만 남긴다. 아무도 못 찾았으면 비워 둔다.

    합격 · 불합격한 지원자 안에서 찾았으면 선택 지원자를 바꾸지 않아 찾은 사람은 답 항목에만 있다.
    """
    turn = Turn(
        message=context.message,
        mentions=[str(application_id) for application_id in context.mentions],
        checked=[str(application_id) for application_id in context.checked],
        kind=kind,
        intent="",
        targets=[],
        answer="",
        items=[],
        focus={},
        total=len(context.candidates),
        plan={},
        asker=(
            {"member_id": str(context.asker.member_id), "name": context.asker.name}
            if context.asker is not None
            else None
        ),
    )
    return update_turn(turn, plan, targets)


def update_turn(turn: Turn, plan: ChatPlan, targets: Sequence[UUID] | None = None) -> Turn:
    """보정된 계획의 대상과 근거만 남긴다. 원래 질문과 전형 인원은 보존한다."""
    answered = list(dict.fromkeys(item.application_id for item in plan.items if item.application_id))
    kind = turn["kind"]
    subject: list[UUID] = (list(plan.targets) or answered) if kind == "FIND" else plan.targets or plan.question_targets
    if not subject and kind != "FIND":
        subject = answered
    if not subject and kind != "FIND" and targets is not None:
        subject = list(targets)
    return {
        **turn,
        "intent": plan.intent.value,
        "targets": [str(application_id) for application_id in subject],
        "answer": plan.message,
        "items": [
            TurnItem(
                application_id=str(item.application_id) if item.application_id else None,
                label=item.label,
                text=item.text,
                status=item.status,
            )
            for item in plan.items
        ],
        "focus": {str(application_id): focus for application_id, focus in plan.question_focus.items()},
        "plan": plan.model_dump(mode="json"),
    }


def verified_turn_items(turn: Turn) -> list[TurnItem]:
    """간결한 검증 항목만 돌려준다. 구형 상태는 같은 대상과 문장의 계획에서만 복구한다."""
    planned = turn["plan"].get("items", [])
    items: list[TurnItem] = []
    for item in turn["items"]:
        statuses = [
            candidate.get("status")
            for candidate in planned
            if (
                candidate.get("applicationId", candidate.get("application_id")),
                candidate.get("label"),
                candidate.get("text"),
            )
            == (item["application_id"], item["label"], item["text"])
        ]
        status = item.get("status")
        if status is None:
            status = "OK" if statuses and all(value == "OK" for value in statuses) else "CHECK"
        elif status not in ("OK", "CHECK") or "CHECK" in statuses:
            status = "CHECK"
        items.append(
            TurnItem(application_id=item["application_id"], label=item["label"], text=item["text"], status=status)
        )
    return items


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
