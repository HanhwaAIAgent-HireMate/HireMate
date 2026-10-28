"""Posting Agent. HR의 수정 요청을 공고 수정안으로 바꾼다. 수정안만 만들고 적용 · 게시하지 않는다 (FR-02~04).

작은 모델은 한 번에 여러 칸을 채우게 하면 바꾸지 않을 칸까지 채우고 오래 걸린다. 그래서 짧게 나눠 묻는다.

1. 요청이 바꾸라는 대상을 고른다 (본문 칸, 전형 절차, 필수 제출 서류, NCS 근거로 자격 요건 · 우대 사항 쓰기).
2. 고른 대상마다 그 대상만 쓰게 한다. 게시 뒤 바꿀 수 없는 대상은 묻지 않는다.

모든 호출의 system과 앞부분(지금 공고, HR 요청)이 같아, 모델은 앞부분을 다시 읽지 않는다. 할 일은 끝에 붙인다.
지금 공고에 합치고 바뀐 칸을 고르는 일은 코드가 한다. 모델이 바뀌었다고 말하는 칸을 믿지 않고 원래 공고와 비교한다.
NCS 근거는 고른 능력단위의 정의를 보여 주고 쓰게 하며, 근거 코드는 실제로 있는 능력단위인지 확인한다 (규칙 7).
고른 능력단위는 NCS 중요도 및 활용도 조사 점수가 높은 것을 앞에 놓고 앞쪽부터 쓰게 한다.
자격 요건 · 우대 사항 중 무엇을 몇 개 쓸지는 코드가 요청과 지금 공고를 보고 정해 모델에게 알려 준다.
HR이 줄을 골라 요청하면 대상을 고르지 않고 그 줄만 한 번에 쓰게 한다. 고른 줄 밖은 코드가 그대로 둔다.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from hiremate_ai.agents.generation.posting.checks import JUDGED_FIELDS, blocked_terms, problems
from hiremate_ai.agents.generation.posting.types import (
    PostingDraftContext,
    PostingFocus,
    PostingSuggestion,
    RecruitmentStatus,
    RevisionResult,
    StageDraft,
    StageIcon,
)
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.contract import DocumentType, PostingContent, PostingRole, StageType
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.tools.ncs import NcsUnit, ncs_data, subdivisions, survey_score, unit_by_code, units_of

AGENT = "posting"
"""호출 로그와 backend 연동 경로(/agents/posting/...)에 쓰는 Agent 키."""

FIELD_LABELS = {
    "title": "채용명",
    "job_category": "직무",
    "employment_type": "고용 형태",
    "career": "경력",
    "location": "근무지",
    "headcount": "채용 인원",
    "position": "직급",
    "education": "학력",
    "work_hours": "근무 일시",
    "salary": "급여",
    "intro": "회사 소개",
    "duties": "주요 업무",
    "qualifications": "자격 요건",
    "preferred": "우대 사항",
    "benefits": "복지",
    "roles": "직무별 모집 내용",
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
FOCUS_MISSING_REPLY = "고른 줄을 공고에서 찾지 못했어요. 줄을 다시 골라 주세요."
LINE_UNCHANGED_REPLY = "고른 줄에서 바꿀 부분을 찾지 못했어요. 어떻게 고칠지 알려 주세요."
UNCHANGED_LINE = "고른 줄을 바꾸지 않고 그대로 썼다. 요청대로 바꿔 쓴다"
MULTILINE_LINE = "고른 줄 하나를 한 줄로 쓰지 않고 칸 이름이나 여러 줄을 썼다"
"""고른 줄을 다시 쓰게 할 때 붙이는 이유. 작은 모델이 고른 줄을 그대로 돌려주거나 칸 전체를 한 줄에 쓰곤 한다."""

ATTEMPTS = 2
"""처음 한 번과, 검사에 걸렸을 때 이유를 붙여 다시 쓰는 한 번."""

MAX_NCS_UNITS = 8
"""정의와 수행준거를 보여 줄 능력단위 수. 더 고르면 조사 점수가 낮은 것부터 뺀다."""

NCS_ORDER_NOTE = (
    "(우선순위 순서다. NCS 현장 조사에서 중요하게 본 능력단위를 앞에 놓았다. "
    "앞쪽 능력단위로 먼저 쓰고 목록에서도 앞에 둔다. 자격 요건과 우대 사항은 이 순서가 아니라 규칙 3으로 나눈다.)"
)
"""조사가 있는 능력단위를 둘 이상 보여 줄 때 능력단위 목록 앞에 붙인다."""

ADVANCED_LABEL = "수준이 높은 능력단위"
"""보여 준 능력단위 중 NCS 수준이 가장 높은 것을 능력단위 목록 뒤에 이 이름으로 적는다 (NCS_SYSTEM 규칙 3)."""

JUNIOR_NOTE = "(신입이 지원하는 공고라서 이 능력단위의 능력은 우대 사항에만 쓴다)"
"""규칙 3의 '주요 업무에 꼭 필요하면 자격 요건'을 두면 모델이 신입 공고에도 어려운 능력을 필수로 넣는다."""
_JUNIOR = re.compile(r"신입")
"""경력 칸에 이 말이 있으면 신입이 지원하는 공고다 (예: 신입, 신입 · 경력)."""

NCS_DETAIL_CHARS = 3000
"""두 번째 호출에 넣는 능력단위 정의와 수행준거의 글자 수 한도. 능력단위 하나에 평균 700자라 다 넣으면
노트북 모델이 한 번에 읽는 양(약 4천 토큰)을 넘는다. 지식 · 기술은 일반적인 말이라 공고 문장에는 넣지 않는다."""

DEFAULT_ITEMS = 5
"""요청에 개수가 없을 때 NCS 근거로 쓰는 자격 요건 · 우대 사항의 최대 수. 읽기 쉬운 분량으로 제한하되,
근거를 찾을 수 있는 만큼만 쓰고 개수를 채우려고 지어내지 않는다."""

MAX_DRAFT_ITEMS = 10
"""NCS 근거로 한 번에 쓰는 목록 하나의 항목 수 한도. 항목이 많을수록 오래 걸리고 근거가 얇아진다."""

ContentLabel = Literal[
    "채용명",
    "직무",
    "고용 형태",
    "경력",
    "근무지",
    "채용 인원",
    "직급",
    "학력",
    "근무 일시",
    "급여",
    "회사 소개",
    "주요 업무",
    "자격 요건",
    "우대 사항",
    "복지",
]
"""모델이 바꿀 칸을 고르는 이름. 영어 필드 이름을 주면 작은 모델이 '근무지'를 job_category에 넣는 식으로 헷갈린다."""
LABEL_FIELDS = {label: name for name, label in FIELD_LABELS.items()}
TEXT_FIELDS = (
    "title",
    "job_category",
    "employment_type",
    "career",
    "location",
    "position",
    "education",
    "work_hours",
    "salary",
    "intro",
)
NCS_FIELDS: tuple[tuple[str, ContentLabel], ...] = (("qualifications", "자격 요건"), ("preferred", "우대 사항"))
MAX_HEADCOUNT = 9999
"""채용 인원 한도. backend PostingContentRequest와 같다."""

EXTRA_WORDS = {DocumentType.PORTFOLIO: ("포트폴리오",), DocumentType.CERTIFICATE: ("자격증",)}
"""필수 서류는 요청에 그 서류가 나올 때만 넣고 뺀다. 작은 모델이 요청하지 않은 서류를 더하곤 한다."""

_STAGE_WORDS = re.compile(
    r"전형|절차|면접|서류|평가|테스트|시험|검사|과제|코딩|순서|순으로|단계|PT|발표|워크숍|아이콘", re.I
)
"""전형 절차는 요청에 전형을 말하는 낱말이 있을 때만 바꾼다. 작은 모델이 "5명 채용하려고 해" 같은 요청에도
하지 말라는 지시를 어기고 전형 절차를 고르곤 한다."""

FACT_WORDS = {
    "employment_type": re.compile(r"고용|정규직|계약직|인턴|파견|프리랜서|아르바이트|알바|비정규|전환형"),
    "career": re.compile(r"경력|신입|년차|연차|\d+\s*년|무관|주니어|시니어"),
    "headcount": re.compile(r"인원|\d+\s*명|(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*명"),
    "position": re.compile(r"직급|직위|직책|사원|주임|대리|과장|차장|부장|선임|책임|수석"),
    "education": re.compile(r"학력|학위|학사|석사|박사|졸업|대졸|고졸|초대졸"),
    "work_hours": re.compile(r"근무\s*(?:시간|일시|요일|일|형태)|출근|퇴근|시차|교대|주\s*\d\s*일|\d+\s*시"),
    "salary": re.compile(r"급여|연봉|월급|임금|보수|시급|처우|\d\s*(?:만\s*)?원"),
    "intro": re.compile(r"소개"),
    "benefits": re.compile(r"복지|혜택|복리"),
}
"""회사가 알려 주는 사실을 담는 칸과, 요청에서 그 칸을 말하는 낱말. 요청에서 그 칸을 말했을 때만 바꾼다.
작은 모델이 공고 전체를 써 달라는 요청에 회사가 알려 주지 않은 복지 · 회사 소개 · 근무 조건을 지어내곤 한다.
경력 · 고용 형태도 회사가 정할 일이라, 말하지 않았는데 흔한 값("경력 3년 이상", "정규직")을 채우면 지어낸 것이다."""

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

# NCS 근거로 쓸 목록을 요청에서 찾는 말. '자격증'은 필수 제출 서류라 자격 요건으로 보지 않는다
_LIST_WORDS = {"qualifications": r"자격\s*요건|자격(?!증)|요건", "preferred": r"우대\s*사항|우대"}
# 목록 이름 바로 뒤의 "그대로 두고", "말고"는 그 목록을 쓰지 말라는 뜻이고, "만"은 그 목록만 쓰라는 뜻이다
_KEEP = r"\s*(?:은|는|을|를)?\s*(?:그대로|말고|빼고|제외)"
_ONLY = r"\s*만(?![들큼약일족])"
_COUNT = r"(\d+|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:개|가지)"
_KOREAN_NUMBERS = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
_COUNT_WINDOW = 8
"""목록 이름 뒤에서 개수를 찾는 글자 수 (예: "자격 요건은 7개로")."""
# 목록 전체를 쓰라는 말과, 항목을 더하거나 빼라는 말. 작은 모델이 "우대 사항만 3개 써 줘"를 고치기(CONTENT)로 골라
# 근거 없이 항목을 지어내서, 목록을 새로 쓰라는 요청은 코드가 NCS 근거 쓰기로 돌린다
_WRITE_WORDS = re.compile(r"써|쓰|작성|만들|채워")
_REWRITE_WORDS = re.compile(r"다시|새로|전부|전체")
_EDIT_WORDS = re.compile(r"추가|더해|넣어|넣고|빼|삭제|지워|고쳐|수정")

# 모델이 숫자와 단위 사이에 넣는 공백 (예: "1 차 면접", "20 대")
_NUMBER_SPACE = re.compile(r"(\d)\s+(차|대|년|개월|월|일|시간|시|분|명|회|개|단계|주)")
# 모델이 영어 · 숫자와 조사 사이에 넣는 공백 (예: "Java 와 Spring Boot 를"). 조사 뒤가 띄어쓰기나 끝일 때만 붙여
# "Java 이상", "Kafka 로그"처럼 조사로 시작하는 낱말은 건드리지 않는다
_PARTICLE_SPACE = re.compile(
    r"(?<=[A-Za-z0-9+#)])\s+(?=(?:와|과|를|을|는|은|이|가|의|으로|로|에서|에|도|만|까지|부터)(?:[\s,.·)]|$))"
)

Target = Literal["CONTENT", "STAGES", "REQUIRED_EXTRAS", "NCS_REQUIREMENTS", "ROLES"]
PROCESS_TARGETS: frozenset[Target] = frozenset({"STAGES", "REQUIRED_EXTRAS"})
"""게시한 뒤에는 바꿀 수 없는 대상."""

# 모델에게서 받는 답. 모든 필드를 필수(값이 없으면 null)로 둔다. 선택 필드로 두면 작은 모델이 필드를 통째로 빼먹는다.


class Route(BaseModel):
    """첫 호출: 요청이 바꾸라는 대상.

    writes_posting을 먼저 정하게 해야 작은 모델이 공고 전체를 써 달라는 요청을 알아본다.
    """

    writes_posting: bool = Field(
        description="HR이 뽑으려는 직무 · 경력 · 인원을 말하며 공고를 써 달라거나 채용하겠다고 하면 true. "
        "이미 있는 칸 몇 개를 바꾸라는 요청이면 false"
    )
    targets: list[Target] = Field(description="요청이 바꾸라는 대상. 알 수 없으면 빈 목록")
    question: str | None = Field(description="무엇을 바꾸라는지 알 수 없을 때 HR에게 되묻는 한 문장. 아니면 null")


class FieldChange(BaseModel):
    """바꿀 본문 칸 하나. 글 칸은 text, 목록 칸은 items에 쓰고 다른 하나는 null이다."""

    field: ContentLabel = Field(description="바꿀 본문 칸")
    text: str | None = Field(description="목록이 아닌 글 칸(채용명, 근무지, 급여, 회사 소개 등)의 새 내용")
    items: list[str] | None = Field(description="목록 칸(주요 업무, 자격 요건, 우대 사항, 복지)의 바꾼 뒤 목록 전체")


class ContentChanges(BaseModel):
    changes: list[FieldChange] = Field(description="요청이 바꾸라는 본문 칸만")


class RoleChanges(BaseModel):
    roles: list[PostingRole] = Field(max_length=10)


class StageEdit(BaseModel):
    """전형 하나. 종류를 알 수 없으면 type을 null로 두고 되묻는다."""

    name: str = Field(description="전형 이름. HR이 말한 이름 그대로")
    type: StageType | None = Field(description="DOCUMENT(서류), ASSESSMENT(평가), INTERVIEW(면접). 알 수 없으면 null")
    icon: StageIcon | None = Field(
        default=None,
        description=(
            "아이콘 변경 요청에만 지정. AUTO 기본, NONE 없음, FILE_TEXT 문서, CLIPBOARD_CHECK 체크리스트, "
            "CODE 코드, PRESENTATION 발표, MESSAGES 대화, USERS 사람, VIDEO 화상, BADGE_CHECK 배지, "
            "CHAIR 실무면접 의자, HEALTH 검진. 변경하지 않으면 null"
        ),
    )


class StagePlan(BaseModel):
    stages: list[StageEdit] = Field(description="바꾼 뒤의 전형 전체를 순서대로")


class ExtrasPlan(BaseModel):
    required_extras: list[Literal["PORTFOLIO", "CERTIFICATE"]] = Field(
        description="이력서 · 자기소개서 밖에 필수로 받을 서류 전체"
    )


class LineEdit(BaseModel):
    """HR이 고른 목록 줄 하나를 고친 답. 지울지는 action으로 고른다.

    text를 null로 두어 지우게 하면 작은 모델이 null 대신 목록을 통째로 쓴다.
    """

    action: Literal["REWRITE", "DELETE"] = Field(
        description="REWRITE(고친 줄을 text에 쓴다) 또는 DELETE(그 줄을 지운다)"
    )
    text: str | None = Field(description="REWRITE면 고친 뒤의 줄 한 줄. DELETE면 null")


class IntroEdit(BaseModel):
    """HR이 고른 회사 소개를 고친 답."""

    text: str = Field(description="고친 뒤의 회사 소개 전체")


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
- CONTENT: 공고 본문 칸(채용명, 직무, 고용 형태, 경력, 근무지, 채용 인원, 직급, 학력, 근무 일시, 급여, 회사 소개,
  주요 업무, 자격 요건, 우대 사항, 복지)을 고치거나 항목을 더하고 빼기.
- STAGES: 전형 절차. 전형 이름은 HR이 말한 그대로 두고 종류를 정한다. 종류는 DOCUMENT(서류: 지원서와 제출 서류 검토),
  ASSESSMENT(평가: 코딩테스트, 인적성, 직무역량 평가, 과제), INTERVIEW(면접: 실무면접, 임원면접)다.
- REQUIRED_EXTRAS: 필수 제출 서류. 이력서와 자기소개서는 항상 받는다. 더 받을 수 있는 것은 PORTFOLIO(포트폴리오),
  CERTIFICATE(자격증)뿐이다.
- NCS_REQUIREMENTS: 자격 요건이나 우대 사항을 새로 쓰거나 전체를 다시 쓰기. NCS 능력단위를 근거로 쓴다.
  항목 하나를 더하거나 고치는 정도면 CONTENT다.
- ROLES: 백엔드·인사·생산관리처럼 여러 모집 직무를 한 공고의 직무별 표로 작성하거나 그 표를 수정한다.
  여러 직무를 채용한다고 하면 CONTENT와 ROLES를 함께 선택한다. 전형 절차나 팀 문화의 목록과 혼동하지 않는다.

규칙:
1. 요청하지 않은 대상과 칸은 바꾸지 않는다.
2. 회사가 알려 주지 않은 사실(급여, 복지, 근무 일시, 직급, 학력, 채용 인원, 회사 정보)은 지어내지 않는다.
   지금 공고와 HR 요청에 있는 내용만 쓴다.
3. 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 자격 요건이나 우대 사항에 넣지 않는다.
4. 회사의 공고 작성 스타일이 있으면 따른다. 한국어로 쓰고, 목록 항목은 앞에 기호 없이 한 줄로 짧게 쓴다."""

ROUTE_STEP = (
    "지금 할 일: 먼저 writes_posting을 정한다. HR이 뽑으려는 직무 · 경력 · 인원을 말하며 공고를 써 달라거나 "
    "채용하겠다고 하면(예: '경력 3년 이상 5명 채용하려고 해', '프론트엔드 신입 공고 만들어 줘') true, "
    "이미 있는 칸 몇 개를 바꾸라는 요청이면 false다. 그다음 요청이 바꾸라는 대상을 targets에 고른다. "
    "요청하지 않은 대상은 넣지 않는다. 전형 절차를 말하지 않았으면 STAGES를 넣지 않는다. "
    "전형 아이콘 변경도 STAGES다. 이름·종류·순서는 유지하고 icon만 바꾼다. "
    "무엇을 바꾸라는지 알 수 없으면 targets를 비우고 question에 되묻는 한 문장을 쓴다."
)
CONTENT_STEP = (
    "지금 할 일: 본문 칸 중 요청이 바꾸라는 칸만 changes에 쓴다. field에는 칸 이름(예: 근무지, 우대 사항)을 쓴다. "
    "글 칸(채용명, 직무, 고용 형태, 경력, 근무지, 채용 인원, 직급, 학력, 근무 일시, 급여, 회사 소개)은 text에 "
    "새 내용을, 목록 칸(주요 업무, 자격 요건, 우대 사항, 복지)은 items에 그대로 둘 항목까지 넣은 바꾼 뒤 목록 전체를 "
    "쓰고, 다른 하나는 null로 둔다. 채용 인원은 숫자만 쓴다(예: 3). "
    "text에는 현재 값을 복사하지 않고 요청한 새 값을 쓴다. "
    "예: 현재 근무지가 서울이고 '근무지만 부산으로 바꿔줘'라는 요청이면 field='근무지', text='부산'이다. "
    "경력 조건을 바꾸면 자격 요건과 우대 사항에 같은 이전 경력 조건이 있는지 확인하고 함께 맞춘다. "
    "예: 경력 3년 이상을 5년 이상으로 변경하면 '서버 개발 경력 3년 이상'도 5년 이상으로 고친다. "
    "별도의 기술별 경력이나 다른 조건은 유지한다."
)
STAGES_STEP = (
    "지금 할 일: 바꾼 뒤의 전형 절차 전체를 순서대로 stages에 쓴다. 이름만으로 종류를 알 수 없는 전형"
    "(예: PT, 발표, 워크숍)은 추측하지 말고 type을 null로 둔다. "
    "아이콘 변경도 STAGES 대상이다. 아이콘만 바꾸라는 요청은 전형 이름·종류·순서를 그대로 유지하고 "
    "해당 전형의 icon만 지정한다. HR이 지정한 아이콘은 전형 종류의 기본 아이콘보다 우선한다. "
    "예: '실무면접을 사람 아이콘으로'는 icon=USERS, '대화 아이콘'은 MESSAGES, '의자 아이콘'은 CHAIR다. "
    "변경 대상이 아닌 전형의 icon은 null로 둔다."
)
EXTRAS_STEP = "지금 할 일: 요청대로 바꾼 뒤, 이력서 · 자기소개서 밖에 필수로 받을 서류 전체를 required_extras에 쓴다."

NCS_SYSTEM = """너는 채용 공고의 자격 요건과 우대 사항을 NCS(국가직무능력표준) 능력단위를 근거로 쓰는 Posting Agent다.

규칙:
1. 주어진 능력단위의 정의와 수행준거에 있는 능력을 지원자가 읽기 쉬운 공고 문장으로 바꿔 쓴다.
   수행준거 문장을 그대로 옮기지 않는다. 정의와 수행준거에 없는 기술 이름(언어, 프레임워크, 자격증)은
   지금 공고나 HR 요청에 있을 때만 쓴다.
2. 항목마다 근거로 쓴 능력단위 코드를 sources에 적는다. 그 능력단위의 정의와 수행준거에 없는 내용
   (예: 주요 업무에서만 가져온 내용)이면 그 코드를 적지 않는다. 근거가 없는 항목은 sources를 비운다.
3. 자격 요건은 지원에 꼭 필요한 조건이고, 우대 사항은 있으면 좋은 조건이다.
   "수준이 높은 능력단위"에 적힌 능력은 주요 업무에 꼭 필요한 것이 아니면 우대 사항에 쓴다.
4. 같은 능력을 자격 요건과 우대 사항에 함께 쓰지 않는다. 한 능력단위를 두 목록에 쓰면
   서로 다른 세부 능력([ ] 안의 이름)을 쓰거나, 자격 요건은 기본, 우대 사항은 그보다 깊은 수준으로 차이가 드러나게 쓴다.
   다른 세부 능력도 주요 업무와 관련 있는 것만 쓴다. 관련 있는 세부 능력이 하나뿐이면 한 목록에만 쓴다.
5. 지금 공고의 항목 중 요청과 관계없이 그대로 둘 항목도 함께 쓴다.
6. 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 넣지 않는다. 회사가 알려 주지 않은 사실은 지어내지 않는다.
7. 항목은 40자 안팎의 한 줄로, 공고에 쓰는 쉬운 말로 쓴다.
   수행준거의 "~할 수 있는 능력" 말투나 전문 용어를 늘어놓지 않고 "~ 경험", "~ 능력"으로 끝낸다. 한국어로 쓴다.
8. 목록마다 "지금 할 일"에 적힌 개수를 채운다. 능력단위마다 세부 능력([ ] 안의 이름)이 여러 개라 보통 채울 수 있다.
   능력단위와 지금 공고에서 더는 근거를 찾을 수 없을 때만 그보다 적게 쓴다.
   개수를 채우려고 같은 능력을 말만 바꿔 다시 쓰거나 근거 없는 항목을 만들지 않는다."""


@dataclass(frozen=True)
class _Edit:
    """고른 대상마다 받은 답을 모은 것. 고르지 않은 대상은 None이다. notes는 답에 덧붙일 안내다."""

    changes: list[FieldChange] = field(default_factory=list)
    stages: list[StageEdit] | None = None
    required_extras: list[str] | None = None
    cited: list[NcsUnit] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    roles: list[PostingRole] | None = None


@dataclass(frozen=True)
class _Draft:
    """답을 지금 공고에 합친 결과. changed는 바뀐 본문 칸, stages · required_extras는 바뀌었을 때만 있다."""

    content: PostingContent
    changed: list[str]
    stages: list[StageDraft] | None
    required_extras: list[DocumentType] | None
    unknown_stages: list[str]


async def revise_posting(
    llm: LlmClient,
    posting: PostingDraftContext,
    writing_style: str,
    request: str,
    focus: PostingFocus | None = None,
) -> RevisionResult:
    """HR의 요청대로 공고 수정안을 만든다. 되묻거나 처리할 수 없으면 수정안 없이 답만 한다.

    수정안이 검사에 걸리면 이유를 붙여 한 번 더 쓰게 한다. 차별 조건은 다시 쓰게 하지 않고 바로 거절한다.
    focus가 있으면 HR이 고른 그 줄만 고친다.
    """
    if focus is not None:
        return await _revise_line(llm, posting, writing_style, request, focus)
    if blocked_attribute(request) and _JUDGING.search(request):
        return RevisionResult(reply=BLOCKED_REPLY, suggestion=None)
    if _ANSWER_ONLY.fullmatch(_compact(request)):
        return RevisionResult(reply=ANSWER_ONLY_REPLY, suggestion=None)
    context = _context(posting, writing_style, request)
    route = await _ask(llm, Route, context, ROUTE_STEP)
    targets = set(route.targets)
    if "CONTENT" in targets and _writes_whole_list(posting.content, request):
        targets.add("NCS_REQUIREMENTS")
    # 공고 전체를 써 달라는 요청이면 자격 요건 · 우대 사항을 말하지 않았어도 비어 있는 목록을 NCS 근거로 쓴다
    fills_empty = (
        route.writes_posting
        and "ROLES" not in targets
        and not _NCS_WORDS.search(request)
        and _has_empty_list(posting.content)
    )
    if fills_empty:
        targets.add("NCS_REQUIREMENTS")
    elif not _NCS_WORDS.search(request):
        # 근거로 새로 쓰는 일은 오래 걸려, 자격 요건 · 우대 사항을 말한 요청일 때만 한다
        targets.discard("NCS_REQUIREMENTS")
    if not _STAGE_WORDS.search(request):
        targets.discard("STAGES")
    locked = posting.status is not RecruitmentStatus.DRAFT and bool(targets & PROCESS_TARGETS)
    targets -= PROCESS_TARGETS if locked else set()
    if not targets:
        reply = LOCKED_REPLY if locked else (route.question or NOTHING_CHANGED_REPLY)
        return RevisionResult(reply=reply, suggestion=None)

    found: list[str] = []
    for _ in range(ATTEMPTS):
        edit = await _write(llm, posting, writing_style, request, context, targets, found, fills_empty)
        draft = _draft(posting, edit, request)
        if draft.unknown_stages:
            # 모델의 되묻는 말은 평가 방식 같은 다른 것을 묻곤 해서, 정해 둔 말로 종류만 묻는다
            return RevisionResult(reply=_stage_question(draft.unknown_stages), suggestion=None)
        if blocked_terms(draft.content, draft.changed):
            return RevisionResult(reply=BLOCKED_REPLY, suggestion=None)
        found = problems(draft.content, draft.changed, draft.stages, FIELD_LABELS, source=context)
        found += career_conflicts(posting.content, draft.content)
        if fills_empty and not posting.content.duties and not draft.content.duties:
            found.append("공고 전체 작성 요청인데 주요 업무가 비어 있다. 직무의 일반적인 주요 업무 초안을 3~5개 쓴다")
        if not found:
            return _result(draft, edit, locked)
    return RevisionResult(reply=CHECK_FAILED_REPLY, suggestion=None)


async def _revise_line(
    llm: LlmClient, posting: PostingDraftContext, writing_style: str, request: str, focus: PostingFocus
) -> RevisionResult:
    """HR이 고른 줄만 고친다. 고른 칸이 자격 요건 · 우대 사항이면 요청에 차별 조건이 있을 때 바로 거절한다.

    회사 소개는 줄 하나짜리 목록으로 다룬다. 고친 줄이 그대로이거나 검사에 걸리면 이유를 붙여 한 번 더 쓰게 한다.
    """
    if blocked_attribute(request) and (focus.field in JUDGED_FIELDS or _JUDGING.search(request)):
        return RevisionResult(reply=BLOCKED_REPLY, suggestion=None)
    value: str | list[str] = getattr(posting.content, focus.field)
    listed = isinstance(value, list)
    lines = list(value) if isinstance(value, list) else [value]
    index = focus.index if listed else 0
    if index is None or not 0 <= index < len(lines):
        return RevisionResult(reply=FOCUS_MISSING_REPLY, suggestion=None)
    label = FIELD_LABELS[focus.field]
    where = f"{label} {index + 1}번 줄" if listed else label
    context = _context(posting, writing_style, request)
    step = _line_step(where, lines[index], listed)
    found: list[str] = []
    revised = lines
    for _ in range(ATTEMPTS):
        revised = await _rewrite_line(llm, context, step, found, lines, index, listed)
        if revised == lines:
            found = [UNCHANGED_LINE]
            continue
        content = posting.content.model_copy(update={focus.field: revised if listed else revised[0]})
        if blocked_terms(content, [focus.field]):
            return RevisionResult(reply=BLOCKED_REPLY, suggestion=None)
        found = problems(content, [focus.field], None, FIELD_LABELS, source=context)
        removed = len(revised) < len(lines)
        if listed and not removed and "\n" in revised[index]:
            found.append(MULTILINE_LINE)
        if not found:
            reply = (
                f"{where}을 지운 수정안을 만들었어요. 확인하고 적용해 주세요."
                if removed
                else f"{where} 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요."
            )
            return RevisionResult(
                reply=reply,
                suggestion=PostingSuggestion(
                    content=content, stages=None, required_extras=None, changed_fields=[to_camel(focus.field)]
                ),
            )
    return RevisionResult(reply=LINE_UNCHANGED_REPLY if revised == lines else CHECK_FAILED_REPLY, suggestion=None)


def _line_step(where: str, line: str, listed: bool) -> str:
    """고른 줄만 고치게 하는 할 일. 고른 줄을 함께 적어야 작은 모델이 다른 줄과 헷갈리지 않는다.

    목록의 줄은 지울지부터 정하게 한다. 고치는 법을 먼저 말하면 작은 모델이 지우라는 요청에도 REWRITE를 고른다.
    """
    if not listed:
        return f'지금 할 일: HR이 고른 {where}("{line}")만 요청대로 고쳐 text에 쓴다. 다른 칸은 쓰지 않는다.'
    return (
        f'지금 할 일: HR이 고른 {where}("{line}")을 다룬다. 먼저 HR 요청이 이 줄을 지우라는 것인지 본다. '
        "지우라는 요청이면 action을 DELETE로, text를 null로 둔다. "
        "아니면 action을 REWRITE로 두고 이 줄만 요청대로 고친 한 줄을 text에 쓴다. 칸 이름이나 다른 줄은 쓰지 않는다."
    )


async def _rewrite_line(
    llm: LlmClient, context: str, step: str, found: list[str], lines: list[str], index: int, listed: bool
) -> list[str]:
    """모델이 고친 줄을 넣은 목록. 목록의 줄은 DELETE면 지운다. 빈 답이면 그대로 둬, 회사 소개는 지우지 않는다."""
    if listed:
        edit = await _ask(llm, LineEdit, context, step, found)
        if edit.action == "DELETE":
            return lines[:index] + lines[index + 1 :]
        text = _BULLET.sub("", (edit.text or "").strip())
    else:
        text = (await _ask(llm, IntroEdit, context, step, found)).text
    cleaned = _tidy(text)
    return lines[:index] + [cleaned] + lines[index + 1 :] if cleaned else lines


async def _write(
    llm: LlmClient,
    posting: PostingDraftContext,
    writing_style: str,
    request: str,
    context: str,
    targets: set[Target],
    found: list[str],
    fills_empty: bool = False,
) -> _Edit:
    """고른 대상마다 그 대상만 쓰게 한다. found가 있으면 앞서 쓴 수정안이 걸린 이유를 붙인다.

    fills_empty면 NCS 근거로 비어 있는 자격 요건 · 우대 사항만 쓴다 (공고 전체를 써 달라는 요청).
    """
    changes: list[FieldChange] = []
    cited: list[NcsUnit] = []
    notes: list[str] = []
    if "CONTENT" in targets:
        step = CONTENT_STEP
        if fills_empty and not posting.content.duties:
            step += (
                " 공고 전체 작성 요청이다. 주요 업무가 비어 있다. "
                "직무에 맞는 일반적인 업무 초안을 3~5개 반드시 쓴다. "
                "회사의 실제 업무나 기술로 단정하지 않고 회사 고유 정보는 만들지 않는다."
            )
        step += f"\n이번에 반영할 HR 요청: {request}"
        changes = (await _ask(llm, ContentChanges, context, step, found)).changes
    roles = None
    if "ROLES" in targets:
        roles = (
            await _ask(
                llm,
                RoleChanges,
                context,
                "지금 할 일: 요청한 모집 직무를 roles의 별도 행으로 나눠 작성한다. name은 HR이 말한 직무 이름, "
                "career는 요청한 신입/경력 구분이다. 경력을 말하지 않았으면 빈 문자열이다. duties, qualifications, "
                "preferred는 직무별 일반적인 초안을 각각 3~5개 쓴다. 급여, 복지, 인원이나 회사만의 기술·실적은 "
                "지어내지 않는다. 수정하지 않은 직무는 기존대로 보존한다. 삭제 요청은 해당 행을 뺀 목록을 반환한다.",
                found,
            )
        ).roles
    if "NCS_REQUIREMENTS" in targets and (plan := _ncs_plan(posting.content, request, fills_empty)):
        pick = await _ask(llm, NcsPick, context, _ncs_pick_step(), found)
        if units := _chosen_units(pick.ncs_codes):
            counts = {name: min(max(count, 1), MAX_DRAFT_ITEMS) for name, count in plan.items()}
            ncs = await llm.structured(
                NcsDraft,
                agent=AGENT,
                system=NCS_SYSTEM,
                user=_with_reasons(_ncs_prompt(posting, writing_style, request, units, counts), found),
            )
            changes, cited, written = _apply_ncs(changes, ncs, units, counts)
            notes = _count_notes(plan, counts, written)
    stages: list[StageEdit] | None = None
    if "STAGES" in targets:
        stages = (await _ask(llm, StagePlan, context, STAGES_STEP, found)).stages
    extras: list[str] | None = None
    if "REQUIRED_EXTRAS" in targets:
        extras = list((await _ask(llm, ExtrasPlan, context, EXTRAS_STEP, found)).required_extras)
    return _Edit(changes=changes, stages=stages, required_extras=extras, cited=cited, notes=notes, roles=roles)


async def _ask[T: BaseModel](
    llm: LlmClient, output: type[T], context: str, step: str, found: list[str] | None = None
) -> T:
    return await llm.structured(output, agent=AGENT, system=SYSTEM, user=f"{_with_reasons(context, found)}\n\n{step}")


def _ncs_plan(content: PostingContent, request: str, empty_only: bool = False) -> dict[str, int]:
    """NCS 근거로 쓸 목록과 요청한 항목 수.

    요청에서 말한 목록은 요청대로 쓰고(개수가 없으면 DEFAULT_ITEMS), 말하지 않은 목록은 비어 있을 때만 쓴다.
    HR이 다듬어 둔 목록을 덮어쓰지 않기 위해서다. "우대 사항만"이면 그 목록만 쓰고, "자격 요건은 그대로 두고"면
    그 목록은 쓰지 않는다. 목록을 말하지 않은 요청(예: "NCS 기반으로 써 줘")은 둘 다 말한 것으로 본다.
    empty_only면 비어 있는 목록만 쓴다.
    """
    if empty_only:
        return {name: DEFAULT_ITEMS for name in _LIST_WORDS if not getattr(content, name)}
    said = {name for name, words in _LIST_WORDS.items() if re.search(words, request)} or set(_LIST_WORDS)
    kept = {name for name, words in _LIST_WORDS.items() if re.search(f"(?:{words}){_KEEP}", request)}
    only = {name for name, words in _LIST_WORDS.items() if re.search(f"(?:{words}){_ONLY}", request)}
    empty = {name for name in _LIST_WORDS if not getattr(content, name)}
    names = (only or (said | empty)) - kept
    plan: dict[str, int] = {}
    for name, words in _LIST_WORDS.items():
        if name in names:
            spoken = _spoken_count(words, request)
            plan[name] = _number(spoken.group(1)) if spoken else DEFAULT_ITEMS
    return plan


def _has_empty_list(content: PostingContent) -> bool:
    return any(not getattr(content, name) for name in _LIST_WORDS)


def _writes_whole_list(content: PostingContent, request: str) -> bool:
    """자격 요건 · 우대 사항 목록을 새로 쓰라는 요청인지.

    개수를 말했거나, 다시 쓰라고 했거나, 비어 있는 목록을 쓰라는 요청이다.
    항목을 더하거나 빼라는 말이 있으면 고치기로 둔다 (예: "우대 사항에 AWS 경험 하나 추가해 줘").
    """
    if _EDIT_WORDS.search(request) or not _WRITE_WORDS.search(request):
        return False
    return any(
        re.search(words, request)
        and (not getattr(content, name) or _REWRITE_WORDS.search(request) or _spoken_count(words, request))
        for name, words in _LIST_WORDS.items()
    )


def _spoken_count(words: str, request: str) -> re.Match[str] | None:
    """목록 이름 바로 뒤의 개수(예: "자격 요건은 7개"), 없으면 "3개씩"처럼 모든 목록에 붙인 개수."""
    own = re.search(rf"(?:{words})[^\d\n]{{0,{_COUNT_WINDOW}}}?{_COUNT}", request)
    return own or re.search(rf"{_COUNT}\s*씩", request)


def _number(word: str) -> int:
    return int(word) if word.isdigit() else _KOREAN_NUMBERS[word]


def _chosen_units(codes: list[str]) -> list[NcsUnit]:
    """모델이 고른 코드 중 실제로 있는 능력단위만, 조사 점수 순서로(_by_survey) 정해 둔 수까지."""
    units = [unit for code in codes if (unit := unit_by_code(code.strip()))]
    return _by_survey(list({unit.code: unit for unit in units}.values()))[:MAX_NCS_UNITS]


def _by_survey(units: list[NcsUnit]) -> list[NcsUnit]:
    """조사 점수가 높은 능력단위를 앞에 놓는다. 조사가 있는 능력단위끼리만 자리를 바꾼다.

    조사가 없는 능력단위(DB엔지니어링 등)는 모델이 고른 자리에 둔다. 조사가 없다는 이유로 뒤로 밀지 않는다.
    """
    surveys = ncs_data().surveys
    ranked = iter(
        sorted((unit for unit in units if unit.code in surveys), key=lambda unit: -survey_score(surveys[unit.code]))
    )
    return [next(ranked) if unit.code in surveys else unit for unit in units]


def _apply_ncs(
    changes: list[FieldChange], ncs: NcsDraft, units: list[NcsUnit], counts: dict[str, int]
) -> tuple[list[FieldChange], list[NcsUnit], dict[str, int]]:
    """NCS 정의를 보고 쓴 목록을 바꿀 칸에 넣고, 보여 준 능력단위 중 근거로 쓴 것과 목록마다 넣은 항목 수를 돌려준다.

    쓰기로 한 목록만 정한 개수까지 넣는다. 목록이 비어 있으면 지금 공고의 목록을 지우지 않게 넣지 않는다.
    개수를 채우려고 같은 항목을 되풀이하면 하나만 남긴다. 보여 주지 않은 능력단위는 근거로 치지 않는다.
    """
    shown = {unit.code for unit in units}
    written: list[FieldChange] = []
    cited: dict[str, NcsUnit] = {}
    sizes: dict[str, int] = {}
    for name, label in NCS_FIELDS:
        if name not in counts:
            continue
        unique: dict[str, SourcedItem] = {}
        for item in getattr(ncs, name):
            if item.text.strip():
                unique.setdefault(_compact(item.text), item)
        items = list(unique.values())[: counts[name]]
        sizes[name] = len(items)
        if not items:
            continue
        written.append(FieldChange(field=label, text=None, items=[item.text for item in items]))
        for code in (code for item in items for code in item.sources):
            if (unit := unit_by_code(code.strip())) and unit.code in shown:
                cited.setdefault(unit.code, unit)
    rewritten = {change.field for change in written}
    kept = [change for change in changes if change.field not in rewritten]
    return kept + written, list(cited.values()), sizes


def _count_notes(plan: dict[str, int], counts: dict[str, int], written: dict[str, int]) -> list[str]:
    """요청보다 적게 쓴 목록을 알린다. 근거를 찾을 수 있는 만큼만 쓰게 해서, 적게 썼다고 다시 쓰게 하지 않는다."""
    notes = [
        f"{FIELD_LABELS[name]}은 {MAX_DRAFT_ITEMS}개까지 써요."
        for name, count in plan.items()
        if count > MAX_DRAFT_ITEMS and written.get(name)
    ]
    notes += [
        f"{FIELD_LABELS[name]}은 근거를 찾을 수 있는 {written[name]}개만 썼어요."
        for name, count in counts.items()
        if 0 < written.get(name, 0) < count
    ]
    return notes


def _draft(posting: PostingDraftContext, edit: _Edit, request: str) -> _Draft:
    content, changed = _apply(posting.content, _requested_facts(edit.changes, request))
    if edit.roles is not None and edit.roles != content.roles:
        content = content.model_copy(update={"roles": edit.roles})
        changed.append("roles")
    stages: list[StageDraft] | None = None
    unknown: list[str] = []
    if edit.stages is not None:
        current = {stage.name for stage in posting.stages}
        named = [(_tidy(stage.name), stage.type) for stage in edit.stages if _tidy(stage.name)]
        unknown = [name for name, kind in named if kind is None or _ambiguous(name, current, request)]
        icons = {stage.name: stage.icon for stage in posting.stages}
        requested_icons = {_tidy(stage.name): stage.icon for stage in edit.stages}
        proposed = [
            StageDraft(name=name, type=kind, icon=requested_icons.get(name) or icons.get(name))
            for name, kind in named
            if kind is not None
        ]
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
    채용 인원은 글에서 숫자를 읽고, 숫자가 없거나 한도를 넘으면 바꾸지 않는다.
    """
    updates: dict[str, str | list[str] | int] = {}
    for change in changes:
        name = LABEL_FIELDS[change.field]
        if name == "headcount":
            count = _headcount(change.text)
            if count is not None and count != content.headcount:
                updates[name] = count
            continue
        value: str | list[str] | None = change.text if name in TEXT_FIELDS else change.items
        if value is None:
            continue
        cleaned = _clean(value)
        if cleaned and cleaned != getattr(content, name):
            updates[name] = cleaned
    changed = [name for name in FIELD_LABELS if name in updates]
    return content.model_copy(update=updates), changed


def _requested_facts(changes: list[FieldChange], request: str) -> list[FieldChange]:
    """회사가 알려 주는 사실을 담는 칸(FACT_WORDS)은 요청에서 그 칸을 말했을 때만 바꾼다."""
    return [
        change
        for change in changes
        if (words := FACT_WORDS.get(LABEL_FIELDS[change.field])) is None or words.search(request)
    ]


def career_conflicts(before: PostingContent, after: PostingContent) -> list[str]:
    """전체 경력 조건을 바꿀 때 기존의 동일한 경력 문구가 남았는지 검사한다.

    기술별로 별도 지정한 경력은 자동 치환하지 않는다. 검사 실패는 모델에 전달해 수정안을 다시 검토한다.
    """
    if before.career == after.career:
        return []
    years = re.search(r"(\d+)\s*년\s*이상", before.career)
    wanted = re.search(r"(\d+)\s*년\s*이상", after.career)
    if not years or not wanted or years.group(1) == wanted.group(1):
        return []
    old = re.compile(r"경력\s*" + years.group(1) + r"\s*년\s*이상")
    return [
        f"{FIELD_LABELS[name]} {index + 1}번에 이전 경력 조건이 남아 있다: {line}. "
        f"새 경력 조건({after.career})과 맞추고 다른 내용은 유지한다"
        for name in ("qualifications", "preferred")
        for index, line in enumerate(getattr(after, name))
        if old.search(line) and any(old.search(previous) for previous in getattr(before, name))
    ]


def _headcount(text: str | None) -> int | None:
    """채용 인원 글에서 읽은 숫자 (예: "3", "3명", "세 명"). 1부터 MAX_HEADCOUNT까지만 받는다."""
    found = re.search(r"\d+|" + "|".join(_KOREAN_NUMBERS), text or "")
    if not found:
        return None
    count = _number(found.group())
    return count if 1 <= count <= MAX_HEADCOUNT else None


# 목록 항목 앞에 모델이 붙이는 기호와 번호 (예: "- ", "• ", "1. ")
_BULLET = re.compile(r"^(?:[-*•·▪●]|\d+[.)])\s+")


def _clean(value: str | list[str]) -> str | list[str]:
    if isinstance(value, str):
        return _tidy(value)
    return [cleaned for item in value if (cleaned := _tidy(_BULLET.sub("", item.strip())))]


def _tidy(text: str) -> str:
    """뜻이 바뀌지 않는 띄어쓰기만 고친다."""
    return _PARTICLE_SPACE.sub("", _NUMBER_SPACE.sub(r"\1\2", text)).strip()


def _result(draft: _Draft, edit: _Edit, locked: bool) -> RevisionResult:
    notes = list(edit.notes)
    if edit.cited and {name for name, _ in NCS_FIELDS} & set(draft.changed):
        notes.append("근거(NCS): " + ", ".join(f"{unit.subdivision} · {unit.name}" for unit in edit.cited))
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


def _ncs_prompt(
    posting: PostingDraftContext, writing_style: str, request: str, units: list[NcsUnit], counts: dict[str, int]
) -> str:
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
        *([NCS_ORDER_NOTE] if sum(unit.code in ncs_data().surveys for unit in units) >= 2 else []),
        *_unit_lines(units),
        *([_advanced_line(advanced, content.career)] if (advanced := _advanced_units(units)) else []),
        "",
        f"HR 요청: {request}",
        "",
        _ncs_task(counts),
    ]
    return "\n".join(lines)


def _ncs_task(counts: dict[str, int]) -> str:
    """쓸 목록과 개수. 요청을 읽고 정하는 일은 코드가 하고 모델에게는 정한 대로 알려 준다."""
    task = f"지금 할 일: {', '.join(f'{FIELD_LABELS[name]} {count}개' for name, count in counts.items())}를 쓴다."
    if skipped := [label for name, label in NCS_FIELDS if name not in counts]:
        task += f" {', '.join(skipped)}은 쓰지 않고 빈 목록으로 둔다."
    return task


def _unit_lines(units: list[NcsUnit]) -> list[str]:
    """능력단위마다 정의와, 세부 능력([요소 이름]) 아래 수행준거를 적는다. 글자 수 한도는 능력단위끼리 나눠 쓴다.

    요소 이름을 보여 줘야 모델이 한 능력단위를 두 목록에 쓸 때 서로 다른 세부 능력을 고를 수 있다.
    """
    share = NCS_DETAIL_CHARS // max(len(units), 1)
    lines = []
    for unit in units:
        lines.append(f"- {unit.code} {unit.name} (수준 {unit.level}): {unit.definition}")
        shown = _criteria_within(unit, share - len(unit.definition))
        for element in unit.elements:
            lines.append(f"  [{element.name}]")
            lines += [f"  · {criterion}" for criterion in element.criteria if criterion in shown]
    return lines


def _criteria_within(unit: NcsUnit, budget: int) -> set[str]:
    """글자 수 한도 안에서 보여 줄 수행준거. 요소마다 고루 고른다 (_spread_criteria)."""
    shown: set[str] = set()
    used = 0
    for criterion in _spread_criteria(unit):
        if used + len(criterion) > budget:
            break
        shown.add(criterion)
        used += len(criterion)
    return shown


def _advanced_line(units: list[NcsUnit], career: str) -> str:
    """수준이 높은 능력단위 줄. 신입이 지원하는 공고면 그 능력은 우대 사항에만 쓰라고 덧붙인다."""
    line = f"{ADVANCED_LABEL}: {', '.join(unit.name for unit in units)}"
    return f"{line} {JUNIOR_NOTE}" if _JUNIOR.search(career) else line


def _advanced_units(units: list[NcsUnit]) -> list[NcsUnit]:
    """보여 준 능력단위 중 NCS 수준이 가장 높은 것. 수준이 모두 같으면 없다."""
    levels = {unit.level for unit in units}
    return [unit for unit in units if unit.level == max(levels)] if len(levels) > 1 else []


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
        elif isinstance(value, int):
            lines.append(f"{label}: {value}명")
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
