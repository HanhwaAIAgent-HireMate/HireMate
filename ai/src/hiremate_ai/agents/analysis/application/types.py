"""Application Agent만 쓰는 타입.

- backend와 주고받는 계약: ScreeningRubric(posting.ScreeningRubric), ApplicationAnalysis(apply.ApplicationAnalysis).
  필드를 바꾸면 저장소 루트 contract/의 샘플도 고친다.
- 분석 결과 원본: ApplicationReview. ai.application_reviews에 그대로 저장하고, backend에 돌려주는 값은 여기서 만든다.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from hiremate_ai.contract import ContractModel, DocumentType


class RubricPreference(ContractModel):
    """우대사항 하나의 평가 기준 (posting.ScreeningRubric.Preference)."""

    text: str  # 공고의 우대사항 문장. 공고 본문의 preferred와 같은 글이어야 짝이 맞는다
    weight: int  # 1~5. 사람이 정한 값이고 Agent가 바꾸지 않는다
    ncs_unit_code: str  # 이 우대사항의 평가 조건을 담은 NCS 능력단위 (예: 2001020218_23v6)
    certificates: list[str]  # 이 능력과 관련된 자격증. 직무 적합도의 '자격증 · 학습' 항목에서 본다


class ScreeningRubric(ContractModel):
    """서류 평가 기준 (posting.ScreeningRubric). 공고 담당이 입력 화면을 만들기 전까지 backend 설정의 더미다."""

    company_id: UUID
    recruitment_id: UUID
    hire_count: int  # 선발 인원. AI 추천은 이 인원의 10배수까지다 (backend screening이 줄 세운다)
    preferred: list[RubricPreference]


class ApplicationAnalysis(ContractModel):
    """지원 접수 때 backend에 돌려주는 요약 (apply.ApplicationAnalysis)."""

    career_years: int | None  # 서류를 읽지 못하면 None, 신입은 0
    last_company: str | None
    document_score: int | None  # AI 적합도 점수 (0~100). 보류면 None
    passed: bool  # 자격요건을 75% 이상 채웠다
    held: bool  # 점수 보류 (서류를 읽지 못함)
    shortfalls: list[str]  # 채우지 못한 자격요건의 짧은 표시 (예: 신입)


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class Actor(StrEnum):
    SELF = "SELF"  # 본인이 직접 했다
    TEAM = "TEAM"  # 팀 · 조직의 성과다
    UNCLEAR = "UNCLEAR"


class Level(StrEnum):
    """NCS 평가 조건 하나의 판정. 0과 1만 쓴다."""

    MET = "MET"  # 서류에 그 일을 한 근거가 있다 (1)
    NONE = "NONE"  # 근거가 없다 (0)


class PreferenceStatus(StrEnum):
    SCORED = "SCORED"  # 평가 조건으로 점수를 매겼다
    UNRATED = "UNRATED"  # 평가 기준(가중치 · NCS)이 없어 점수에 넣지 않았다


class Quote(_Record):
    """원문에서 찾은 근거 문장. sentence는 원문 글자 그대로다."""

    document: DocumentType
    sentence: str


class Fact(_Record):
    kind: str  # EXPERIENCE, PROJECT, SKILL, CERTIFICATE, ACHIEVEMENT, ACTIVITY, EDUCATION
    statement: str
    actor: Actor
    quotes: list[Quote]
    supported: bool = True  # 검토에서 근거가 주장을 받쳐 주지 않으면 False


class Period(_Record):
    company: str
    role: str
    kind: str  # EMPLOYMENT, INTERN, FREELANCE, PROJECT, EDUCATION
    start: str  # YYYY-MM
    end: str | None  # 재직 중이면 None
    months: int
    quote: Quote


class QualificationResult(_Record):
    number: int  # Q 번호 (1부터)
    text: str
    met: bool
    evaluated: bool = True  # 차별 조건처럼 평가하지 않은 요건이면 False (충족률 계산에서 뺀다)
    shortfall: str | None = None
    reason: str
    quotes: list[Quote] = []


class CriterionResult(_Record):
    number: int  # C 번호 (1부터)
    content_no: str  # NCS 수행준거 번호 (능력단위요소-순서, 예: 1-2)
    content: str  # 수행준거 문장
    level: Level
    reason: str
    quotes: list[Quote] = []


class PreferenceResult(_Record):
    number: int  # P 번호 (1부터)
    text: str
    weight: int | None
    unit_code: str | None
    unit_name: str | None
    criteria: list[CriterionResult] = []
    status: PreferenceStatus
    score: float | None  # 만족한 평가 조건 수 ÷ 평가 조건 수 (0~1). 평가 기준이 없으면 None


class FitLine(_Record):
    """AI 적합도 점수의 한 항목. points는 모델이 매기고 코드가 0~max로 자른다."""

    key: str
    label: str
    points: int
    max: int
    reason: str
    quotes: list[Quote] = []


class Note(_Record):
    """카드에 보여 줄 한 줄과 출처."""

    text: str
    source: str


class ApplicationReview(_Record):
    """지원서 분석 한 번의 결과 원본."""

    version: str
    input_hash: str
    application_id: UUID
    readable: bool  # 제출 서류에서 글자를 읽었는가
    facts: list[Fact] = []
    periods: list[Period] = []
    career_years: int | None = None
    last_company: str | None = None
    qualifications: list[QualificationResult] = []
    passed: bool = False
    preferences: list[PreferenceResult] = []
    preference_points: float = 0  # 우대사항 · NCS 평가 조건 점수 (0~60)
    fit: list[FitLine] = []  # 직무 적합도 항목 (합 0~40)
    held: bool = False  # 서류를 읽지 못해 점수를 매기지 못했다
    holds: list[Note] = []
    document_score: int | None = None
    checks: list[Note] = []
