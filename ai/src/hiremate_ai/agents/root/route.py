"""요청 분류. 모델을 한 번 불러 요청 종류와 경로별 값을 받고, 없는 자료 · 결정 요청 · 되묻기는 코드가 바로 답한다."""

import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.agents.root.stages import next_stage, reached
from hiremate_ai.agents.root.targets import Targets, checked
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Decision, EditAction, Intent, SelectionMode
from hiremate_ai.contract import StageType
from hiremate_ai.llm.client import LlmClient

DECISION_REPLY = "합격 · 불합격은 지원자를 체크하고 화면 아래 버튼으로 결정해 주세요."
DEFAULT_CLARIFY = (
    '조건으로 지원자를 찾거나("금융 경험이 있는 지원자 찾아줘"), '
    '@로 지원자를 골라 물어보세요("@이름 강점과 확인할 점은?").'
)
NOT_UNDERSTOOD = "요청을 이해하지 못했어요. " + DEFAULT_CLARIFY
# 아직 없는 전형 자료: 뒤 전형에서 생기는지, 이 채용에 그 전형이 없는지 나눠 말한다
NOT_YET_ASSESSMENT = (
    "평가는 아직 진행하지 않았어요. 결과는 {order}번째 전형 '{name}'에서 생겨요. "
    "지금은 지원서에서 협업 경험이 약한 지원자를 찾아볼까요?"
)
NO_ASSESSMENT = "이 채용에는 평가 전형이 없어요. 지원서에서 협업 경험이 약한 지원자를 찾아볼까요?"
NOT_YET_INTERVIEW = (
    "면접은 아직 진행하지 않았어요. 답변 기록은 {order}번째 전형 '{name}'에서 생겨요. "
    "지금은 @로 지원자를 골라 면접에서 확인할 점을 물어볼 수 있어요."
)
NO_INTERVIEW = "이 채용에는 면접 전형이 없어요. @로 지원자를 골라 지원서의 강점과 확인할 점을 물어볼 수 있어요."
NO_PREVIOUS = "앞 대화에서 가리킨 지원자를 찾지 못했어요. @로 골라 다시 말씀해 주세요."
COMPARE_NEEDS_TWO = "비교할 지원자를 두 명 이상 @로 고르거나 체크해 주세요."
# backend ChatService와 같은 문구. 확정한 전형에서는 선택 지원자를 바꾸지 않는다
LOCKED = "결과를 확정한 전형이라 선택 지원자를 바꿀 수 없어요. 분석이나 요약은 계속 물어볼 수 있어요."
# 분류 프롬프트에 넣는 최근 턴 수와 체크한 지원자 이름 수
RECENT_TURNS = 3
CHECKED_NAMES = 5

_STAGE_LABELS = {StageType.DOCUMENT: "서류", StageType.ASSESSMENT: "평가", StageType.INTERVIEW: "면접"}

# 모델이 자료가 필요하다고 해도 문장에 그 자료를 가리키는 낱말이 있을 때만 "아직 없다"고 답한다.
# 잘못 막으면 정상 요청이 되묻기로 끝나고, 놓치면 경로가 자료가 없다고 정직하게 답한다
_ASSESSMENT_WORDS = re.compile(r"평가|과제|점수")
_POINTS = re.compile(r"\d+\s*점")
# "서류 점수", "서류 평가"는 서류 전형의 값이라 평가 결과가 아니다. 이 말이 있으면 "N점"도 서류 점수로 본다
_DOCUMENT_SCORE = re.compile(r"(?:서류|지원서|이력서|자기소개서|자소서)\s*(?:점수|평가)")
_INTERVIEW_WORDS = re.compile(r"답변|면접\s*기록")
# 찾기 결과를 가리키는 말. "그중", "그 중에서"만. "그 중요한", "그 중간"은 아니다
_RESULT_WORDS = re.compile(r"찾은|고른|그\s*중(?:에서는|에서|에는|에|엔|의)?(?![가-힣])")
# 체크한 지원자가 있으면 앞 대화는 순서를 말하거나 앞 대화를 가리키는 말이 있을 때만 쓴다
_PREVIOUS_WORDS = re.compile(
    rf"방금|아까|앞에서|앞서|위에서|이전|지난번|만든|그\s*(?:사람|지원자|분|둘|셋)|{_RESULT_WORDS.pattern}"
)
# 이유를 묻는 말과 질문을 만들거나 고쳐 달라는 말. 이유만 물으면 면접 질문 만들기가 아니다
_ASKS_REASON = re.compile(r"왜|이유")
_MAKE_REQUEST = re.compile(r"만들어|추가|고쳐|바꿔|다시|생성|뽑아|짜\s*줘")
# 순서를 말하는 말. 실제 모델은 "몇 명이야?", "두 지원자를 비교해봐"에도 ordinal을 적는다
_ORDINAL_WORDS = re.compile(r"(?:첫|두|둘|세|셋|네|넷|다섯|여섯|일곱|여덟|아홉|열|\d+)\s*(?:번째|째)|마지막")
# 공고 항목을 가리키는 말. 이 말이 있어야 공고의 자격 요건 · 우대 사항으로 찾는다
_POSTING_WORDS = re.compile(r"공고|우대|자격\s*요건|요건")
# 지원자끼리 견주는 말. 모델은 "@김하늘 공고 요건과 비교해줘"처럼 한 사람을 기준과 견주는 요청에도 compare를 표시한다
_BETWEEN_APPLICANTS = re.compile(
    r"둘|두\s*(?:사람|명|분)|세\s*(?:사람|명|분)|\d+\s*명|사람들|지원자들|이들|끼리|서로|누가\s*더|어느\s*쪽|중\s*누가"
)
# 비교해 달라는 말. 여러 지원자를 가리키는 말과 같이 있으면 모델이 compare를 빠뜨려도 지원자끼리 비교다
_COMPARE_WORDS = re.compile(r"비교|견주|견줘")
# 전형 요약(get_stage_summary)에 있는 값의 순위를 묻는 말. 찾기 동사가 있으면 HR이 찾아 달라고 한 것이다
_SUPERLATIVE = re.compile(r"가장|제일|최고|최다")
_SUMMARY_FIELD = re.compile(r"경력|연차|년차|평가\s*점수|과제\s*점수")
_FIND_REQUEST = re.compile(r"찾|보여|골라|고르|뽑|추려|선택|남겨|추가|좁혀")
# 이미 정한 결정을 가리키는 말. 이 말이 있어야 그 결정의 지원자 안에서 찾는다 ("합격 가능성"은 아니다)
_DECIDED_WORDS = {
    Decision.PASS: re.compile(r"(?<!불)합격\s*(?:처리\s*)?(?:한|된|시킨|했던|자|인)"),
    Decision.FAIL: re.compile(r"(?:불합격|탈락)\s*(?:처리\s*)?(?:한|된|시킨|했던|자|인)"),
    Decision.PENDING: re.compile(r"미결정|결정\s*(?:안|하지\s*않|되지\s*않)"),
}


class RootRoute(BaseModel):
    """분류 결과. 해당하지 않는 칸은 기본값으로 둔다."""

    kind: Literal["FIND", "ANSWER", "EDIT", "CLARIFY", "DECISION"] = Field(description="요청 종류")
    mode: SelectionMode | None = Field(default=None, description="FIND: 새로 찾기 REPLACE, 추가 ADD, 그중 NARROW")
    concepts: list[str] = Field(default=[], description="FIND: 찾는 직무 조건. 짧은 명사구")
    min_score: int | None = Field(default=None, description="FIND: 평가 점수 하한")
    without_score: bool = Field(default=False, description="FIND: 평가 결과가 아직 없는 사람")
    score_gap: bool = Field(default=False, description="FIND: 평가 결과와 지원서가 엇갈리는 사람")
    use_talents: bool = Field(default=False, description="FIND: 회사 인재상 · 중요하게 보는 요소로 찾기")
    posting_criteria: Literal["none", "qualifications", "preferred", "both"] = Field(
        default="none", description="FIND: 공고의 자격 요건(qualifications) · 우대 사항(preferred) · 둘 다(both)로 찾기"
    )
    criteria_match: Literal["any", "most", "all"] = Field(
        default="any", description="FIND 공고 기준: 하나 이상 any, 가장 많이 most, 모두 all"
    )
    decision: Literal["none", "PASS", "FAIL", "PENDING"] = Field(
        default="none",
        description="FIND: 합격한 사람 중이면 PASS, 불합격한 사람 중이면 FAIL, 아직 결정하지 않은 사람 중이면 PENDING",
    )
    edit: EditAction | None = Field(
        default=None, description="EDIT: 넣기 ADD, 빼기 REMOVE, 비우기 CLEAR, 되돌리기 RESTORE"
    )
    uses_checked: bool = Field(default=False, description="EDIT: 체크한 지원자를 가리킴")
    interview_questions: bool = Field(default=False, description="ANSWER: 면접 질문을 만들거나 고쳐 달라는 요청")
    all_candidates: bool = Field(default=False, description="ANSWER: 전형 지원자 모두를 가리킴")
    compare: bool = Field(default=False, description="ANSWER: 지원자끼리 비교해 달라는 요청")
    needs_assessment: bool = Field(
        default=False, description="요청에 평가 결과, 평가 점수, 과제, 'N점'이 직접 나오면 true"
    )
    needs_interview: bool = Field(
        default=False, description="요청에 '면접 답변'이나 '면접 기록'이 직접 나오면 true. 면접 질문 만들기는 false"
    )
    clarify: str | None = Field(default=None, description="CLARIFY: 되물을 말")
    previous_ref: Literal["none", "result", "subject"] = Field(
        default="none", description="앞 대화를 가리킴: result는 직전 찾기 결과, subject는 직전에 다룬 지원자"
    )
    ordinal: int | None = Field(default=None, description="'두 번째'처럼 순서를 말하면 그 번호")


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
- posting_criteria: 공고의 항목을 기준으로 찾을 때. "우대 사항"은 preferred, "자격 요건" · "필수 요건"은 qualifications,
  "공고에 맞는 사람"처럼 공고 전체면 both. 이때 concepts에는 HR이 따로 말한 직무 조건만 넣고,
  "우대 사항", "자격 요건", "적합성", "충족" 같은 말은 넣지 않는다.
- criteria_match: "다", "모두", "전부" 충족이면 all. "아주", "가장", "잘 맞는", "많이"면 most. 그 밖은 any.

EDIT
- edit: 넣기 · 추가는 ADD, 빼기 · 제외는 REMOVE, 비우기는 CLEAR, 되돌리기는 RESTORE.
- uses_checked: "이 3명", "체크한 사람"처럼 체크한 지원자를 가리킬 때.
- 사람 이름이 있는 "정하늘도 추가해줘"는 EDIT ADD다. 조건만 있는 "결제 경험 있는 사람도 추가해줘"는 FIND ADD다.

ANSWER
- interview_questions: 면접 질문을 만들거나 고쳐 달라는 요청.
- all_candidates: "다들", "전원", "모두"처럼 전형 지원자 모두를 가리킬 때.
- compare: 두 명 이상의 지원자끼리 비교하는 요청. 한 지원자를 공고나 기준과 견주는 것은 false.

앞 대화
- 이름이나 @ 없이 앞 대화의 지원자를 가리키면 previous_ref를 쓴다.
  "방금 찾은 사람들", "그중 두 번째 사람"(설명 · 편집 요청)은 result, "아까 그 사람", "그 지원자"는 subject.
  "두 번째", "첫 번째"처럼 순서가 있으면 ordinal에 번호를 적는다.
- "그중 ~만", "그중에 ~ 있는 사람"처럼 조건으로 좁히는 찾기는 previous_ref 없이 FIND NARROW다.
- 체크한 지원자가 있고 "이 둘", "둘", "이 사람들"처럼 가리키면 체크한 지원자다. previous_ref 없이 둔다.

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
- "우대 사항을 다 충족하는 사람 찾아줘" → FIND, REPLACE, posting_criteria preferred, criteria_match all, concepts []
- "공고 우대 사항에 아주 적합한 사람 찾아줘" → FIND, REPLACE, posting_criteria preferred, criteria_match most
- "과제 점수는 높은데 자기소개서와 다른 사람" → FIND, REPLACE, score_gap, needs_assessment
- "@김하늘 강점이 뭐야?" → ANSWER
- "@김하늘 빼줘" → EDIT, REMOVE
- "선택한 사람 다 지워줘" → EDIT, CLEAR
- "체크한 사람들 합격 처리해" → DECISION"""


def route_prompt(context: ChatContext, targets: Targets, turns: Sequence[Turn] = ()) -> str:
    """분류에 필요한 것만 넣는다. 지원자 문서는 넣지 않는다. 앞 대화는 질문과 다룬 지원자 이름만."""
    previous = ", ".join(_STAGE_LABELS[stage] for stage in context.previous_types) or "없음"
    names = ", ".join(row.name for row in targets.rows) or "없음"
    prompt = (
        f"질문: {context.message}\n"
        f"현재 전형: {context.stage_name} ({_STAGE_LABELS[context.stage_type]})\n"
        f"끝난 전형: {previous}\n"
        f"대상 지원자: {names}\n"
        f"체크한 지원자: {_checked_names(context)}"
    )
    if turns:
        by_id = {str(row.application_id): row.name for row in context.candidates}
        lines = []
        for number, turn in enumerate(turns[-RECENT_TURNS:], start=1):
            people = ", ".join(by_id[target] for target in turn["targets"] if target in by_id) or "없음"
            label = "찾기 결과" if turn["kind"] == "FIND" else "대상"
            lines.append(f'{number}. "{turn["message"]}" → {label}: {people}')
        prompt += "\n앞 대화 (오래된 것부터):\n" + "\n".join(lines)
    return prompt


def _checked_names(context: ChatContext) -> str:
    ids = set(context.checked)
    names = [row.name for row in context.candidates if row.application_id in ids]
    if len(names) > CHECKED_NAMES:
        return ", ".join(names[:CHECKED_NAMES]) + f" 외 {len(names) - CHECKED_NAMES}명"
    return ", ".join(names) or "없음"


def refers_previous(route: RootRoute, context: ChatContext) -> bool:
    """앞 대화의 지원자를 대상으로 쓸지. 체크한 지원자가 있으면 순서나 앞 대화를 가리키는 말이 있어야 한다."""
    if route.previous_ref == "none":
        return False
    return not checked(context) or says_previous(route, context.message)


def says_previous(route: RootRoute, message: str) -> bool:
    """문장이 앞 대화를 가리키는가: 순서를 말하거나 앞 대화를 가리키는 말이 있다.

    실제 모델은 이름이 없는 질문이면 "미결정이 몇 명 남았어?"에도 앞 대화를 표시한다.
    """
    return route.ordinal is not None or bool(_PREVIOUS_WORDS.search(message))


def posting_section(route: RootRoute, message: str) -> Literal["qualifications", "preferred", "both"] | None:
    """공고 항목으로 찾는 찾기의 기준. 모델이 표시하고 문장에도 공고 항목을 가리키는 말이 있어야 한다."""
    if route.kind != "FIND" or route.posting_criteria == "none" or not _POSTING_WORDS.search(message):
        return None
    return route.posting_criteria


def asks_comparison(route: RootRoute, message: str) -> bool:
    """지원자끼리 비교하는 요청. 모델이 표시하고 문장에도 여러 지원자를 견주는 말이 있어야 한다."""
    return route.compare and bool(_BETWEEN_APPLICANTS.search(message))


def asks_stage_ranking(message: str) -> bool:
    """전형 요약에 있는 값(경력, 평가 점수)이 가장 높은 사람을 묻는 질문인가. "경력이 가장 많은 사람은?" 같은 것."""
    return bool(_SUPERLATIVE.search(message) and _SUMMARY_FIELD.search(message) and not _FIND_REQUEST.search(message))


def decided_filter(route: RootRoute, message: str) -> Decision | None:
    """그 결정의 지원자 안에서 찾는 찾기. 모델이 표시하고 문장에도 그 결정을 가리키는 말이 있어야 한다."""
    if route.kind != "FIND" or route.decision == "none":
        return None
    decision = Decision(route.decision)
    return decision if _DECIDED_WORDS[decision].search(message) else None


async def classify(llm: LlmClient, context: ChatContext, targets: Targets, turns: Sequence[Turn] = ()) -> RootRoute:
    decided = await llm.structured(
        RootRoute, agent="root", system=ROUTE_SYSTEM, user=route_prompt(context, targets, turns)
    )
    return _settled(decided, context.message)


def _settled(route: RootRoute, message: str) -> RootRoute:
    """모델이 표시했지만 문장에 근거가 없는 값을 고친다.

    순서 말이 없는 ordinal은 지운다. 남기면 첫 턴의 인원 질문도 앞 대화를 가리키는 것으로 보고 되묻는다.
    "그중", "찾은"이 있으면 직전에 다룬 지원자가 아니라 찾기 결과다. 아무도 못 찾은 새 찾기 뒤의 "그중 첫 번째"가
    그 전 찾기 결과를 가리키지 않게 한다.
    지원자끼리 비교하는 요청을 되묻기로 표시하면 분석으로 돌린다. 대상이 모자라면 정해 둔 문구로 되묻고,
    체크한 지원자가 있으면 그 사람들을 비교한다. 비교하는 말과 여러 지원자를 가리키는 말이 있으면 모델 표시와 상관없이
    지원자끼리 비교로 본다. 실제 모델은 대상 없는 "둘 비교해줘"에 compare 없이 자기 되물음을 쓰기도 한다.
    전형 요약에 있는 값의 순위를 묻는 질문("경력이 가장 많은 사람은?")을 찾기 조건 없이 찾기로 표시하면 분석으로 돌린다.
    찾기는 조건으로 거르는 경로라 순위를 매기지 못하고 아무도 못 찾았다고 답한다.
    만든 질문의 이유만 묻는 문장("방금 만든 질문은 왜 만든 거야?")은 면접 질문 만들기가 아니라 분석이다.
    표시를 남기면 질문을 다시 만든다.
    """
    update: dict[str, object] = {}
    if route.interview_questions and _ASKS_REASON.search(message) and not _MAKE_REQUEST.search(message):
        update["interview_questions"] = False
    if route.ordinal is not None and not _ORDINAL_WORDS.search(message):
        update["ordinal"] = None
    if route.previous_ref == "subject" and _RESULT_WORDS.search(message):
        update["previous_ref"] = "result"
    if route.kind in ("CLARIFY", "ANSWER") and _COMPARE_WORDS.search(message) and _BETWEEN_APPLICANTS.search(message):
        update |= {"kind": "ANSWER", "compare": True}
    elif route.kind == "CLARIFY" and asks_comparison(route, message):
        update["kind"] = "ANSWER"
    if route.kind == "FIND" and asks_stage_ranking(message) and _plain_find(route):
        update["kind"] = "ANSWER"
    return route.model_copy(update=update) if update else route


def _plain_find(route: RootRoute) -> bool:
    """공고 · 인재상 · 결정 · 점수 같은 찾기 기준 없이 낱말 조건만 있는 찾기."""
    return (
        route.posting_criteria == "none"
        and not route.use_talents
        and route.decision == "none"
        and route.min_score is None
        and not route.without_score
        and not route.score_gap
    )


def required_data(route: RootRoute, message: str) -> set[StageType]:
    """요청에 필요한 전형 자료. 모델이 표시하고 문장에도 그 자료를 가리키는 낱말이 있는 것만 친다."""
    required = set()
    if route.needs_assessment and _mentions_assessment(message):
        required.add(StageType.ASSESSMENT)
    if route.needs_interview and _INTERVIEW_WORDS.search(message):
        required.add(StageType.INTERVIEW)
    return required


def names_document_score(message: str) -> bool:
    """점수 조건이 평가 결과가 아니라 서류 점수인가. 모델은 "서류 점수 80점"도 min_score로 적는다."""
    return bool(_DOCUMENT_SCORE.search(message))


def _mentions_assessment(message: str) -> bool:
    rest = _DOCUMENT_SCORE.sub(" ", message)
    if _ASSESSMENT_WORDS.search(rest):
        return True
    return rest == message and bool(_POINTS.search(message))


def unavailable(context: ChatContext, kind: StageType) -> str:
    """아직 진행하지 않았거나 이 채용에 없는 전형의 자료를 물었을 때의 답."""
    later = next_stage(context, kind)
    if later is None:
        return NO_ASSESSMENT if kind is StageType.ASSESSMENT else NO_INTERVIEW
    order, stage = later
    template = NOT_YET_ASSESSMENT if kind is StageType.ASSESSMENT else NOT_YET_INTERVIEW
    return template.format(order=order, name=stage.name)


def precheck(route: RootRoute, context: ChatContext) -> ChatPlan | None:
    """결정 요청, 아직 없는 전형 자료, 되묻기는 경로를 타지 않고 바로 답한다. 해당 없으면 None."""
    if route.kind == "DECISION":
        return ChatPlan.answer(Intent.CLARIFY, DECISION_REPLY)
    # 합격 · 불합격한 지원자 안에서 찾기는 선택 지원자를 바꾸지 않아 결과를 확정한 전형에서도 답한다
    among_decided = decided_filter(route, context.message) in (Decision.PASS, Decision.FAIL)
    if route.kind in ("FIND", "EDIT") and not context.selectable and not among_decided:
        return ChatPlan.answer(Intent.CLARIFY, LOCKED)
    required = required_data(route, context.message)
    for kind in (StageType.ASSESSMENT, StageType.INTERVIEW):
        if kind in required and not reached(context, kind):
            return ChatPlan.answer(Intent.CLARIFY, unavailable(context, kind))
    if route.kind == "CLARIFY":
        return ChatPlan.answer(Intent.CLARIFY, route.clarify or DEFAULT_CLARIFY)
    return None
