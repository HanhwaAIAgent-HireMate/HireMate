"""Root의 최종 명령에서 조회 범위, 실행 가능 상태와 원문 근거를 검증한다."""

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hiremate_ai.agents.guardrails import BLOCKED_REPLY, blocked_attribute
from hiremate_ai.agents.root.answer import (
    _REF,
    BULK_LIMIT,
    FOCUS_WITH_REQUEST,
    INTERVIEW_AGENT,
    MEMO_SOURCE,
    AnswerItem,
    _invalid_message,
    memo_evidence,
    readable,
    verify_items,
)
from hiremate_ai.agents.root.edit import plan_edit
from hiremate_ai.agents.root.stages import blames_later_stage
from hiremate_ai.agents.root.toolkit import RootToolkit, candidate_ref, resolve_ref, scope_of
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, ChatItem, ChatPlan, EditAction, Intent
from hiremate_ai.contract import InterviewerMemo, StageType

LOCKED = "결과를 확정한 전형이라 선택 지원자를 바꿀 수 없어요. 분석이나 요약은 계속 물어볼 수 있어요."
DECISION_REPLY = "합격과 불합격 결정, 결과 확정, 공고 게시와 안내 발송은 담당자가 화면에서 직접 실행해 주세요."
QUESTIONS_REQUESTED = "{count}명의 면접 질문 생성을 요청했어요."


class _Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnswerCommand(_Command):
    """자료에 근거한 분석과 업무 현황 답변. 특정 지원자는 candidates와 원문 근거 items를 작성한다."""

    kind: Literal["answer"] = "answer"
    candidates: list[str] = Field(default=[], description="답변 대상 지원자 번호. 전형 전체 질문이면 비운다")


class ConversationCommand(_Command):
    """인사, 감사, 말투 변경과 일반 기능 설명. 지원자 분석이나 선택 편집 요청에 대한 명령이 아니다."""

    kind: Literal["conversation"] = "conversation"


class FindCommand(_Command):
    """조건 검색으로 선택 목록을 교체, 추가, 좁힌다. 실제 검색 도구가 반환한 결과 번호만 참조한다."""

    kind: Literal["find"] = "find"
    result: str = Field(description="search_candidates가 반환한 검색 결과 식별자")


class EditCommand(_Command):
    """명확한 지원자를 선택 목록에 넣거나 뺀다. 미선택 지원자 전체 추가도 ADD와 대상 C번호로 실행한다."""

    kind: Literal["edit"] = "edit"
    action: EditAction
    candidates: list[str] = Field(default=[], description="편집할 지원자 번호. 비우기와 되돌리기에는 비운다")


class QuestionsCommand(_Command):
    """지원자별 면접 질문 생성 요청. 검증된 대상과 원문 근거 항목을 전달한다."""

    kind: Literal["questions"] = "questions"
    candidates: list[str] = Field(description="면접 질문을 만들 지원자 번호")
    focus: dict[str, str] = Field(
        default={}, description="지원자 번호별 확인할 점. 해당 지원자의 items.text 중 하나와 정확히 같은 값"
    )


class ClarifyCommand(_Command):
    """현재 화면과 앞 대화에도 없는 필수 정보만 되묻는다. 이미 알려준 조건을 다시 확인하지 않는다."""

    kind: Literal["clarify"] = "clarify"


class BlockedCommand(_Command):
    """차별 조건에 따른 탐색이나 선택 요청을 차단한다."""

    kind: Literal["blocked"] = "blocked"


class DecisionCommand(_Command):
    """합격, 불합격, 결과 확정, 게시, 발송은 담당자가 직접 실행하도록 안내한다."""

    kind: Literal["decision"] = "decision"


type RootCommand = Annotated[
    AnswerCommand
    | ConversationCommand
    | FindCommand
    | EditCommand
    | QuestionsCommand
    | ClarifyCommand
    | BlockedCommand
    | DecisionCommand,
    Field(discriminator="kind"),
]


def _require_all(schema: dict[str, Any]) -> None:
    # 기본값이 있는 인자도 빠뜨리지 않고 쓰게 모든 인자를 필수로 보여 준다
    schema["required"] = list(schema.get("properties", {}))


class _Reply(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all)

    message: str = Field(description="현재 요청에 대한 짧은 답. 분석 내용은 items에 적는다")

    @model_validator(mode="before")
    @classmethod
    def unused_arguments(cls, value: Any) -> Any:
        """다른 명령의 인자를 빈 값(null, "null", [], {})으로 적었으면 버리고, 실제 값을 넣었으면 알린다."""
        if not isinstance(value, dict):
            return value
        unused = [key for key in value if key not in cls.model_fields]
        filled = [key for key in unused if value[key] not in (None, "null", [], {})]
        if filled:
            raise ValueError(f"이 명령에서 사용하지 않는 인자가 있어요: {', '.join(filled)}")
        return {key: argument for key, argument in value.items() if key not in unused}


class AnswerReply(_Reply):
    """자료에 근거한 분석, 비교와 업무 현황 답변. 특정 지원자는 candidates와 지원자별 원문 근거 items를 작성한다."""

    items: list[AnswerItem] = Field(
        default=[], description="지원자별 원문 근거 항목. 전형 집계는 candidate=null인 항목에 전형 결과 근거를 쓴다"
    )
    candidates: list[str] = Field(default=[], description="답변 대상 지원자 C번호. 전형 전체 질문이면 []")


class ConversationReply(_Reply):
    """인사, 감사, 말투 변경과 일반 기능 설명. 지원자 분석이나 선택 편집 요청에 대한 답이 아니다."""


class FindReply(_Reply):
    """조건 검색 결과로 선택 목록을 교체, 추가, 좁힌다. 후보와 근거는 서버가 보존하므로 복사하지 않는다."""

    result: str = Field(description="search_candidates가 반환한 검색 결과 번호(S1 등)")


class EditReply(_Reply):
    """명확한 지원자를 선택 목록에 넣거나 뺀다. 미선택 지원자 전체 추가도 ADD와 대상 C번호로 실행한다."""

    action: EditAction = Field(description="ADD, REMOVE, CLEAR, RESTORE")
    candidates: list[str] = Field(default=[], description="편집할 지원자 C번호. 비우기와 되돌리기에는 []")


class QuestionsReply(_Reply):
    """지원자별 면접 질문 생성 요청. 검증된 대상과 확인할 점의 원문 근거 항목을 전달한다."""

    items: list[AnswerItem] = Field(default=[], description="지원자별 확인할 점과 원문 근거 항목")
    candidates: list[str] = Field(description="면접 질문을 만들 지원자 C번호")
    focus: dict[str, str] = Field(
        default={},
        description=(
            "지원자 번호별 확인할 점. 해당 지원자의 items.text 하나를 글자 그대로 복사한다. "
            "여러 항목의 요약이나 evidence.sentence를 새로 쓰지 않는다"
        ),
    )


class ClarifyReply(_Reply):
    """현재 화면과 앞 대화에도 없는 필수 정보만 되묻는다. 이미 알려준 조건을 다시 확인하지 않는다."""


class BlockedReply(_Reply):
    """차별 조건에 따른 탐색이나 선택 요청을 차단한다."""


class DecisionReply(_Reply):
    """합격, 불합격, 결과 확정, 게시, 발송은 담당자가 화면에서 직접 실행하도록 안내한다."""


# 모델이 보는 최종 답 도구. 이름이 명령 종류이고 각 도구에는 그 명령의 인자만 있다
REPLY_FORMS: dict[str, type[_Reply]] = {
    "answer": AnswerReply,
    "conversation": ConversationReply,
    "find": FindReply,
    "edit": EditReply,
    "questions": QuestionsReply,
    "clarify": ClarifyReply,
    "blocked": BlockedReply,
    "decision": DecisionReply,
}


class RootReply(BaseModel):
    """검증할 최종 명령. 모델이 고른 종류별 도구의 답을 본문, 근거 항목과 명령으로 나눈다."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(description="담당자에게 보여 줄 짧은 답")
    items: list[AnswerItem] = Field(default=[], description="지원자별 원문 근거 항목")
    command: RootCommand = Field(description="대화와 조회 결과에 근거한 최종 명령")

    @model_validator(mode="before")
    @classmethod
    def from_form(cls, value: Any) -> Any:
        """{"kind": 도구 이름, **인자}를 받으면 그 도구 형식으로 검증한다. 의도는 다시 추론하지 않는다."""
        if not isinstance(value, dict) or "command" in value:
            return value
        kind = value.get("kind")
        form = REPLY_FORMS.get(kind) if isinstance(kind, str) else None
        if form is None:
            raise ValueError(f"알 수 없는 최종 명령이에요: {kind}")
        reply = form.model_validate({key: argument for key, argument in value.items() if key != "kind"})
        arguments = reply.model_dump(exclude={"message", "items"})
        return {"message": reply.message, "items": getattr(reply, "items", []), "command": {"kind": kind, **arguments}}


async def compile_reply(
    reply: RootReply,
    context: ChatContext,
    toolkit: RootToolkit,
    searches: Mapping[str, ChatPlan],
    *,
    reviewed_conversation_subjects: Sequence[UUID] = (),
) -> ChatPlan:
    """의미와 대상을 다시 추론하지 않는다. 검증 실패는 수정 요청에 쓸 ValueError로 알린다.

    reviewed_conversation_subjects는 최근 기록과의 의미 검토를 통과한 일반 대화의 대상 참조에만 쓴다.
    새 지원자 사실의 근거나 분석 항목으로 사용하지 않는다.
    """
    command = reply.command
    if isinstance(command, BlockedCommand):
        return ChatPlan.answer(Intent.BLOCKED, BLOCKED_REPLY)
    if isinstance(command, DecisionCommand):
        return ChatPlan.answer(Intent.CLARIFY, DECISION_REPLY)
    conditions: list[str] = []
    if isinstance(command, EditCommand):
        conditions.append(reply.message)
    elif isinstance(command, QuestionsCommand):
        conditions.extend(command.focus.values())
    if blocked_attribute(context.message) or any(blocked_attribute(value) for value in conditions):
        return ChatPlan.answer(Intent.BLOCKED, BLOCKED_REPLY)
    if isinstance(command, FindCommand):
        plan = searches.get(command.result)
        if plan is None:
            raise ValueError("조회한 검색 결과가 아니에요. search_candidates가 반환한 결과 식별자를 사용하세요.")
        _check_plan_scope(plan, context)
        if plan.intent in (Intent.FIND, Intent.EDIT):
            _require_selectable(context)
        return plan
    if isinstance(command, EditCommand):
        _require_selectable(context)
        rows = _rows(context, command.candidates)
        if command.action in (EditAction.CLEAR, EditAction.RESTORE):
            if rows:
                raise ValueError("선택 비우기와 되돌리기 명령에는 대상 지원자를 넣지 마세요.")
        elif not rows:
            raise ValueError("편집할 대상 지원자를 명시하세요. 불분명하면 되물어 주세요.")
        return plan_edit(command.action, context, rows)
    message = _message(reply.message, context)
    if isinstance(command, ConversationCommand):
        if reply.items:
            raise ValueError("일반 대화에는 지원자 분석 항목을 넣지 마세요. 자료에 근거한 답변은 answer로 작성하세요.")
        _check_message_subjects(reply.message, context, [], reviewed_conversation_subjects)
        return ChatPlan.answer(Intent.ANSWER, message)
    if isinstance(command, ClarifyCommand):
        if reply.items:
            raise ValueError("되묻기에는 지원자 분석 항목을 넣지 마세요.")
        return ChatPlan.answer(Intent.CLARIFY, message)
    rows = _rows(context, command.candidates)
    if isinstance(command, QuestionsCommand):
        return await _questions(reply, command, context, toolkit, rows)
    items, sources, agents = await _items(reply.items, context, toolkit, rows, require_each=bool(rows))
    _check_message_subjects(reply.message, context, items)
    return ChatPlan.answer(Intent.ANSWER, message, items, sources, agents)


def _rows(context: ChatContext, refs: Sequence[str]) -> list[CandidateRow]:
    rows: list[CandidateRow] = []
    seen: set[UUID] = set()
    for ref in refs:
        row = resolve_ref(context, ref)
        if row is None:
            raise ValueError(
                f"지원자 번호 {ref!r}는 현재 전형에 없어요. resolve_candidates로 이름을 확인하고, "
                "찾지 못했거나 동명이인이면 clarify로 되물어 주세요. 다른 사람으로 대신하지 마세요."
            )
        if row.application_id in seen:
            raise ValueError("같은 지원자를 여러 번 지정하지 마세요.")
        seen.add(row.application_id)
        rows.append(row)
    return rows


def _require_selectable(context: ChatContext) -> None:
    if not context.selectable:
        raise ValueError(LOCKED)


def _check_plan_scope(plan: ChatPlan, context: ChatContext) -> None:
    allowed = {row.application_id for row in context.candidates}
    used = {*plan.targets, *plan.question_targets, *plan.question_focus, *plan.question_memos}
    used.update(item.application_id for item in plan.items if item.application_id is not None)
    if used - allowed:
        raise ValueError("검색 결과에 현재 전형 밖의 지원자가 있어요. 현재 전형 안에서 다시 조회하세요.")
    if plan.edit is not None or plan.question_targets or plan.question_focus or plan.question_memos:
        raise ValueError("검색 결과에는 선택 편집이나 면접 질문 명령을 담을 수 없어요.")


def _message(text: str, context: ChatContext) -> str:
    message = readable(text, context)
    if _invalid_message(message):
        raise ValueError("본문은 내부 필드나 JSON 없이 담당자가 읽을 문장으로 작성하세요.")
    if blames_later_stage(context, message):
        raise ValueError("아직 진행하지 않은 전형의 자료는 생기기 전이에요. 부족한 자료로 쓰지 마세요.")
    return message


def _check_message_subjects(
    text: str,
    context: ChatContext,
    items: Sequence[ChatItem],
    reviewed_conversation_subjects: Sequence[UUID] = (),
) -> None:
    """지원자 사실을 본문에만 써서 근거 항목 검증을 우회하지 못하게 한다."""
    present = {item.application_id for item in items if item.application_id is not None} | set(
        reviewed_conversation_subjects
    )
    missing: list[str] = []
    for match in _REF.finditer(text):
        row = resolve_ref(context, match.group(1))
        if row is None or row.application_id not in present:
            missing.append(candidate_ref(context, row.application_id) if row else f"C{match.group(1)}")
    remaining = readable(text, context)
    for name in sorted({row.name for row in context.candidates if row.name}, key=len, reverse=True):
        if name not in remaining:
            continue
        same_name = {row.application_id for row in context.candidates if row.name == name}
        if not same_name & present:
            missing.extend(candidate_ref(context, row.application_id) for row in context.candidates if row.name == name)
        remaining = remaining.replace(name, "\0")
    if missing:
        raise ValueError(
            f"본문에서 언급한 지원자 {', '.join(dict.fromkeys(missing))}의 검증된 항목이 없어요. "
            "대상과 근거가 연결된 항목이 필요해요. "
            "candidates에 번호만 추가해도 해결되지 않아요. 해당 지원자의 근거를 확인한 items를 작성하거나 "
            "본문에서 그 지원자에 관한 언급을 삭제하세요. 자료에서 확인하지 못한 내용을 없다고 단정하지 마세요."
        )


async def _items(
    raw: Sequence[AnswerItem],
    context: ChatContext,
    toolkit: RootToolkit,
    rows: Sequence[CandidateRow],
    *,
    require_each: bool,
) -> tuple[list[ChatItem], list[str], list[str]]:
    target_ids = {row.application_id for row in rows}
    for item in raw:
        if item.candidate is not None:
            _rows(context, [item.candidate])
        if blames_later_stage(context, f"{item.label} {item.text}"):
            raise ValueError("아직 진행하지 않은 전형의 자료가 없다는 항목을 작성하지 마세요.")
    candidate_ids = {
        row.application_id
        for item in raw
        if item.candidate is not None and (row := resolve_ref(context, item.candidate)) is not None
    }
    recorded = await toolkit.evidence(scope_of(context), list(target_ids | candidate_ids))
    items, sources, agents = verify_items(raw, context, rows[0] if len(rows) == 1 else None, recorded)
    if len(items) != len(raw):
        raise ValueError("항목의 지원자 번호가 현재 전형에 없어요.")
    for number, (original, verified) in enumerate(zip(raw, items, strict=True), start=1):
        if verified.application_id is not None and target_ids and verified.application_id not in target_ids:
            raise ValueError("대상 지원자 밖의 항목을 작성하지 마세요.")
        if original.status == "OK" and verified.status == "CHECK":
            raise ValueError(
                f"{number}번 항목의 원문 근거가 충분하지 않아요. "
                "해당 항목의 대상과 출처에 맞는 원문을 인용하거나 확인이 필요한 내용으로 다시 작성하세요. "
                "서로 다른 문장을 이어 붙이지 말고 evidence의 별도 항목으로 나누세요. "
                "프로필은 '근거:' 문장과 실제 출처를 쓰세요. 프로필의 경력과 점수 요약은 평가 제출물 원문이 아니에요. "
                "지원자 문서를 인용하는 비교 항목은 지원자별로 나누고 각 candidate를 지정하세요."
            )
        if _invalid_message(verified.label) or _invalid_message(verified.text):
            raise ValueError("항목은 내부 필드나 JSON 없이 담당자가 읽을 문장으로 작성하세요.")
        _check_message_subjects(f"{original.label} {original.text}", context, [verified])
    present = {item.application_id for item in items}
    if require_each and target_ids - present:
        raise ValueError("대상 지원자별 항목을 하나 이상 작성하세요. 자료가 부족하면 CHECK 항목으로 설명하세요.")
    return items, sources, agents


async def _questions(
    reply: RootReply,
    command: QuestionsCommand,
    context: ChatContext,
    toolkit: RootToolkit,
    rows: Sequence[CandidateRow],
) -> ChatPlan:
    if context.stage_type is not StageType.INTERVIEW:
        raise ValueError("면접 질문 생성 명령은 면접 전형에서만 사용할 수 있어요.")
    if not rows or len(rows) > BULK_LIMIT:
        raise ValueError(f"질문을 만들 대상 지원자를 1명 이상 {BULK_LIMIT}명 이하로 지정하세요.")
    target_ids = {row.application_id for row in rows}
    requested_focus = dict(command.focus)
    # 모델이 메모 근거 항목을 선택하고 선택적 focus만 비웠다면 그 항목을 그대로 전달한다.
    # 요청 문장의 낱말로 의도를 재분류하거나 확인 목표를 새로 만들지 않는다.
    for raw in reply.items:
        row = resolve_ref(context, raw.candidate) if raw.candidate else None
        if (
            row is not None
            and row.application_id in target_ids
            and any(memo_evidence(context, row, evidence) is not None for evidence in raw.evidence)
        ):
            requested_focus.setdefault(raw.candidate or "", raw.text)
    focused = _rows(context, list(requested_focus))
    if any(row.application_id not in target_ids for row in focused):
        raise ValueError("질문 대상 지원자에게만 확인할 점을 작성하세요.")
    items, sources, agents = await _items(reply.items, context, toolkit, rows, require_each=False)
    focus: dict[UUID, str] = {}
    memos: dict[UUID, InterviewerMemo] = {}
    for ref, text in requested_focus.items():
        row = resolve_ref(context, ref)
        if row is None:
            raise ValueError("확인할 점의 대상 지원자가 현재 전형에 없어요.")
        own = [
            (raw, verified)
            for raw, verified in zip(reply.items, items, strict=True)
            if verified.application_id == row.application_id
        ]
        if text not in {raw.text for raw, _ in own}:
            raise ValueError("확인할 점은 해당 지원자의 검증된 항목 text 중 하나와 정확히 같아야 해요.")
        details = " ".join(
            f"{item.label} ({'근거 확인' if item.status == 'OK' else '추가 확인 필요'}): {item.text}" for _, item in own
        )
        focus[row.application_id] = FOCUS_WITH_REQUEST.format(focus=details, request=context.message)
        for raw, _ in own:
            if raw.text != text:
                continue
            for evidence in raw.evidence:
                if memo := memo_evidence(context, row, evidence):
                    memos[row.application_id] = memo
                    break
            if row.application_id in memos:
                break
        if (
            any(
                "".join(evidence.source.split()) == MEMO_SOURCE
                for raw, _ in own
                if raw.text == text
                for evidence in raw.evidence
            )
            and row.application_id not in memos
        ):
            raise ValueError("질문에 참고할 해당 지원자의 면접관메모 원문을 확인해 주세요.")
    if MEMO_SOURCE in sources and not memos:
        raise ValueError("메모 원문에 연결한 확인할 점을 focus로 전달해 주세요.")
    plan = ChatPlan.answer(
        Intent.ANSWER,
        QUESTIONS_REQUESTED.format(count=len(rows)),
        items,
        sources,
        list(dict.fromkeys([*agents, INTERVIEW_AGENT])),
    )
    return plan.model_copy(
        update={
            "question_targets": [row.application_id for row in rows],
            "question_focus": focus,
            "question_memos": memos,
        }
    )
