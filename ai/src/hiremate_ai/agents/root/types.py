"""Root Agent만 쓰는 계약 타입. backend `ai.application` · `screening`의 Java 레코드를 그대로 옮긴다.

필드를 바꾸면 저장소 루트 contract/의 ChatContext.json · ChatPlan.json도 고친다.
"""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from hiremate_ai.contract import (
    AnalysisStatus,
    ApplicantDocument,
    CompanyProfile,
    ContractModel,
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
    document_score: int | None = None  # 서류 전형의 AI 적합도 점수. 다른 전형이면 null


class QuestionSource(StrEnum):
    """면접 질문을 만든 쪽 (interview.QuestionSource)."""

    AI = "AI"
    MANUAL = "MANUAL"


class InterviewSchedule(ContractModel):
    """면접 일정 (InterviewView.Schedule)."""

    scheduled_at: datetime | None
    interviewers: str


class InterviewQuestion(ContractModel):
    """면접 질문 하나와 기록한 답변 (InterviewView.Question). 답변이 없으면 빈 문자열이다."""

    question_id: UUID
    text: str
    source: QuestionSource
    answer: str


class PreviousInterview(ContractModel):
    """이전 면접 전형의 질문과 답변 (InterviewView.PreviousInterview)."""

    stage_id: UUID
    stage_name: str
    schedule: InterviewSchedule | None
    questions: list[InterviewQuestion]


class InterviewView(ContractModel):
    """면접 전형 지원자 카드의 면접 기록 (interview.InterviewView)."""

    application_id: UUID
    schedule: InterviewSchedule | None
    questions: list[InterviewQuestion]
    previous: list[PreviousInterview]


class ChatContext(ContractModel):
    """Root Agent가 받는 요청 범위: 현재 채용 · 전형 + 대상(@멘션 · 체크) + 질문 (ai.application.ChatContext)."""

    stage_id: UUID
    recruitment_id: UUID
    thread_id: str  # 대화방 id. backend가 기업 · 전형 · 담당자로 만든다. 끝난 전형이면 비어 있다(기억하지 않는다)
    stage_name: str
    selectable: bool  # 선택 지원자를 바꿀 수 있는 전형(진행 중)인가. 결과를 확정한 전형이면 false
    stage_type: StageType
    previous_types: list[StageType]
    candidates: list[CandidateRow]
    documents: dict[UUID, list[ApplicantDocument]]
    document_scores: dict[UUID, int]
    interviews: dict[UUID, InterviewView]  # 면접 전형일 때만 채워진다
    mentions: list[UUID]
    checked: list[UUID]
    company: CompanyProfile
    posting: PostingContent
    message: str


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


class ChatHistoryTurn(ContractModel):
    """대화방의 지난 턴 하나 (ai.application.ChatHistoryTurn). 화면이 대화 기록을 다시 보여 줄 때 쓴다.

    plan.message의 {count}는 backend가 대상 수로, {total}은 그때 전형 인원(total)으로 바꾼다.
    """

    message: str
    plan: ChatPlan
    total: int
