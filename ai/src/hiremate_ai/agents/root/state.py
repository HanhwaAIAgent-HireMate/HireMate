"""Root 그래프의 상태. 대화방에 남는 값과 요청 하나 동안만 쓰고 저장하지 않는 값(run)을 나눈다."""

from dataclasses import dataclass, field
from typing import Annotated, TypedDict

from langgraph.channels.untracked_value import UntrackedValue

from hiremate_ai.agents.root.analysis import AnalysisReply, AnalysisRun
from hiremate_ai.agents.root.plan import RootPlan
from hiremate_ai.agents.root.turns import Turn
from hiremate_ai.agents.root.types import CandidateRow, ChatPlan, SelectionMode
from hiremate_ai.llm.chat import ModelCallBudget


@dataclass
class RootRun:
    """요청 하나 동안의 값. 노드 사이로 넘기지만 체크포인터에는 남기지 않는다 (근거 번호표에 원문 인용이 있다)."""

    budget: ModelCallBudget
    plan: RootPlan | None = None
    rows: list[CandidateRow] = field(default_factory=list)
    analysis: AnalysisRun | None = None
    reply: AnalysisReply | None = None


class RootInput(TypedDict, total=False):
    """그래프 입력. 턴마다 비우는 값만 받는다. 요청 하나 동안의 값(run)은 입력으로 받지 않는다."""

    plan: ChatPlan | None
    kind: str
    mode: SelectionMode | None
    steps: list[str]


class RootOutput(TypedDict, total=False):
    """그래프 출력. 대화방에 남는 값이고 run은 내보내지 않는다."""

    plan: ChatPlan | None
    kind: str
    mode: SelectionMode | None
    turns: list[Turn]
    result: list[str] | None
    subject: list[str]
    steps: list[str]
    started: float


class RootState(TypedDict, total=False):
    plan: ChatPlan | None  # 검증을 마친 계획. 정해지면 record로 간다
    kind: str  # 턴 기록의 종류 (FIND, EDIT, ANSWER, 실패면 빈 값)
    mode: SelectionMode | None
    turns: list[Turn]
    result: list[str] | None
    subject: list[str]
    steps: list[str]  # 이번 턴에 낸 단계 문구
    started: float  # 이번 턴을 시작한 시각 (time.monotonic)
    run: Annotated[RootRun | None, UntrackedValue]
