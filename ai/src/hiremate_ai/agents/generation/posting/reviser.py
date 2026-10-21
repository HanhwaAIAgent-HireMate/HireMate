"""Posting Agent. HR의 수정 요청을 공고 수정안으로 바꾼다. 수정안만 만들고 적용 · 게시하지 않는다 (FR-02~04).

작은 모델은 한 번에 여러 칸을 채우게 하면 바꾸지 않을 칸까지 채우고 오래 걸린다. 그래서 짧게 나눠 묻는다.

1. 요청이 바꾸라는 대상을 고른다 (본문 칸, 전형 절차, 필수 제출 서류, NCS 근거로 자격 요건 · 우대 사항 쓰기).
2. 고른 대상마다 그 대상만 쓰게 한다. 게시 뒤 바꿀 수 없는 대상은 묻지 않는다.

모든 호출의 system과 앞부분(지금 공고, HR 요청)이 같아, 모델은 앞부분을 다시 읽지 않는다. 할 일은 끝에 붙인다.
지금 공고에 합치고 바뀐 칸을 고르는 일은 코드가 한다. 모델이 바뀌었다고 말하는 칸을 믿지 않고 원래 공고와 비교한다.
NCS 근거는 고른 능력단위의 정의를 보여 주고 쓰게 하며, 근거 코드는 실제로 있는 능력단위인지 확인한다 (규칙 7).
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from hiremate_ai.agents.generation.posting.checks import blocked_terms, problems
from hiremate_ai.agents.generation.posting.types import (
    PostingDraftContext,
    PostingSuggestion,
    RecruitmentStatus,
    RevisionResult,
    StageDraft,
)
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.contract import DocumentType, PostingContent, StageType
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.tools.ncs import NcsUnit, ncs_data, subdivisions, unit_by_code, units_of

AGENT = "posting"
"""호출 로그와 backend 연동 경로(/agents/posting/...)에 쓰는 Agent 키."""

FIELD_LABELS = {
    "title": "채용명",
    "job_category": "직무",
    "employment_type": "고용 형태",
    "career": "경력",
    "location": "근무지",
    "intro": "회사 소개",
    "duties": "주요 업무",
    "qualifications": "자격 요건",
    "preferred": "우대 사항",
    "benefits": "복지",
}
"""공고 본문 칸 → 화면 이름. 순서는 공고 편집 화면 순서다."""

STAGE_TYPE_LABELS = {StageType.DOCUMENT: "서류", StageType.ASSESSMENT: "평가", StageType.INTERVIEW: "면접"}
STATUS_LABELS = {
    RecruitmentStatus.DRAFT: "작성 중",
    RecruitmentStatus.PUBLISHED: "공고 게시 중",
    RecruitmentStatus.IN_PROGRESS: "전형 진행 중",
    RecruitmentStatus.CLOSED: "종료",
}

NOTHING_CHANGED_REPLY = "요청에서 바꿀 부분을 찾지 못했어요. 어느 칸을 어떻게 바꿀지 알려 주세요."
LOCKED_REPLY = "공고를 게시한 뒤에는 전형 절차와 필수 제출 서류를 바꿀 수 없어요."
BLOCKED_REPLY = (
    "나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 자격 요건이나 우대 사항에 넣을 수 없어요. "
    "직무와 관련된 경험이나 역량으로 다시 말씀해 주세요."
)
CHECK_FAILED_REPLY = "요청대로 고친 수정안이 공고 작성 규칙을 지키지 못했어요. 요청을 조금 바꿔 다시 말씀해 주세요."
RETRY_HINT = "처음 요청에 종류를 붙여 다시 말씀해 주세요. 예: 'PT 발표 전형을 평가로 넣어 줘'"
ANSWER_ONLY_REPLY = f"앞의 대화는 기억하지 못해요. {RETRY_HINT}"

ATTEMPTS = 2
"""처음 한 번과, 검사에 걸렸을 때 이유를 붙여 다시 쓰는 한 번."""

MAX_NCS_UNITS = 8
"""정의와 수행준거를 보여 줄 능력단위 수."""

NCS_DETAIL_CHARS = 3000
"""두 번째 호출에 넣는 능력단위 정의와 수행준거의 글자 수 한도. 능력단위 하나에 평균 700자라 다 넣으면
노트북 모델이 한 번에 읽는 양(약 4천 토큰)을 넘는다. 지식 · 기술은 일반적인 말이라 공고 문장에는 넣지 않는다."""

ContentLabel = Literal[
    "채용명", "직무", "고용 형태", "경력", "근무지", "회사 소개", "주요 업무", "자격 요건", "우대 사항", "복지"
]
"""모델이 바꿀 칸을 고르는 이름. 영어 필드 이름을 주면 작은 모델이 '근무지'를 job_category에 넣는 식으로 헷갈린다."""
LABEL_FIELDS = {label: name for name, label in FIELD_LABELS.items()}
TEXT_FIELDS = ("title", "job_category", "employment_type", "career", "location", "intro")
NCS_FIELDS: tuple[tuple[str, ContentLabel], ...] = (("qualifications", "자격 요건"), ("preferred", "우대 사항"))

EXTRA_WORDS = {DocumentType.PORTFOLIO: ("포트폴리오",), DocumentType.CERTIFICATE: ("자격증",)}
"""필수 서류는 요청에 그 서류가 나올 때만 넣고 뺀다. 작은 모델이 요청하지 않은 서류를 더하곤 한다."""

# 이름만으로 전형 종류를 알 수 없는 낱말과, 종류를 알 수 있는 낱말. 새 전형 이름이 앞에만 걸리고
# 요청에도 종류가 없으면 모델이 종류를 골랐어도 되묻는다 (FR-04). 모델은 지시를 어기고 추측하곤 한다.
_AMBIGUOUS_STAGE = re.compile(r"PT|프레젠테이션|발표|워크숍|워크샵|토론|합숙|캠프|인턴", re.IGNORECASE)
_CLEAR_STAGE = re.compile(r"서류|면접|테스트|시험|평가|검사|과제|코딩")
_TYPE_WORD = re.compile(r"서류|평가|면접")

# 차별 조건을 지원자를 거르는 데 쓰라는 요청. 차별 조건 낱말과 함께 나오면 모델을 부르지 않고 거절한다.
# 낱말만으로 막으면 "근무 지역", "자녀 학자금"처럼 공고에 쓰는 말까지 막혀서 함께 나올 때만 본다
_JUDGING = re.compile(r"우대|자격|요건|선호|조건|제한|이하|이상만|만\s*(?:받|뽑)")

# 공고 AI는 앞 대화를 받지 못한다(backend가 이번 요청만 보낸다). 되물음에 종류 낱말 하나로 답하면
# 무엇의 종류인지 알 수 없어, 모델을 부르지 않고 처음 요청에 붙여 다시 말해 달라고 한다
_ANSWER_ONLY = re.compile(r"(?:서류|평가|면접)(?:전형)?(?:이요|요|입니다|이에요|예요)?[.!]?")
_NCS_WORDS = re.compile(r"자격|우대|요건|NCS", re.IGNORECASE)

# 모델이 숫자와 단위 사이에 넣는 공백 (예: "1 차 면접", "20 대")
_NUMBER_SPACE = re.compile(r"(\d)\s+(차|대|년|개월|월|일|시간|시|분|명|회|개|단계|주)")

Target = Literal["CONTENT", "STAGES", "REQUIRED_EXTRAS", "NCS_REQUIREMENTS"]
PROCESS_TARGETS: frozenset[Target] = frozenset({"STAGES", "REQUIRED_EXTRAS"})
"""게시한 뒤에는 바꿀 수 없는 대상."""

# 모델에게서 받는 답. 모든 필드를 필수(값이 없으면 null)로 둔다. 선택 필드로 두면 작은 모델이 필드를 통째로 빼먹는다.


class Route(BaseModel):
    """첫 호출: 요청이 바꾸라는 대상."""

    targets: list[Target] = Field(description="요청이 바꾸라는 대상. 알 수 없으면 빈 목록")
    question: str | None = Field(description="무엇을 바꾸라는지 알 수 없을 때 HR에게 되묻는 한 문장. 아니면 null")


class FieldChange(BaseModel):
    """바꿀 본문 칸 하나. 글 칸은 text, 목록 칸은 items에 쓰고 다른 하나는 null이다."""

    field: ContentLabel = Field(description="바꿀 본문 칸")
    text: str | None = Field(description="글 칸(채용명, 직무, 고용 형태, 경력, 근무지, 회사 소개)의 새 내용")
    items: list[str] | None = Field(description="목록 칸(주요 업무, 자격 요건, 우대 사항, 복지)의 바꾼 뒤 목록 전체")


class ContentChanges(BaseModel):
    changes: list[FieldChange] = Field(description="요청이 바꾸라는 본문 칸만")


class StageEdit(BaseModel):
    """전형 하나. 종류를 알 수 없으면 type을 null로 두고 되묻는다."""

    name: str = Field(description="전형 이름. HR이 말한 이름 그대로")
    type: StageType | None = Field(description="DOCUMENT(서류), ASSESSMENT(평가), INTERVIEW(면접). 알 수 없으면 null")


class StagePlan(BaseModel):
    stages: list[StageEdit] = Field(description="바꾼 뒤의 전형 전체를 순서대로")


class ExtrasPlan(BaseModel):
    required_extras: list[Literal["PORTFOLIO", "CERTIFICATE"]] = Field(
        description="이력서 · 자기소개서 밖에 필수로 받을 서류 전체"
    )


class NcsPick(BaseModel):
    ncs_codes: list[str] = Field(description="근거로 쓸 NCS 능력단위 코드 (최대 8개)")


class SourcedItem(BaseModel):
    """근거가 붙은 목록 항목. sources는 근거로 쓴 NCS 능력단위 코드이고, 근거가 없는 항목은 비운다."""

    text: str = Field(description="항목 한 줄")
    sources: list[str] = Field(description="근거로 쓴 NCS 능력단위 코드")


class NcsDraft(BaseModel):
    """NCS 정의를 보고 쓴 목록. 바꾼 뒤의 목록 전체다."""

    qualifications: list[SourcedItem] = Field(description="자격 요건 목록 전체")
    preferred: list[SourcedItem] = Field(description="우대 사항 목록 전체")


SYSTEM = """너는 기업 인사팀의 채용 공고 편집을 돕는 Posting Agent다. HR의 요청대로 공고 수정안을 쓴다.
요청은 여러 번에 나눠 처리한다. 맨 끝의 "지금 할 일"만 하고, 그 형식의 칸만 쓴다.

바꿀 수 있는 대상:
- CONTENT: 공고 본문 칸(채용명, 직무, 고용 형태, 경력, 근무지, 회사 소개, 주요 업무, 자격 요건, 우대 사항, 복지)을
  고치거나 항목을 더하고 빼기.
- STAGES: 전형 절차. 전형 이름은 HR이 말한 그대로 두고 종류를 정한다. 종류는 DOCUMENT(서류: 지원서와 제출 서류 검토),
  ASSESSMENT(평가: 코딩테스트, 인적성, 직무역량 평가, 과제), INTERVIEW(면접: 실무면접, 임원면접)다.
- REQUIRED_EXTRAS: 필수 제출 서류. 이력서와 자기소개서는 항상 받는다. 더 받을 수 있는 것은 PORTFOLIO(포트폴리오),
  CERTIFICATE(자격증)뿐이다.
- NCS_REQUIREMENTS: 자격 요건이나 우대 사항을 새로 쓰거나 전체를 다시 쓰기. NCS 능력단위를 근거로 쓴다.
  항목 하나를 더하거나 고치는 정도면 CONTENT다.

규칙:
1. 요청하지 않은 대상과 칸은 바꾸지 않는다.
2. 회사가 알려 주지 않은 사실(연봉, 복지, 근무 조건, 회사 정보)은 지어내지 않는다.
3. 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 자격 요건이나 우대 사항에 넣지 않는다.
4. 회사의 공고 작성 스타일이 있으면 따른다. 한국어로 쓰고, 목록 항목은 앞에 기호 없이 한 줄로 짧게 쓴다."""

ROUTE_STEP = (
    "지금 할 일: 요청이 바꾸라는 대상을 targets에 고른다. 요청하지 않은 대상은 넣지 않는다. "
    "무엇을 바꾸라는지 알 수 없으면 targets를 비우고 question에 되묻는 한 문장을 쓴다."
)
CONTENT_STEP = (
    "지금 할 일: 본문 칸 중 요청이 바꾸라는 칸만 changes에 쓴다. field에는 칸 이름(예: 근무지, 우대 사항)을 쓴다. "
    "글 칸(채용명, 직무, 고용 형태, 경력, 근무지, 회사 소개)은 text에 새 내용을, 목록 칸(주요 업무, 자격 요건, "
    "우대 사항, 복지)은 items에 그대로 둘 항목까지 넣은 바꾼 뒤 목록 전체를 쓰고, 다른 하나는 null로 둔다."
)
STAGES_STEP = (
    "지금 할 일: 바꾼 뒤의 전형 절차 전체를 순서대로 stages에 쓴다. 이름만으로 종류를 알 수 없는 전형"
    "(예: PT, 발표, 워크숍)은 추측하지 말고 type을 null로 둔다."
)
EXTRAS_STEP = "지금 할 일: 요청대로 바꾼 뒤, 이력서 · 자기소개서 밖에 필수로 받을 서류 전체를 required_extras에 쓴다."

NCS_SYSTEM = """너는 채용 공고의 자격 요건과 우대 사항을 NCS(국가직무능력표준) 능력단위를 근거로 쓰는 Posting Agent다.

규칙:
1. 주어진 능력단위의 정의와 수행준거에 있는 능력을 지원자가 읽기 쉬운 공고 문장으로 바꿔 쓴다.
   수행준거 문장을 그대로 옮기지 않는다. 정의와 수행준거에 없는 기술 이름(언어, 프레임워크, 자격증)은
   지금 공고나 HR 요청에 있을 때만 쓴다.
2. 항목마다 근거로 쓴 능력단위 코드를 sources에 적는다. 근거가 없는 항목은 sources를 비운다.
3. 자격 요건은 지원에 꼭 필요한 조건이고, 우대 사항은 있으면 좋은 조건이다. 수준이 높은 능력단위는 우대 사항에 어울린다.
4. 지금 공고의 항목 중 요청과 관계없이 그대로 둘 항목도 함께 쓴다.
5. 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 넣지 않는다. 회사가 알려 주지 않은 사실은 지어내지 않는다.
6. 항목은 "~ 경험", "~ 능력"처럼 한 줄로 짧게 쓰고, 목록마다 3~6개로 쓴다. 한국어로 쓴다."""


@dataclass(frozen=True)
class _Edit:
    """고른 대상마다 받은 답을 모은 것. 고르지 않은 대상은 None이다."""

    changes: list[FieldChange] = field(default_factory=list)
    stages: list[StageEdit] | None = None
    required_extras: list[str] | None = None
    cited: list[NcsUnit] = field(default_factory=list)


@dataclass(frozen=True)
class _Draft:
    """답을 지금 공고에 합친 결과. changed는 바뀐 본문 칸, stages · required_extras는 바뀌었을 때만 있다."""

    content: PostingContent
    changed: list[str]
    stages: list[StageDraft] | None
    required_extras: list[DocumentType] | None
    unknown_stages: list[str]


async def revise_posting(
    llm: LlmClient, posting: PostingDraftContext, writing_style: str, request: str
) -> RevisionResult:
    """HR의 요청대로 공고 수정안을 만든다. 되묻거나 처리할 수 없으면 수정안 없이 답만 한다.

    수정안이 검사에 걸리면 이유를 붙여 한 번 더 쓰게 한다. 차별 조건은 다시 쓰게 하지 않고 바로 거절한다.
    """
    if blocked_attribute(request) and _JUDGING.search(request):
        return RevisionResult(reply=BLOCKED_REPLY, suggestion=None)
    if _ANSWER_ONLY.fullmatch(_compact(request)):
        return RevisionResult(reply=ANSWER_ONLY_REPLY, suggestion=None)
    context = _context(posting, writing_style, request)
    route = await _ask(llm, Route, context, ROUTE_STEP)
    targets = set(route.targets)
    if not _NCS_WORDS.search(request):
        # 근거로 새로 쓰는 일은 오래 걸려, 자격 요건 · 우대 사항을 말한 요청일 때만 한다
        targets.discard("NCS_REQUIREMENTS")
    locked = posting.status is not RecruitmentStatus.DRAFT and bool(targets & PROCESS_TARGETS)
    targets -= PROCESS_TARGETS if locked else set()
    if not targets:
        reply = LOCKED_REPLY if locked else (route.question or NOTHING_CHANGED_REPLY)
        return RevisionResult(reply=reply, suggestion=None)

    found: list[str] = []
    for _ in range(ATTEMPTS):
        edit = await _write(llm, posting, writing_style, request, context, targets, found)
        draft = _draft(posting, edit, request)
        if draft.unknown_stages:
            # 모델의 되묻는 말은 평가 방식 같은 다른 것을 묻곤 해서, 정해 둔 말로 종류만 묻는다
            return RevisionResult(reply=_stage_question(draft.unknown_stages), suggestion=None)
        if blocked_terms(draft.content, draft.changed):
            return RevisionResult(reply=BLOCKED_REPLY, suggestion=None)
        found = problems(draft.content, draft.changed, draft.stages, FIELD_LABELS, source=context)
        if not found:
            return _result(draft, edit.cited, locked)
    return RevisionResult(reply=CHECK_FAILED_REPLY, suggestion=None)


async def _write(
    llm: LlmClient,
    posting: PostingDraftContext,
    writing_style: str,
    request: str,
    context: str,
    targets: set[Target],
    found: list[str],
) -> _Edit:
    """고른 대상마다 그 대상만 쓰게 한다. found가 있으면 앞서 쓴 수정안이 걸린 이유를 붙인다."""
    changes: list[FieldChange] = []
    cited: list[NcsUnit] = []
    if "CONTENT" in targets:
        changes = (await _ask(llm, ContentChanges, context, CONTENT_STEP, found)).changes
    if "NCS_REQUIREMENTS" in targets:
        pick = await _ask(llm, NcsPick, context, _ncs_pick_step(), found)
        if units := _chosen_units(pick.ncs_codes):
            ncs = await llm.structured(
                NcsDraft,
                agent=AGENT,
                system=NCS_SYSTEM,
                user=_with_reasons(_ncs_prompt(posting, writing_style, request, units), found),
            )
            changes, cited = _apply_ncs(changes, ncs, units)
    stages: list[StageEdit] | None = None
    if "STAGES" in targets:
        stages = (await _ask(llm, StagePlan, context, STAGES_STEP, found)).stages
    extras: list[str] | None = None
    if "REQUIRED_EXTRAS" in targets:
        extras = list((await _ask(llm, ExtrasPlan, context, EXTRAS_STEP, found)).required_extras)
    return _Edit(changes=changes, stages=stages, required_extras=extras, cited=cited)


async def _ask[T: BaseModel](
    llm: LlmClient, output: type[T], context: str, step: str, found: list[str] | None = None
) -> T:
    return await llm.structured(output, agent=AGENT, system=SYSTEM, user=f"{_with_reasons(context, found)}\n\n{step}")


def _chosen_units(codes: list[str]) -> list[NcsUnit]:
    """모델이 고른 코드 중 실제로 있는 능력단위만, 정해 둔 수까지."""
    units = [unit for code in codes if (unit := unit_by_code(code.strip()))]
    return list({unit.code: unit for unit in units}.values())[:MAX_NCS_UNITS]


def _apply_ncs(
    changes: list[FieldChange], ncs: NcsDraft, units: list[NcsUnit]
) -> tuple[list[FieldChange], list[NcsUnit]]:
    """NCS 정의를 보고 쓴 목록을 바꿀 칸에 넣고, 보여 준 능력단위 중 근거로 쓴 것을 돌려준다.

    목록이 비어 있으면 지금 공고의 목록을 지우지 않게 넣지 않는다. 보여 주지 않은 능력단위는 근거로 치지 않는다.
    """
    shown = {unit.code for unit in units}
    written: list[FieldChange] = []
    cited: dict[str, NcsUnit] = {}
    for name, label in NCS_FIELDS:
        items = [item for item in getattr(ncs, name) if item.text.strip()]
        if not items:
            continue
        written.append(FieldChange(field=label, text=None, items=[item.text for item in items]))
        for code in (code for item in items for code in item.sources):
            if (unit := unit_by_code(code.strip())) and unit.code in shown:
                cited.setdefault(unit.code, unit)
    rewritten = {change.field for change in written}
    kept = [change for change in changes if change.field not in rewritten]
    return kept + written, list(cited.values())


def _draft(posting: PostingDraftContext, edit: _Edit, request: str) -> _Draft:
    content, changed = _apply(posting.content, edit.changes)
    stages: list[StageDraft] | None = None
    unknown: list[str] = []
    if edit.stages is not None:
        current = {stage.name for stage in posting.stages}
        named = [(_tidy(stage.name), stage.type) for stage in edit.stages if _tidy(stage.name)]
        unknown = [name for name, kind in named if kind is None or _ambiguous(name, current, request)]
        proposed = [StageDraft(name=name, type=kind) for name, kind in named if kind is not None]
        if not unknown and proposed != posting.stages:
            stages = proposed
    extras: list[DocumentType] | None = None
    if edit.required_extras is not None:
        proposed_extras = _requested_extras(posting.required_extras, edit.required_extras, request)
        if set(proposed_extras) != set(posting.required_extras):
            extras = proposed_extras
    return _Draft(content=content, changed=changed, stages=stages, required_extras=extras, unknown_stages=unknown)


def _ambiguous(name: str, current: set[str], request: str) -> bool:
    """새로 넣는 전형인데 이름으로 종류를 알 수 없고, 요청에서 그 이름 바로 뒤에 종류가 없으면 되묻는다.

    요청 전체에서 종류 낱말을 찾으면 "서류 다음에 PT 발표 넣어 줘"의 '서류'처럼 다른 전형 이름에 걸린다.
    """
    if name in current or not _AMBIGUOUS_STAGE.search(name) or _CLEAR_STAGE.search(name):
        return False
    spoken, compact = _compact(request), _compact(name)
    at = spoken.find(compact)
    return at < 0 or not _TYPE_WORD.search(spoken[at + len(compact) : at + len(compact) + _TYPE_WINDOW])


_TYPE_WINDOW = 8
"""전형 이름 뒤에서 종류 낱말을 찾는 글자 수 (예: "PT발표를면접전형으로")."""


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _requested_extras(current: list[DocumentType], proposed: list[str], request: str) -> list[DocumentType]:
    """모델이 낸 필수 서류 중 요청에 나온 서류의 변화만 받는다. 나오지 않은 서류는 지금 그대로 둔다."""
    mentioned = {extra for extra, words in EXTRA_WORDS.items() if any(word in request for word in words)}
    wanted = {DocumentType(extra) for extra in proposed}
    kept = {extra for extra in current if extra not in mentioned}
    return sorted(kept | (wanted & mentioned))


def _apply(content: PostingContent, changes: list[FieldChange]) -> tuple[PostingContent, list[str]]:
    """모델이 바꾼 본문 칸을 지금 공고에 합친다. 원래와 같은 칸은 바뀐 칸에 넣지 않는다.

    빈 값은 칸을 지우라는 뜻으로 보지 않는다. 작은 모델이 바꾸지 않을 칸을 빈 값으로 채우기 때문이다.
    """
    updates: dict[str, str | list[str]] = {}
    for change in changes:
        name = LABEL_FIELDS[change.field]
        value: str | list[str] | None = change.text if name in TEXT_FIELDS else change.items
        if value is None:
            continue
        cleaned = _clean(value)
        if cleaned and cleaned != getattr(content, name):
            updates[name] = cleaned
    changed = [name for name in FIELD_LABELS if name in updates]
    return content.model_copy(update=updates), changed


# 목록 항목 앞에 모델이 붙이는 기호와 번호 (예: "- ", "• ", "1. ")
_BULLET = re.compile(r"^(?:[-*•·▪●]|\d+[.)])\s+")


def _clean(value: str | list[str]) -> str | list[str]:
    if isinstance(value, str):
        return _tidy(value)
    return [cleaned for item in value if (cleaned := _tidy(_BULLET.sub("", item.strip())))]


def _tidy(text: str) -> str:
    """뜻이 바뀌지 않는 띄어쓰기만 고친다."""
    return _NUMBER_SPACE.sub(r"\1\2", text).strip()


def _result(draft: _Draft, cited: list[NcsUnit], locked: bool) -> RevisionResult:
    notes = []
    if cited and {name for name, _ in NCS_FIELDS} & set(draft.changed):
        notes.append("근거(NCS): " + ", ".join(f"{unit.subdivision} · {unit.name}" for unit in cited))
    if locked:
        notes.append(LOCKED_REPLY)
    labels = [FIELD_LABELS[name] for name in draft.changed]
    fields = [to_camel(name) for name in draft.changed]
    if draft.stages is not None:
        labels.append("전형 절차")
        fields.append("stages")
    if draft.required_extras is not None:
        labels.append("필수 제출 서류")
        fields.append("requiredDocuments")
    if not labels:
        return RevisionResult(reply=LOCKED_REPLY if locked else NOTHING_CHANGED_REPLY, suggestion=None)
    reply = " ".join([f"{', '.join(labels)} 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요.", *notes])
    return RevisionResult(
        reply=reply,
        suggestion=PostingSuggestion(
            content=draft.content, stages=draft.stages, required_extras=draft.required_extras, changed_fields=fields
        ),
    )


def _stage_question(names: list[str]) -> str:
    quoted = ", ".join(f"'{name}'" for name in names)
    return f"{quoted}의 종류를 알 수 없어요. 서류, 평가, 면접 중 어떤 전형인지 {RETRY_HINT}"


def _with_reasons(prompt: str, found: list[str] | None) -> str:
    """다시 쓸 때 앞서 쓴 수정안이 걸린 이유를 붙인다."""
    if not found:
        return prompt
    reasons = "\n".join(f"- {reason}" for reason in found)
    return f"{prompt}\n\n앞서 쓴 수정안의 문제:\n{reasons}\n문제를 고쳐 다시 쓴다."


def _ncs_pick_step() -> str:
    lines = [
        "지금 할 일: 아래 NCS 능력단위 중 이 직무의 자격 요건 · 우대 사항 근거로 쓸 것을 ncs_codes에 고른다.",
        f"최대 {MAX_NCS_UNITS}개이고 코드는 그대로 옮겨 쓴다. 직무와 관계있는 것이 없으면 빈 목록이다.",
        "",
        "NCS 능력단위 (코드 이름, 수준):",
    ]
    for subdivision in subdivisions():
        lines.append(f"[{subdivision}]")
        lines += [f"{unit.code} {unit.name} (수준 {unit.level})" for unit in units_of(subdivision)]
    return "\n".join(lines)


def _ncs_prompt(posting: PostingDraftContext, writing_style: str, request: str, units: list[NcsUnit]) -> str:
    content = posting.content
    lines = [
        f"채용명: {content.title or '(비어 있음)'}",
        f"직무: {content.job_category or '(비어 있음)'}",
        f"경력: {content.career or '(비어 있음)'}",
    ]
    for name in ("duties", "qualifications", "preferred"):
        lines.append(f"지금 {FIELD_LABELS[name]}:")
        lines += [f"- {item}" for item in getattr(content, name)] or ["(비어 있음)"]
    lines += [
        "",
        f"공고 작성 스타일: {writing_style.strip() or '(없음)'}",
        "",
        f"NCS 능력단위 ({ncs_data().source}):",
        *_unit_lines(units),
        "",
        f"HR 요청: {request}",
    ]
    return "\n".join(lines)


def _unit_lines(units: list[NcsUnit]) -> list[str]:
    """능력단위마다 정의와 수행준거를 적는다. 글자 수 한도는 능력단위끼리 나눠 쓴다."""
    share = NCS_DETAIL_CHARS // max(len(units), 1)
    lines = []
    for unit in units:
        lines.append(f"- {unit.code} {unit.name} (수준 {unit.level}): {unit.definition}")
        used = len(unit.definition)
        for criterion in _spread_criteria(unit):
            if used + len(criterion) > share:
                break
            lines.append(f"  · {criterion}")
            used += len(criterion)
    return lines


def _spread_criteria(unit: NcsUnit) -> list[str]:
    """요소마다 첫 수행준거, 그다음 두 번째 수행준거 순서로 늘어놓는다. 한도에 걸려도 요소가 고루 들어간다."""
    rounds = max((len(element.criteria) for element in unit.elements), default=0)
    return [element.criteria[i] for i in range(rounds) for element in unit.elements if i < len(element.criteria)]


def _context(posting: PostingDraftContext, writing_style: str, request: str) -> str:
    """모든 호출의 앞부분. 지금 공고와 HR 요청이다."""
    lines = ["지금 공고:"]
    for name, label in FIELD_LABELS.items():
        value = getattr(posting.content, name)
        if isinstance(value, list):
            lines.append(f"{label}:")
            lines += [f"- {item}" for item in value] or ["(비어 있음)"]
        else:
            lines.append(f"{label}: {value or '(비어 있음)'}")
    lines.append("전형 절차:")
    lines += [
        f"{number}. {stage.name} ({STAGE_TYPE_LABELS[stage.type]})" for number, stage in enumerate(posting.stages, 1)
    ] or ["(비어 있음)"]
    extras = [extra.label for extra in sorted(posting.required_extras)]
    lines.append(f"필수 제출 서류: {', '.join(['이력서', '자기소개서', *extras])}")
    status = STATUS_LABELS[posting.status]
    if posting.status is not RecruitmentStatus.DRAFT:
        status += " (게시한 뒤라 전형 절차와 필수 제출 서류는 바꿀 수 없다)"
    lines += [
        f"공고 상태: {status}",
        "",
        f"공고 작성 스타일: {writing_style.strip() or '(없음)'}",
        "",
        f"HR 요청: {request}",
    ]
    return "\n".join(lines)
