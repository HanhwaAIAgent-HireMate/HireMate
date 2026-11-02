"""리포트 설계서. Report Agent는 완성된 글이 아니라 어떤 부품을 어떤 자료로 그릴지를 낸다.

설계서는 섹션으로 나눈다: 한눈에 보기 → 영역마다 한 섹션 → (요청 관점) → 정리. 섹션마다 읽을 점 한 문장과 부품 1~3개다.
부품(블록) 종류는 화면과 PDF가 같이 그리는 정해진 목록이다. 숫자는 묶음의 지표 id · 값 key로만 가리키고,
코드(check.py)가 모든 참조와 문장을 검사한다. 화면과 PDF는 이 설계서와 묶음을 함께 받아 그린다.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class SpecModel(BaseModel):
    """설계서 부품의 공통 설정. JSON 이름은 contract와 같은 camelCase이고, 모델도 같은 이름으로 낸다.

    검사 · 기본 구성이 부품을 고쳐 만들 수 있게 frozen이 아니다.
    """

    model_config = ConfigDict(
        alias_generator=to_camel, validate_by_name=True, validate_by_alias=True, serialize_by_alias=True
    )


VISUAL_TYPES = frozenset(
    {
        "kpi",
        "bar",
        "stacked",
        "radar",
        "distribution",
        "donut",
        "cross",
        "share",
        "composition",
        "position",
        "rings",
        "matrix",
        "tally",
        "table",
    }
)
"""시각화 부품. 리포트마다 셋 이상 있어야 한다."""


class KpiBlock(SpecModel):
    type: Literal["kpi"] = "kpi"
    title: str
    caption: str = Field(description="이 지표들이 무엇을 보여 주는지 한 줄")
    metrics: list[str] = Field(description="묶음 지표 id 2~5개")


class BarBlock(SpecModel):
    type: Literal["bar"] = "bar"
    title: str
    caption: str = Field(description="막대가 무엇을 비교하는지 한 줄")
    keys: list[str] = Field(description="만점이 같은 숫자 값 key 1~6개. 총점과 영역 점수를 한 막대 묶음에 섞지 않는다")
    applicants: list[str] = Field(description="지원자번호 1~5명")
    reference: list[str] = Field(
        default=[], description="기준선으로 그릴 지표 id (예: 전체 평균). key가 하나이고 그 key를 집계한 지표만"
    )


class StackedBlock(SpecModel):
    type: Literal["stacked"] = "stacked"
    title: str
    caption: str = Field(description="막대 구성이 무엇을 보여 주는지 한 줄")
    keys: list[str] = Field(
        description="합치면 총점이 되는 영역 점수 key 2~6개 (예: document.qualification, document.preference)"
    )
    applicants: list[str] = Field(description="지원자번호 1~5명. 지원자마다 막대 하나를 영역 점수로 쌓는다")


class RadarBlock(SpecModel):
    type: Literal["radar"] = "radar"
    title: str
    caption: str = Field(description="영역별 모양이 무엇을 보여 주는지 한 줄")
    keys: list[str] = Field(description="같은 만점의 숫자 값 key 3~8개 (예: 평가 영역 점수)")
    applicants: list[str] = Field(description="지원자번호 1~5명")


class DistributionBlock(SpecModel):
    type: Literal["distribution"] = "distribution"
    title: str
    caption: str = Field(description="분포에서 읽을 점 한 줄. highlight가 있으면 표시한 까닭도")
    key: str = Field(description="전형 전체 지원자의 숫자 값 key 하나 (예: document.total)")
    highlight: list[str] = Field(default=[], description="분포 위에 표시할 지원자번호 5명까지. 없으면 빈 목록")
    split: str | None = Field(
        default=None, description="막대를 나눠 칠할 판정 key (예: document.decision이면 합격 · 불합격). 없으면 비운다"
    )
    reference: list[str] = Field(
        default=[], description="기준선으로 그릴 지표 id (예: 평균 총점). 그 key를 집계한 지표만"
    )


class DonutBlock(SpecModel):
    type: Literal["donut"] = "donut"
    title: str
    caption: str = Field(description="구성에서 읽을 점 한 줄")
    metrics: list[str] = Field(
        description="합치면 전체가 되는 같은 단위 지표 id 2~5개 (예: 자격요건 충족 · 미달 · 판단 보류)"
    )


class CrossBlock(SpecModel):
    type: Literal["cross"] = "cross"
    title: str
    caption: str = Field(description="교차표에서 읽을 점 한 줄")
    row_key: str = Field(description="행 판정 key (예: document.ai_pick)")
    col_key: str = Field(description="열 판정 key (예: document.decision). 범위 전체 지원자의 교차 인원을 센다")


class ShareBlock(SpecModel):
    type: Literal["share"] = "share"
    title: str
    caption: str = Field(description="그룹과 전체의 차이에서 읽을 점 한 줄")
    keys: list[str] = Field(description="있음 · 충족을 세는 판정 key 2~8개 (예: document.skill.*)")
    group_key: str = Field(description="그룹을 나누는 판정 key (예: document.decision)")
    group_value: str = Field(
        description="그룹 값 (예: PASS). 그룹과 전체에서 각 key가 있음 · 충족인 비율을 나란히 그린다"
    )


class CompositionRow(SpecModel):
    label: str = Field(description="막대 이름 (예: 전체, 합격자)")
    metrics: list[str] = Field(description="합치면 이 막대 전체가 되는 지표 id. 행마다 같은 구간 순서")


class CompositionBlock(SpecModel):
    type: Literal["composition"] = "composition"
    title: str
    caption: str = Field(description="구성 차이에서 읽을 점 한 줄")
    rows: list[CompositionRow] = Field(description="100%로 쌓은 막대 2~4개 (예: 전체 · 합격자의 경력 구간)")


class PositionBlock(SpecModel):
    type: Literal["position"] = "position"
    title: str
    caption: str = Field(description="위치에서 읽을 점 한 줄")
    keys: list[str] = Field(description="숫자 값 key 2~6개. 칸마다 전형 전체 지원자 안에서 상위 몇 %인지 그린다")
    applicants: list[str] = Field(description="지원자번호 1~5명")


class RingView(SpecModel):
    label: str = Field(description="관점 이름 (예: 자격요건, 협업)")
    keys: list[str] = Field(
        description="만점이 있는 숫자 key 하나(점수 / 만점 %), 또는 판정 key 1개 이상(충족 항목 비율 %)"
    )


class RingsBlock(SpecModel):
    type: Literal["rings"] = "rings"
    title: str
    caption: str = Field(description="관점별 비율에서 읽을 점 한 줄")
    views: list[RingView] = Field(
        description="관점 2~6개. 영역 점수면 지원자별 점수 표, 판정이면 관점별 충족 항목 칸 표로 그린다"
    )
    applicants: list[str] = Field(description="지원자번호 2~5명")


class MatrixBlock(SpecModel):
    type: Literal["matrix"] = "matrix"
    title: str
    caption: str = Field(description="판정 칸이 무엇을 보여 주는지 한 줄")
    keys: list[str] = Field(description="판정 값 key 2개 이상 (예: document.criterion.Q-01)")
    applicants: list[str] = Field(description="지원자번호")


class TallyBlock(SpecModel):
    type: Literal["tally"] = "tally"
    title: str
    caption: str = Field(description="판정 비율이 무엇을 보여 주는지 한 줄")
    keys: list[str] = Field(description="판정 값 key 2개 이상")
    applicants: list[str] = Field(
        default=[], description="지원자번호. 비우면 범위 전체(비교면 비교 대상, 전형 결과면 전형 전체)"
    )
    by: Literal["key", "applicant"] = Field(
        description="key면 항목마다(그 항목의 충족 비율), applicant면 지원자마다(그 지원자의 판정 구성) 막대 하나"
    )


class TableBlock(SpecModel):
    type: Literal["table"] = "table"
    title: str
    caption: str = Field(description="표가 무엇을 정리하는지 한 줄")
    keys: list[str] = Field(description="값 key. 숫자와 판정을 섞어도 된다")
    applicants: list[str] = Field(description="지원자번호")


class EvidenceItem(SpecModel):
    """근거 항목 하나. 화면은 키워드 요약을 먼저 보여 주고, 그 아래 근거 id의 AI 분석과 원문을 보여 준다."""

    applicant: str = Field(description="지원자번호")
    keywords: list[str] = Field(
        description="확인한 점의 키워드 요약 1~4개. 짧은 명사구 (예: 'Java 3년 이상', 'Spring Boot REST API'). "
        "근거가 없으면 확인할 점 (예: '협업 경험')"
    )
    text: str = Field(default="", description="근거가 있으면 빈 문자열. 근거가 없을 때만 '...은 확인되지 않았어요'")
    evidence: list[str] = Field(description="근거 id. 확인되지 않았다는 항목만 비운다")


class EvidenceBlock(SpecModel):
    type: Literal["evidence"] = "evidence"
    title: str
    items: list[EvidenceItem]


class TextBlock(SpecModel):
    type: Literal["text"] = "text"
    title: str
    text: str = Field(description="판단이 들어간 짧은 단락")
    evidence: list[str] = Field(description="이 단락의 근거 id 1개 이상")


Block = Annotated[
    KpiBlock
    | BarBlock
    | StackedBlock
    | RadarBlock
    | DistributionBlock
    | DonutBlock
    | CrossBlock
    | ShareBlock
    | CompositionBlock
    | PositionBlock
    | RingsBlock
    | MatrixBlock
    | TallyBlock
    | TableBlock
    | EvidenceBlock
    | TextBlock,
    Field(discriminator="type"),
]


class Section(SpecModel):
    title: str
    area: str | None = Field(
        default=None, description="영역 섹션이면 묶음 영역 id. 한눈에 보기 · 요청 관점 · 정리 섹션은 비운다"
    )
    takeaway: str = Field(description="이 섹션에서 읽을 점 한 문장")
    blocks: list[Block] = Field(description="부품 1~3개")


class Split(SpecModel):
    """비교 대상끼리 판정이 갈린 항목 하나와 그 이유."""

    key: str = Field(
        description="판정이 갈린 항목 판정 key (예: document.criterion.Q-03). get_overview의 '판정이 갈린 항목'만"
    )
    text: str = Field(
        description="갈린 이유 한 문장. 근거의 세부(충족한 부분 · 못 채운 부분 · 확인 필요한 부분 · 역할)로 "
        "누가 무엇이 달랐는지 쓴다. 지원자는 지원자번호, 항목은 짧은 이름으로 쓴다"
    )
    evidence: list[str] = Field(description="그 문장의 근거 id. get_evidence로 받은 것만")


class ReportSpec(SpecModel):
    """리포트 설계서. summary는 두세 문장 요약이고, 지원자는 지원자번호로만 쓴다."""

    title: str
    summary: str = Field(description="리포트 전체 요약 두세 문장. 숫자는 묶음에 있는 값만 쓴다")
    skills: list[str] = Field(default=[], description="읽은 스킬 이름")
    sections: list[Section] = Field(description="섹션 2~7개. 영역마다 섹션 하나, 시각화 부품은 모두 합쳐 셋 이상")
    perspectives: list[RingView] = Field(
        default=[],
        description="비교 리포트만 채운다. 항목 판정 key를 관점 3~6개로 묶고, 관점마다 항목 2~3개를 넣는다. "
        "이름은 항목 내용을 보고 짧게 짓는다 (예: 협업, 연동 · API, 품질 · 테스트, 데이터 설계). "
        "sections에 관점 rings가 없으면 코드가 이 묶음으로 관점별 항목 충족 표를 만든다. 전형 · 최종 리포트는 []",
    )
    splits: list[Split] = Field(
        default=[],
        description="비교 리포트만 채운다. 판정이 갈린 항목마다 하나씩 갈린 이유를 쓴다 (최대 6개). "
        "전형 · 최종 리포트는 []",
    )

    def all_blocks(self) -> list[Block]:
        return [block for section in self.sections for block in section.blocks]
