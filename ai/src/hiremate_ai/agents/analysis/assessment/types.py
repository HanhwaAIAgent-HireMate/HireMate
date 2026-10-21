"""Assessment Agent 입출력 타입. backend의 ai.application.AssessmentInput을 그대로 옮긴다.

이 Agent만 쓰는 타입이지만 Agent 함수, 검사, 라우터가 같이 쓰므로 types.py에 둔다.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hiremate_ai.contract import ContractModel
from hiremate_ai.db.profile import ProfileStatus
from hiremate_ai.db.profile_store import NewItem


class Submission(ContractModel):
    """평가 전형에 올린 파일(결과 리포트나 과제 제출물)과 추출한 본문. 글자를 읽지 못한 PDF면 text가 비어 있다."""

    file_name: str
    text: str


class AssessmentInput(ContractModel):
    """지원자 한 명의 평가 결과 (ai.application.AssessmentInput).

    점수 · 등급은 backend가 저장한 값 그대로다. areas는 영역 이름을 키로 쓰고, 점수가 없는 영역은 null이다.
    url은 주소만 받는다. 본문을 가져오지 않는다 (내부망 주소 차단을 정한 뒤 다음 단계에서 한다).
    """

    company_id: UUID
    recruitment_id: UUID
    stage_id: UUID
    application_id: UUID
    stage_name: str
    total: float | None
    areas: dict[str, float | None]
    grade: str | None
    submission: Submission | None
    url: str | None
    note: str | None


class FindingDraft(BaseModel):
    """모델이 쓰는 강점 · 약점 한 줄."""

    kind: Literal["STRENGTH", "WEAKNESS"] = Field(description="강점이면 STRENGTH, 약점이나 확인할 점이면 WEAKNESS")
    content: str = Field(description="자료에서 드러난 강점이나 약점을 한 문장으로")
    evidence: str = Field(description="content를 받치는 자료 원문 한 문장. 글자 그대로 옮긴다")
    source: str = Field(description="evidence가 있는 자료의 label 그대로")


class AssessmentDraft(BaseModel):
    """모델이 쓰는 부분. 점수 · 등급은 코드가 다루므로 여기에 없다."""

    findings: list[FindingDraft] = Field(description="자료에서 드러난 강점과 약점. 근거가 없으면 빈 목록")


class AssessmentAnalysis(BaseModel):
    """Assessment Agent가 돌려주는 결과. items는 그대로 프로필에 저장할 수 있다.

    status: 강점 · 약점을 뽑았으면 DONE, 볼 자료가 없으면 CHECK, 모델이 끝내 형식에 맞는 답을 내지 못하면 FAILED.
    dropped: 근거를 원문에서 찾지 못하는 등 검사를 끝내 통과하지 못해 버린 항목 수.
    """

    status: ProfileStatus
    items: list[NewItem]
    dropped: int
