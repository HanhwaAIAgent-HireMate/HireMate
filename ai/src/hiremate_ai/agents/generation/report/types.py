"""Report Agent 입출력 타입. backend의 ai.application.ReportInput, report.ReportContent를 그대로 옮긴다.

이 Agent만 쓰는 타입이지만 Agent 함수와 라우터가 같이 쓰므로 types.py에 둔다.
"""

from pydantic import BaseModel, Field

from hiremate_ai.contract import ContractModel, Finding


class ReportStage(ContractModel):
    """전형 하나의 인원 (ReportContent.ReportStage). backend가 집계한 값이다."""

    name: str
    target: int
    # pass는 파이썬 예약어라 필드 이름만 바꾸고 JSON 이름은 그대로 둔다
    passed: int = Field(alias="pass")
    fail: int


class FinalistInput(ContractModel):
    """최종 합격자 이름과 분석 근거, 전형 메모 (ReportInput.FinalistInput)."""

    name: str
    notable: list[Finding]
    memos: list[str]


class ReportInput(ContractModel):
    """리포트를 쓰는 데 필요한 확정 결과 (ai.application.ReportInput).

    undecided는 전형마다 결정하지 않아 불합격으로 확정된 인원이다.
    """

    title: str
    applicant_count: int
    stages: list[ReportStage]
    finalists: list[FinalistInput]
    undecided: list[int]


class Finalist(ContractModel):
    """최종 합격자와 판단 근거 (ReportContent.Finalist). sources는 근거의 출처다."""

    name: str
    reason: str
    sources: list[str]


class ReportContent(ContractModel):
    """최종 채용 리포트 (report.ReportContent). 채용 상태를 바꾸지 않는 요약 문서다."""

    summary: str
    applicant_count: int
    final_count: int
    stages: list[ReportStage]
    finalists: list[Finalist]
    notes: list[str]


class FinalistDraft(BaseModel):
    name: str = Field(description="자료에 적힌 최종 합격자 이름 그대로")
    reason: str = Field(description="분석 근거와 전형 메모에 있는 내용만으로 쓴 한두 문장")
    sources: list[str] = Field(
        description="reason에 쓴 근거의 출처. 분석 근거의 출처 그대로, 전형 메모를 썼으면 '전형 메모'"
    )


class ReportDraft(BaseModel):
    """모델이 쓰는 부분. 인원과 숫자는 코드가 넣으므로 여기에 없다."""

    summary: str = Field(description="최종 합격자들의 공통 강점을 한두 문장으로. 인원 수는 쓰지 않는다")
    finalists: list[FinalistDraft]
    notes: list[str] = Field(description="자료에서 보이는 특이사항이나 확인할 점. 없으면 빈 목록")
