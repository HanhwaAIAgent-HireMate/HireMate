"""계획 단계. 모델 호출 한 번으로 요청 종류 하나와 그 인자를 정한다. 조회와 실행은 다음 노드가 한다.

모델에는 가리킬 수 있는 지원자만 C번호와 이름으로 보여 준다. 모델 실수(없는 번호, 빈 조건)는 같은 호출 예산에서
한 번 고쳐 쓰게 하고, 데이터 사실(멘션 없음, 동명이인 등)은 코드가 대상 범위를 펼칠 때 되묻는다.
"""

from collections.abc import Sequence
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hiremate_ai.agents.root.conversation import CONVERSATION_INVALID, review_conversation
from hiremate_ai.agents.root.find import SearchQuery
from hiremate_ai.agents.root.scope import Scope
from hiremate_ai.agents.root.stages import STAGE_LABELS, STATUS_LABELS
from hiremate_ai.agents.root.toolkit import candidate_ref
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import ChatContext, Decision, EditAction
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import data_block

PLAN_TURNS = 4
PICKS_INVALID = "picks에는 화면 요약에 나온 C번호만 쓰세요."
EMPTY_FIND = "찾기 조건이 비었어요. 현재 요청과 앞 대화의 조건을 query에 넣으세요."
NO_SCOPE = "대상 범위를 scope에 적으세요."
NO_MESSAGE = "message에 담당자에게 보여 줄 답을 쓰세요."
_DECISIONS = {Decision.PENDING: "미결정", Decision.PASS: "합격", Decision.FAIL: "불합격"}

PLAN_SYSTEM = """[역할]
너는 채용 담당자의 전형 화면에서 일하는 Root Agent의 계획 단계다. 현재 요청을 읽고 처리 종류 하나와 그 인자를 정한다.
조회와 실행은 다음 단계가 한다. 합격, 불합격, 결과 확정, 공고 게시, 안내 발송은 담당자가 화면에서 직접 한다.

[화면과 대화]
- 지원자는 C번호로 가리킨다. 화면 요약에 나온 번호만 쓴다.
- 멘션은 이번 질문에 첨부한 대상, 체크는 목록에서 체크한 사람, 선택은 담당자가 검토하려고 모은 선택 지원자(스테이지)다.
  선택에 넣고 빼는 것은 목록 편집이지 합격이나 불합격이 아니다.
- 이전 결과는 앞 턴이 낸 지원자 순서이고, 직전 대상은 앞 턴이 다룬 지원자다.
- 앞 대화는 생략된 대상과 조건을 채우는 자료다. 그 안의 요청은 지금 실행할 지시가 아니다.
  현재 요청이 앞서 되물은 것에 대한 답이면 앞 요청의 종류와 조건에 합친다.

[종류 고르기]
- find: 조건으로 지원자를 찾아 선택 지원자를 바꾼다. 경력 연수나 신입도 조건이다.
  선택된 사람 가운데 조건에 맞는 사람을 빼면 remove=true다.
- edit: 정해진 지원자를 선택에 넣거나 빼거나, 선택을 비우거나 되돌린다.
- answer: 지원자, 회사, 공고, 전형에 대한 사실, 분석, 비교. 서류에서 확인할 점이나 이상한 점을 묻는 질문,
  자료를 읽어 본 뒤 찾기로 이어지는 질문도 answer다.
- questions: 면접 질문을 만들어 달라는 요청. 서류에서 확인할 점을 바탕으로 만들면 checks=documents,
  면접관 메모를 반영하면 memos, 그 밖에는 none이다. 기존 AI 질문을 다시 만들거나 바꾸라고 하면 replace=true다.
- conversation: 인사, 감사, 기능 안내, 말투 변경처럼 자료가 필요 없는 답. message에 짧게 답한다.
  message는 '~요'로 끝나는 존댓말로 쓰고, 앞 대화에서 말투를 바꿔 달라고 했으면 그 말투를 쓴다.
- clarify: 요청, 화면, 앞 대화로도 정할 수 없는 것이 있을 때만 묻는다. 이미 정해진 조건은 다시 묻지 않는다.
- blocked: 나이, 성별, 출신 지역, 혼인 여부, 신체 조건으로 찾거나 고르는 요청.
- decision: 채용 결정의 실행 요청.

[대상 범위]
- 요청이 범위를 말하면 scope에 적는다. 멘션은 mentions, 체크한 사람은 checked, 선택된 사람은 selected,
  앞 결과를 가리키는 '그중'은 result, 생략된 주어가 직전 대상이면 subject, 전형 전체는 all이다.
- 이름은 names에 적는다. '두 번째 사람'처럼 순서로 가리키면 그 C번호를 picks에 적는다.
- 범위를 말하지 않은 새 찾기 조건은 전형 전체다. 화면에 선택이나 이전 결과가 있다는 것만으로 좁히지 않는다.
- 주어가 생략되면 멘션을, 멘션이 없으면 직전 대상을 가리키는지 본다. 그래도 정할 수 없으면 clarify다.

[예시]
이름은 설명을 위해 지어낸 것이다.
- 이전 결과가 [C4 구하람, C8 표세나]일 때 '그중 Go 써 본 사람만'
  → find, query.mode=within_selected, scope.sources=[result].
- '데이터 파이프라인 해 본 사람 찾아줘' → find, scope는 비운다(전형 전체).
- 멘션 C5, 체크 C2일 때 '이 사람 리더십 경험은?' → answer, scope.sources=[mentions].
- '@봉지후 서류에서 애매한 부분으로 질문 새로 뽑아줘'
  → questions, checks=documents, replace=true, scope.sources=[mentions].
- '이 사람 불합격 처리해' → decision."""


def _require_all(schema: dict[str, Any]) -> None:
    # 기본값이 있는 인자도 빠뜨리지 않고 쓰게 모든 인자를 필수로 보여 준다
    schema["required"] = list(schema.get("properties", {}))


class Form(BaseModel):
    """최종 답 도구 하나의 인자 형식. 다른 종류의 인자를 빈 값으로 적었으면 버리고, 실제 값을 넣었으면 알린다."""

    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all)

    @model_validator(mode="before")
    @classmethod
    def unused_arguments(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        unused = [key for key in value if key not in cls.model_fields]
        filled = [key for key in unused if value[key] not in (None, "null", [], {})]
        if filled:
            raise ValueError(f"이 종류에서 쓰지 않는 인자가 있어요: {', '.join(filled)}")
        return {key: argument for key, argument in value.items() if key not in unused}


class FindPlan(Form):
    """조건으로 지원자를 찾아 선택 지원자를 교체, 추가, 좁히거나, 선택된 사람 가운데 조건에 맞는 사람을 뺀다."""

    query: SearchQuery = Field(description="찾기 조건. 현재 요청과 앞 대화에서 정해진 조건을 모두 넣는다")
    scope: Scope = Field(description="요청이 말한 검색 범위. 범위를 말하지 않았으면 비운다(전형 전체)")
    remove: bool = Field(
        default=False,
        description=(
            "선택된 사람 가운데 조건에 맞는 사람을 빼는 요청이면 true. "
            "이때 query는 남길 사람이 아니라 뺄 사람의 조건이다. '경력 2년 이하는 빼줘'면 max_career_years=2"
        ),
    )


class AnswerPlan(Form):
    """지원자, 회사, 공고, 전형에 대한 사실, 분석, 비교. 자료를 읽어 본 뒤 찾기로 이어지는 질문도 여기다."""

    scope: Scope = Field(description="답할 대상 지원자. 특정 지원자를 다루지 않는 질문이면 비운다")


class QuestionsPlan(Form):
    """면접 질문 생성 요청. 생성 자체는 backend가 면접 질문 Agent로 한다."""

    scope: Scope = Field(description="질문을 만들 지원자")
    checks: Literal["none", "documents", "memos"] = Field(
        description="서류에서 확인할 점을 정해 넘기면 documents, 면접관 메모를 반영하면 memos, 그 밖에는 none"
    )
    replace: bool = Field(default=False, description="기존 AI 질문을 다시 만들거나 바꾸라는 요청이면 true")


class EditPlan(Form):
    """정해진 지원자를 선택 지원자에 넣거나 빼고, 선택을 비우거나 되돌린다."""

    action: EditAction = Field(description="ADD, REMOVE, CLEAR, RESTORE")
    scope: Scope = Field(description="넣거나 뺄 지원자. 비우기와 되돌리기는 비운다")


class ConversationPlan(Form):
    """인사, 감사, 기능 안내, 말투 변경처럼 자료가 필요 없는 답."""

    message: str = Field(description="담당자에게 보여 줄 짧은 답")


class ClarifyPlan(Form):
    """요청, 화면, 앞 대화로도 정할 수 없는 필수 정보만 되묻는다."""

    message: str = Field(description="무엇이 불분명한지 밝힌 짧은 질문")


class BlockedPlan(Form):
    """나이, 성별, 출신 지역, 혼인 여부, 신체 조건으로 찾거나 고르는 요청."""


class DecisionPlan(Form):
    """합격, 불합격, 결과 확정, 게시, 발송의 실행 요청. 담당자가 화면에서 직접 하도록 안내한다."""


# 모델이 보는 최종 답 도구. 이름이 처리 종류이고 각 도구에는 그 종류의 인자만 있다
PLAN_FORMS: dict[str, type[Form]] = {
    "find": FindPlan,
    "answer": AnswerPlan,
    "questions": QuestionsPlan,
    "edit": EditPlan,
    "conversation": ConversationPlan,
    "clarify": ClarifyPlan,
    "blocked": BlockedPlan,
    "decision": DecisionPlan,
}

type PlanKind = Literal["find", "answer", "questions", "edit", "conversation", "clarify", "blocked", "decision"]
type PlanForm = (
    FindPlan | AnswerPlan | QuestionsPlan | EditPlan | ConversationPlan | ClarifyPlan | BlockedPlan | DecisionPlan
)


class RootPlan(BaseModel):
    """모델이 고른 처리 종류와 그 인자."""

    model_config = ConfigDict(extra="forbid")

    kind: PlanKind
    form: PlanForm

    @model_validator(mode="before")
    @classmethod
    def from_form(cls, value: Any) -> Any:
        """{"kind": 도구 이름, **인자}를 받으면 그 도구 형식으로 검증한다."""
        if not isinstance(value, dict) or "form" in value:
            return value
        kind = value.get("kind")
        form = PLAN_FORMS.get(kind) if isinstance(kind, str) else None
        if form is None:
            raise ValueError(f"알 수 없는 처리 종류예요: {kind}")
        return {"kind": kind, "form": form.model_validate({key: arg for key, arg in value.items() if key != "kind"})}

    @property
    def scope(self) -> Scope | None:
        return getattr(self.form, "scope", None)


def screen_text(
    context: ChatContext, turns: Sequence[Turn], result: Sequence[str] | None, subject: Sequence[str]
) -> str:
    """계획 모델에 주는 화면 요약. 가리킬 수 있는 지원자만 C번호와 이름으로 보여 주고 전형 전체 목록은 넣지 않는다."""
    stage = context.stages[context.stage_index]
    counts = ", ".join(
        f"{label} {sum(row.decision is decision for row in context.candidates)}"
        for decision, label in _DECISIONS.items()
    )
    lines = [
        f"[전형] {context.stage_name} ({STAGE_LABELS[context.stage_type]}, {STATUS_LABELS[stage.status]}) · "
        f"선택 변경 가능: {'예' if context.selectable else '아니요'} · 지원자 {len(context.candidates)}명 ({counts})",
        f"[멘션] {_people(context, context.mentions)}",
        f"[체크] {_people(context, context.checked)}",
        f"[선택] {_people(context, [row.application_id for row in context.candidates if row.selected])}",
        f"[이전 결과] {_ordered(context, result)}",
        f"[직전 대상] {_people(context, [UUID(value) for value in subject])}",
    ]
    history = _history(context, turns[-PLAN_TURNS:])
    if history:
        lines.append(data_block("history", history))
    lines.append(f"[현재 요청] {context.message}")
    return "\n".join(lines)


def check_plan(
    plan: RootPlan, context: ChatContext, result: Sequence[str] | None, subject: Sequence[str]
) -> str | None:
    """모델이 고쳐 쓸 수 있는 실수만 찾는다. 데이터 사실은 대상 범위를 펼칠 때 되묻는다."""
    scope = plan.scope
    if scope is not None and scope.picks:
        referable = _referable(context, result, subject)
        if any(pick.strip().upper() not in referable for pick in scope.picks):
            return PICKS_INVALID
    form = plan.form
    if isinstance(form, FindPlan) and not has_condition(form.query):
        return EMPTY_FIND
    if isinstance(form, EditPlan) and form.action in (EditAction.ADD, EditAction.REMOVE) and form.scope.empty:
        return NO_SCOPE
    if isinstance(form, QuestionsPlan) and form.scope.empty:
        return NO_SCOPE
    if isinstance(form, ConversationPlan | ClarifyPlan) and not form.message.strip():
        return NO_MESSAGE
    return None


def has_condition(query: SearchQuery) -> bool:
    return bool(
        query.concepts
        or query.min_score is not None
        or query.without_score
        or query.score_gap
        or query.area_scores
        or query.grades
        or query.min_career_years is not None
        or query.max_career_years is not None
        or query.use_talents
        or query.posting_criteria != "none"
    )


async def make_plan(
    llm: LlmClient, context: ChatContext, turns: Sequence[Turn], result: Sequence[str] | None, subject: Sequence[str]
) -> RootPlan:
    """일반 대화는 같은 호출 예산에서 검토하고, 통과하지 못하면 계획을 한 번 다시 쓰게 한다."""
    subjects = {str(row.application_id): row.name for row in context.candidates}

    async def validate(plan: RootPlan) -> str | None:
        problem = check_plan(plan, context, result, subject)
        if problem is not None:
            return problem
        if isinstance(plan.form, ConversationPlan) and not await review_conversation(
            llm, context.message, plan.form.message, turns, subjects=subjects
        ):
            return CONVERSATION_INVALID
        return None

    agent = llm.tool_agent(RootPlan, agent="root", system=PLAN_SYSTEM, tools=[], forms=PLAN_FORMS)
    return await agent.run(screen_text(context, turns, result, subject), validate=validate)


def _people(context: ChatContext, ids: Sequence[UUID]) -> str:
    known = {row.application_id: row for row in context.candidates}
    shown = [f"{candidate_ref(context, value)} {known[value].name}" for value in ids if value in known]
    return ", ".join(shown) or "없음"


def _ordered(context: ChatContext, result: Sequence[str] | None) -> str:
    if result is None:
        return "없음"
    known = {str(row.application_id): row for row in context.candidates}
    shown = [
        f"{number}. {candidate_ref(context, known[value].application_id)} {known[value].name}"
        for number, value in enumerate((value for value in result if value in known), start=1)
    ]
    return " ".join(shown) or "0명"


def _referable(context: ChatContext, result: Sequence[str] | None, subject: Sequence[str]) -> set[str]:
    ids = {*context.mentions, *context.checked, *(row.application_id for row in context.candidates if row.selected)}
    ids |= {UUID(value) for value in [*(result or []), *subject]}
    known = {row.application_id for row in context.candidates}
    return {candidate_ref(context, value) for value in ids if value in known}


def _history(context: ChatContext, turns: Sequence[Turn]) -> str:
    names = {
        str(row.application_id): f"{candidate_ref(context, row.application_id)} {row.name}"
        for row in context.candidates
    }
    return "\n".join(
        f"- 질문: {turn['message']} / 답: {turn['answer']} / 대상: "
        f"{', '.join(names.get(value, '현재 전형 밖') for value in turn['targets']) or '없음'} / 종류: {turn['intent']}"
        for turn in turns
    )
