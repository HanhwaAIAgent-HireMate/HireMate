"""Interview Agent(답변 분석) 입출력 타입. backend의 ai.application.InterviewAnalysisInput을 그대로 옮긴다.

이 Agent만 쓰는 타입이지만 Agent 함수, 검사, 라우터가 같이 쓰므로 types.py에 둔다.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hiremate_ai.contract import ContractModel
from hiremate_ai.db.profile import ProfileStatus
from hiremate_ai.db.profile_store import NewItem


class AnsweredQuestion(ContractModel):
    """면접 질문 하나와 면접관이 기록한 답변. 답변을 기록하지 않았으면 answer가 빈 문자열이다."""

    text: str
    answer: str


class PreviousInterview(ContractModel):
    """같은 지원자의 이전 면접 기록. 이번 답변과 비교할 맥락으로만 쓴다."""

    stage_name: str
    questions: list[AnsweredQuestion]


class InterviewAnalysisInput(ContractModel):
    """지원자 한 명의 면접 전형 기록 (ai.application.InterviewAnalysisInput).

    questions는 이번 면접 전형의 질문과 답변이다. previous는 이전 면접 전형의 기록이다.
    """

    company_id: UUID
    recruitment_id: UUID
    stage_id: UUID
    application_id: UUID
    stage_name: str
    questions: list[AnsweredQuestion]
    previous: list[PreviousInterview]


class FindingDraft(BaseModel):
    """모델이 쓰는 면접 기록 정리 한 줄."""

    kind: Literal["CONFIRMED", "UNCONFIRMED", "CONFLICT"] = Field(
        description="답변으로 확인된 점이면 CONFIRMED, 답변이 모호해 아직 확인되지 않은 점이면 UNCONFIRMED, "
        "질문의 전제(서류 · 평가 내용)나 이전 면접 답변과 어긋나는 점이면 CONFLICT"
    )
    content: str = Field(description="확인된 점 · 확인되지 않은 점 · 어긋나는 점을 한 문장으로")
    evidence: str = Field(description="content를 받치는 이번 면접 답변 원문 한 문장. 글자 그대로 옮긴다")


class InterviewDraft(BaseModel):
    """모델이 쓰는 부분. 답변을 기록하지 않은 질문은 코드가 다루므로 여기에 없다."""

    findings: list[FindingDraft] = Field(description="답변에서 정리한 점. 근거가 없으면 빈 목록")


class InterviewAnalysis(BaseModel):
    """Interview Agent(답변 분석)가 돌려주는 결과. items는 그대로 프로필에 저장할 수 있다.

    status: 정리했으면 DONE, 기록한 답변이 없으면 CHECK, 모델이 끝내 형식에 맞는 답을 내지 못하면 FAILED.
    dropped: 근거를 답변 원문에서 찾지 못하는 등 검사를 끝내 통과하지 못해 버린 항목 수.
    """

    status: ProfileStatus
    items: list[NewItem]
    dropped: int
