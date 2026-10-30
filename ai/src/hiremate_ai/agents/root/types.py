"""Root Agent만 쓰는 계약 타입. backend `ai.application` · `screening`의 Java 레코드를 그대로 옮긴다.

필드를 바꾸면 저장소 루트 contract/의 ChatContext.json · ChatPlan.json도 고친다.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import model_validator

from hiremate_ai.contract import (
    AnalysisStatus,
    ApplicantDocument,
    CompanyProfile,
    ContractModel,
    InterviewerMemo,
    InterviewView,
    PostingContent,
    StageType,
)


class Decision(StrEnum):
    """HR 결정 (screening.Decision)."""

    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"


class SelectionMode(StrEnum):
    """찾기 결과의 반영 방식: 찾아줘는 교체, 추가해줘는 추가, 그중은 좁히기 (screening.SelectionMode)."""

    REPLACE = "REPLACE"
    ADD = "ADD"
    NARROW = "NARROW"


class Intent(StrEnum):
    """요청 유형: 지원자 찾기 · 분석과 생성 · 선택 지원자 편집 · 되묻기 · 차단 (ChatPlan.Intent)."""

    FIND = "FIND"
    ANSWER = "ANSWER"
    EDIT = "EDIT"
    CLARIFY = "CLARIFY"
    BLOCKED = "BLOCKED"


class EditAction(StrEnum):
    """선택 지원자 편집 명령 (ChatPlan.EditAction). 실행은 backend가 대상과 권한을 검증한 뒤 한다."""

    ADD = "ADD"
    REMOVE = "REMOVE"
    CLEAR = "CLEAR"
    RESTORE = "RESTORE"


class CandidateRow(ContractModel):
    """전형 리스트의 지원자 한 명 (screening.CandidateRow). score는 평가 전형 점수다."""

    application_id: UUID
    name: str
    career_years: int | None
    last_company: str | None
    decision: Decision
    selected: bool
    ai_selected: bool
    above_line: bool
    score: float | None
    analysis_status: AnalysisStatus
    held: bool = False  # 서류 점수 보류
    shortfalls: list[str] = []  # 채우지 못한 자격요건의 짧은 표시
    document_score: float | None = None  # 서류 전형의 총점. 다른 전형이면 null
    document_score_low: float | None = None  # 확인 필요를 0점으로 넣어 계산한 서류 전형 총점 (보류 점수)
    qualification_score: float | None = None  # 서류 전형의 자격요건 점수
    qualification_max: int = 0
    preference_score: float | None = None  # 서류 전형의 우대사항 점수
    preference_max: int = 0


class StageStatus(StrEnum):
    """전형 진행 상태 (recruit.StageStatus). 결과를 확정하면 CONFIRMED(안내 단계), 전형을 종료하면 DONE이다."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"
    DONE = "DONE"


class ChatStage(ContractModel):
    """채용의 전형 하나 (ChatContext.Stage)."""

    id: UUID
    name: str
    type: StageType
    status: StageStatus


class AssessmentScores(ContractModel):
    """평가 전형 결과 한 명분 (ai.application.ChatContext.Assessment). 점수 · 등급은 backend가 저장한 값 그대로다.

    areas는 영역 이름(예: 의사소통능력)을 키로 쓰고, 점수가 없는 영역은 null이다.
    """

    areas: dict[str, float | None]
    grade: str | None


class ChatAsker(ContractModel):
    """질문한 담당자. 탭 대화방은 같은 기업 담당자가 함께 써서 턴마다 남긴다."""

    member_id: UUID
    name: str


class ChatContext(ContractModel):
    """Root Agent가 받는 요청 범위: 현재 채용 · 전형 + 대상(@멘션 · 체크) + 질문 (ai.application.ChatContext)."""

    stage_id: UUID
    recruitment_id: UUID
    thread_id: str  # 대화방 id. backend가 기업 · 전형 · 탭으로 만든다. 비어 있으면(Studio, 평가) 기억하지 않는다
    stage_name: str
    selectable: bool  # 선택 지원자를 바꿀 수 있는 전형(진행 중)인가. 결과를 확정한 전형이면 false
    stage_type: StageType
    stages: list[ChatStage]  # 채용의 전형 전체, 전형 순서대로. 현재 전형도 들어 있다
    candidates: list[CandidateRow]
    documents: dict[UUID, list[ApplicantDocument]]
    document_scores: dict[UUID, float]
    interviews: dict[UUID, InterviewView]  # 면접 전형일 때만 채워진다
    mentions: list[UUID]
    checked: list[UUID]
    company: CompanyProfile
    posting: PostingContent
    message: str

    asker: ChatAsker | None = None  # 질문한 담당자. Studio와 평가에는 없다
    interviewer_memos: dict[UUID, list[InterviewerMemo]] = {}
    assessments: dict[UUID, AssessmentScores] = {}  # 현재 평가 전형의 영역 점수 · 등급. 평가 전형일 때만 채워진다

    @model_validator(mode="after")
    def _has_current_stage(self) -> Self:
        if all(stage.id != self.stage_id for stage in self.stages):
            raise ValueError("stages에 현재 전형이 없다")
        return self

    @property
    def stage_index(self) -> int:
        """현재 전형이 stages에서 몇 번째인가 (0부터)."""
        return next(index for index, stage in enumerate(self.stages) if stage.id == self.stage_id)

    @property
    def stage_status(self) -> StageStatus:
        return self.stages[self.stage_index].status

    @property
    def previous_types(self) -> list[StageType]:
        """현재 전형 앞에 있는 전형의 종류."""
        return [stage.type for stage in self.stages[: self.stage_index]]


class ChatItem(ContractModel):
    """답변의 한 줄 (ai.application.ChatItem). status는 OK(근거 충분), CHECK(확인 필요), 없으면 None."""

    application_id: UUID | None
    label: str
    text: str
    status: str | None


class ChatStatus(ContractModel):
    """처리 단계 문구 (ai.application.ChatStatus). Root plan SSE의 status 이벤트 data다. 문구는 코드 상수다."""

    text: str


class ChatPlan(ContractModel):
    """Root Agent의 실행 계획 (ai.application.ChatPlan). 선택 지원자 변경은 명령(동작, 대상)으로만 담는다.

    message의 {count}는 실제로 반영된 인원, {total}은 전형 전체 인원으로 backend가 바꾼다.
    """

    intent: Intent
    mode: SelectionMode | None
    edit: EditAction | None
    targets: list[UUID]
    message: str
    items: list[ChatItem]
    sources: list[str]
    agents: list[str]
    question_targets: list[UUID]
    question_focus: dict[UUID, str]  # 지원자별로 Interview Agent에 넘길 확인할 점
    question_memos: dict[UUID, InterviewerMemo] = {}  # 명시적으로 요청해 원문을 확인한 메모만 전달
    question_replace: bool = False  # 만들기 전에 답변 없는 AI 질문을 지운다

    @classmethod
    def answer(
        cls,
        intent: Intent,
        message: str,
        items: Sequence[ChatItem] = (),
        sources: Sequence[str] = (),
        agents: Sequence[str] = (),
    ) -> "ChatPlan":
        """선택 지원자를 바꾸지 않는 답. backend ChatPlan.answer와 같다."""
        return cls(
            intent=intent,
            mode=None,
            edit=None,
            targets=[],
            message=message,
            items=list(items),
            sources=list(sources),
            agents=list(agents),
            question_targets=[],
            question_focus={},
        )


class ChatApplied(ContractModel):
    """업무 서버가 실제 반영한 응답. 원래 질문과 계획이 일치하는 기록만 보정한다."""

    thread_id: str
    message: str
    previous: ChatPlan
    plan: ChatPlan


class ChatHistoryTurn(ContractModel):
    """대화방의 지난 턴 하나 (ai.application.ChatHistoryTurn). 화면이 대화 기록을 다시 보여 줄 때 쓴다.

    plan.message의 {count}는 backend가 대상 수로, {total}은 그때 전형 인원(total)으로 바꾼다.
    mentions는 그때 멘션한 지원자, steps는 그때 낸 단계 문구, seconds는 걸린 시간, asker는 질문한 담당자다.
    예전 턴에는 없다.
    """

    message: str
    plan: ChatPlan
    total: int
    mentions: list[UUID] = []
    steps: list[str] = []
    seconds: int | None = None
    asker: ChatAsker | None = None
