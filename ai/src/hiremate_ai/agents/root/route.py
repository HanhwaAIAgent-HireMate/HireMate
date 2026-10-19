"""요청 분류. 모델을 한 번 불러 요청 종류와 경로별 값을 받고, 없는 자료 · 결정 요청 · 되묻기는 코드가 바로 답한다."""

import re
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.agents.root.targets import Targets
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, EditAction, Intent, SelectionMode
from hiremate_ai.contract import StageType
from hiremate_ai.llm.client import LlmClient

DECISION_REPLY = "합격 · 불합격은 지원자를 체크하고 화면 아래 버튼으로 결정해 주세요."
DEFAULT_CLARIFY = (
    '조건으로 지원자를 찾거나("금융 경험이 있는 지원자 찾아줘"), '
    '@로 지원자를 골라 물어보세요("@이름 강점과 확인할 점은?").'
)
NOT_UNDERSTOOD = "요청을 이해하지 못했어요. " + DEFAULT_CLARIFY
NO_ASSESSMENT = "아직 평가 결과가 없어요. 지원서에서 협업 경험이 약한 지원자를 찾아볼까요?"
NO_INTERVIEW = "아직 면접 답변 기록이 없어요. @로 지원자를 골라 면접에서 확인할 점을 물어볼 수 있어요."

_STAGE_LABELS = {StageType.DOCUMENT: "서류", StageType.ASSESSMENT: "평가", StageType.INTERVIEW: "면접"}

# 모델이 자료가 필요하다고 해도 문장에 그 자료를 가리키는 낱말이 있을 때만 "아직 없다"고 답한다.
# 잘못 막으면 정상 요청이 되묻기로 끝나고, 놓치면 경로가 자료가 없다고 정직하게 답한다
_ASSESSMENT_WORDS = re.compile(r"평가|과제|점수")
_POINTS = re.compile(r"\d+\s*점")
# "서류 점수", "서류 평가"는 서류 전형의 값이라 평가 결과가 아니다. 이 말이 있으면 "N점"도 서류 점수로 본다
_DOCUMENT_SCORE = re.compile(r"(?:서류|지원서|이력서|자기소개서|자소서)\s*(?:점수|평가)")
_INTERVIEW_WORDS = re.compile(r"답변|면접\s*기록")


class RootRoute(BaseModel):
    """분류 결과. 해당하지 않는 칸은 기본값으로 둔다."""

    kind: Literal["FIND", "ANSWER", "EDIT", "CLARIFY", "DECISION"] = Field(description="요청 종류")
    mode: SelectionMode | None = Field(default=None, description="FIND: 새로 찾기 REPLACE, 추가 ADD, 그중 NARROW")
    concepts: list[str] = Field(default=[], description="FIND: 찾는 직무 조건. 짧은 명사구")
    min_score: int | None = Field(default=None, description="FIND: 평가 점수 하한")
    without_score: bool = Field(default=False, description="FIND: 평가 결과가 아직 없는 사람")
    score_gap: bool = Field(default=False, description="FIND: 평가 결과와 지원서가 엇갈리는 사람")
    use_talents: bool = Field(default=False, description="FIND: 회사 인재상 · 중요하게 보는 요소로 찾기")
    edit: EditAction | None = Field(
        default=None, description="EDIT: 넣기 ADD, 빼기 REMOVE, 비우기 CLEAR, 되돌리기 RESTORE"
    )
    uses_checked: bool = Field(default=False, description="EDIT: 체크한 지원자를 가리킴")
    interview_questions: bool = Field(default=False, description="ANSWER: 면접 질문을 만들거나 고쳐 달라는 요청")
    all_candidates: bool = Field(default=False, description="ANSWER: 전형 지원자 모두를 가리킴")
    needs_assessment: bool = Field(
        default=False, description="요청에 평가 결과, 평가 점수, 과제, 'N점'이 직접 나오면 true"
    )
    needs_interview: bool = Field(
        default=False, description="요청에 '면접 답변'이나 '면접 기록'이 직접 나오면 true. 면접 질문 만들기는 false"
    )
    clarify: str | None = Field(default=None, description="CLARIFY: 되물을 말")


ROUTE_SYSTEM = """너는 채용 담당자가 전형 화면의 AI Chat에 쓴 요청을 분류한다.
지원자를 평가하거나 고르지 않고 요청의 종류만 정한다.

kind
- FIND: 조건으로 지원자를 찾아 선택 지원자 영역을 바꾸는 요청.
  "찾아줘", "보여줘", "골라줘", "~한 사람 있어?", "그중 ~만".
- ANSWER: 특정 지원자에 대한 의견, 비교, 설명, 요약, 인원이나 결정 현황 질문, 면접 질문 만들기.
  후보군을 바꾸지 않는다.
- EDIT: 이름, @멘션, 체크로 가리킨 지원자를 선택 지원자 영역에 넣거나 빼거나,
  영역을 비우거나 이전 선택으로 되돌리는 요청.
- DECISION: 합격, 불합격, 결과 확정, 안내 발송을 시키는 요청.
- CLARIFY: 무엇을 원하는지 알 수 없는 요청. clarify에 되물을 말을 쓴다.

FIND
- mode: 새로 찾으면 REPLACE. "추가", "더 찾아"면 ADD. "그중", "이 중에서", "여기서"면 NARROW.
- concepts: 찾는 직무 조건을 짧은 명사구로 적는다. 예: "금융 도메인 경험", "대용량 트래픽 처리".
  점수 조건은 넣지 않는다.
- min_score: "80점 이상"처럼 평가 점수의 하한.
- without_score: 평가 결과가 아직 없는 사람을 찾을 때.
- score_gap: 평가 결과와 지원서 내용이 엇갈리거나 차이가 큰 사람을 찾을 때.
- use_talents: "우리 회사가 중요하게 보는 요소", "인재상"처럼 회사 기준으로 찾을 때.
  이때 concepts에는 HR이 따로 말한 직무 조건만 넣고, "인재상", "중요하게 보는 요소" 같은 말은 넣지 않는다.

EDIT
- edit: 넣기 · 추가는 ADD, 빼기 · 제외는 REMOVE, 비우기는 CLEAR, 되돌리기는 RESTORE.
- uses_checked: "이 3명", "체크한 사람"처럼 체크한 지원자를 가리킬 때.
- 사람 이름이 있는 "정하늘도 추가해줘"는 EDIT ADD다. 조건만 있는 "결제 경험 있는 사람도 추가해줘"는 FIND ADD다.

ANSWER
- interview_questions: 면접 질문을 만들거나 고쳐 달라는 요청.
- all_candidates: "다들", "전원", "모두"처럼 전형 지원자 모두를 가리킬 때.

공통
- needs_assessment: 요청 문장에 평가 결과, 평가 점수, 과제, "N점"이 직접 나올 때만 true.
- needs_interview: 요청 문장에 "면접 답변"이나 "면접 기록"이 직접 나올 때만 true.
  면접 질문을 만들어 달라는 요청은 false다.
- 서류, 지원서, 이력서, 자기소개서, 인재상만 나오면 두 칸 모두 false다.
  "서류 점수", "서류 평가"는 평가 결과가 아니다.
- 해당하지 않는 칸은 기본값으로 둔다.

예
- "결제 시스템을 만들어 본 사람 보여줘" → FIND, REPLACE, concepts ["결제 시스템 개발 경험"]
- "그중에 리더 경험 있는 사람만" → FIND, NARROW, concepts ["리더 경험"]
- "과제 점수는 높은데 자기소개서와 다른 사람" → FIND, REPLACE, score_gap, needs_assessment
- "@김하늘 강점이 뭐야?" → ANSWER
- "@김하늘 빼줘" → EDIT, REMOVE
- "선택한 사람 다 지워줘" → EDIT, CLEAR
- "체크한 사람들 합격 처리해" → DECISION"""


def route_prompt(context: ChatContext, targets: Targets) -> str:
    """분류에 필요한 것만 넣는다. 지원자 문서는 넣지 않는다."""
    previous = ", ".join(_STAGE_LABELS[stage] for stage in context.previous_types) or "없음"
    names = ", ".join(row.name for row in targets.rows) or "없음"
    return (
        f"질문: {context.message}\n"
        f"현재 전형: {context.stage_name} ({_STAGE_LABELS[context.stage_type]})\n"
        f"끝난 전형: {previous}\n"
        f"대상 지원자: {names}\n"
        f"체크한 지원자: {len(context.checked)}명"
    )


async def classify(llm: LlmClient, context: ChatContext, targets: Targets) -> RootRoute:
    return await llm.structured(RootRoute, agent="root", system=ROUTE_SYSTEM, user=route_prompt(context, targets))


def required_data(route: RootRoute, message: str) -> set[StageType]:
    """요청에 필요한 전형 자료. 모델이 표시하고 문장에도 그 자료를 가리키는 낱말이 있는 것만 친다."""
    required = set()
    if route.needs_assessment and _mentions_assessment(message):
        required.add(StageType.ASSESSMENT)
    if route.needs_interview and _INTERVIEW_WORDS.search(message):
        required.add(StageType.INTERVIEW)
    return required


def _mentions_assessment(message: str) -> bool:
    rest = _DOCUMENT_SCORE.sub(" ", message)
    if _ASSESSMENT_WORDS.search(rest):
        return True
    return rest == message and bool(_POINTS.search(message))


def precheck(route: RootRoute, context: ChatContext) -> ChatPlan | None:
    """결정 요청, 아직 없는 전형 자료, 되묻기는 경로를 타지 않고 바로 답한다. 해당 없으면 None."""
    if route.kind == "DECISION":
        return ChatPlan.answer(Intent.CLARIFY, DECISION_REPLY)
    available = {context.stage_type, *context.previous_types}
    missing = required_data(route, context.message) - available
    if StageType.ASSESSMENT in missing:
        return ChatPlan.answer(Intent.CLARIFY, NO_ASSESSMENT)
    if StageType.INTERVIEW in missing:
        return ChatPlan.answer(Intent.CLARIFY, NO_INTERVIEW)
    if route.kind == "CLARIFY":
        return ChatPlan.answer(Intent.CLARIFY, route.clarify or DEFAULT_CLARIFY)
    return None
