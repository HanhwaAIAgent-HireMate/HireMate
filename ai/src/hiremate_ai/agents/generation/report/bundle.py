"""Report Agent가 읽는 데이터 묶음. backend가 리포트 작업을 넣을 때 범위 안의 자료를 한 번에 넘긴다.

숫자는 모두 backend가 계산한 값이고, 모델은 id로 가리키기만 한다. 지원자는 지원자번호(예: A-0012)로만 나오고
이름은 없다. 화면에서 이름을 붙이는 일은 backend가 한다.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from hiremate_ai.contract import ContractModel, StageType


class ReportKind(StrEnum):
    """리포트 종류. STAGE는 결과 확정 때 만드는 전형 결과 리포트, COMPARE는 Chat에서 요청한 지원자 비교다."""

    STAGE = "STAGE"
    COMPARE = "COMPARE"
    FINAL = "FINAL"


class Strength(StrEnum):
    """근거 원문의 강도. QUANT는 성과를 숫자와 단위로 적은 문장, CLAIM은 한 일만 적은 문장이다 (strength.py)."""

    QUANT = "QUANT"
    CLAIM = "CLAIM"


_STRENGTH_LABELS = {Strength.QUANT: "정량", Strength.CLAIM: "서술"}


class BundleStage(ContractModel):
    """범위 안의 전형 하나. confirmed_at이 없으면 진행 중인 전형이라 as_of 기준 기록이다."""

    stage_id: UUID
    name: str
    type: StageType
    confirmed_at: datetime | None


class BundleApplicant(ContractModel):
    """대상 지원자. number는 채용 안에서 모든 전형에 같은 지원자번호다 (A-{지원 번호}).

    application_id는 ai가 저장한 분석 결과를 찾는 열쇠다. Report Agent 도구에는 보이지 않는다.
    """

    number: str
    application_id: UUID | None = None
    career_years: int | None
    last_company: str | None


class Metric(ContractModel):
    """backend가 집계한 지표 하나 (인원, 통과율, 평균 등). 지표 칸에 쓴다."""

    id: str
    stage_id: UUID | None
    label: str
    value: float
    unit: str  # 예: "명", "%", "점"
    key: str | None = None  # 이 지표가 집계한 값 key (예: 평균 총점은 document.total). 막대의 기준선으로 쓴다
    group: str | None = None  # 같은 group 지표를 합치면 전체가 된다 (예: 경력 구간별 인원). 도넛 · 구성 막대 조각이다


class Fact(ContractModel):
    """지원자 한 명의 값 하나. key는 '<전형 종류>.<항목>' 꼴이다 (예: document.total, document.criterion.Q-01).

    value가 숫자면 점수, 글이면 판정(MET · PARTIAL · NOT_MET · UNKNOWN, 면접 CONFIRMED · NOT_CONFIRMED 등)이다.
    """

    id: str
    applicant: str
    stage_id: UUID
    key: str
    label: str
    value: float | str
    max: float | None = None


class Evidence(ContractModel):
    """근거 하나. text는 분석 Agent의 판단이고, quote는 그 판단의 원문 문장(글자 그대로)이다. 둘을 섞지 않는다.

    agent는 그 근거를 만든 분석 Agent, source는 원문의 출처(이력서 등)다.
    label은 근거가 받치는 항목 이름(서류 평가 항목, 강점 · 확인할 점), verdict는 그 항목의 판정 코드다.
    strength는 원문의 강도(정량 · 서술)이고, 원문이 없으면 비어 있다.
    detail · role은 서류 분석의 판정 세부(충족한 부분 · 못 채운 부분 · 확인 필요한 부분 · 역할)로, 모델에게만 보여 주고
    backend로 돌려보내지 않는다 (exclude). 판정이 갈린 이유를 쓰고 서류 Agent에게 확인을 맡길 근거를 고르는 데 쓴다.
    """

    id: str
    applicant: str
    stage_id: UUID
    agent: str  # application · assessment · interview
    text: str
    source: str
    quote: str | None = None
    label: str | None = None
    verdict: str | None = None
    strength: Strength | None = None
    detail: str | None = Field(default=None, exclude=True)
    role: str | None = Field(default=None, exclude=True)  # SELF · TEAM · UNCLEAR (서류 분석의 Actor)

    def line(self) -> str:
        """모델에게 보여 줄 한 줄. 판단과 원문을 나눠 적고, 원문에 정량 · 서술을, 끝에 판정 세부를 붙인다."""
        label = f"{self.label}: " if self.label else ""
        kind = f"({_STRENGTH_LABELS[self.strength]})" if self.strength else ""
        quote = f' / 원문{kind}: "{self.quote}"' if self.quote else ""
        detail = f" / 세부: {self.detail}" if self.detail else ""
        return f"{label}{self.text}{quote}{detail} (출처: {self.source})"


class Area(ContractModel):
    """현재 전형의 평가 영역 하나 (서류면 자격요건 · 우대사항, 평가면 평가 영역). 리포트는 영역마다 섹션을 하나 둔다."""

    id: str
    label: str
    score_key: str | None  # 영역 점수 값 key. 없으면 판정만 있는 영역이다
    keys: list[str]  # 영역의 항목 값 key (판정)


class ReportBundle(ContractModel):
    """리포트 하나를 만드는 데 필요한 자료 (ai.application.ReportBundle).

    targets는 COMPARE의 비교 대상이고 STAGE · FINAL이면 빈 목록이다. focus는 요청에서 뽑은 관점(예: 협업)이다.
    total_key는 현재 전형 총점 값 key, areas는 현재 전형의 평가 영역이다.
    """

    kind: ReportKind
    company_id: UUID
    recruitment_id: UUID
    stage_id: UUID
    title: str
    as_of: datetime
    focus: str
    brief: bool  # 요청이 '간략히'면 요약과 한눈에 보기만 짧게 만든다
    stages: list[BundleStage]
    applicants: list[BundleApplicant]
    targets: list[str]
    total_key: str | None
    areas: list[Area]
    metrics: list[Metric]
    facts: list[Fact]
    evidence: list[Evidence]

    def stage(self, stage_id: UUID) -> BundleStage | None:
        return next((stage for stage in self.stages if stage.stage_id == stage_id), None)

    @property
    def current(self) -> BundleStage:
        stage = self.stage(self.stage_id)
        if stage is None:
            raise ValueError("stages에 현재 전형이 없다")
        return stage
