"""Root 처리 중 진행 알림. 단계 문구(status)와 검증을 마친 항목(item)만 낸다.

모델이 쓴 문장을 검사 전에 내보내지 않는다 (규칙 6, 7). 단계 문구는 코드 상수이고, 지원자 이름과 개수만 코드가 채운다.
그래프 노드는 runtime.stream_writer를 감싸 넘기고, 그래프 밖에서 부르는 테스트와 평가는 SILENT를 쓴다.

단계에는 깊이(depth)가 있다. 0은 Root의 단계, 1은 그 아래에서 Root가 부른 도구나 하위 Agent의 일, 2는 그 일의 결과다.
아래 단계에 넘길 때는 nested로 한 칸 들여 넘긴다.
"""

from collections.abc import Sequence
from typing import Literal, Protocol, TypedDict

from langgraph.types import StreamWriter

from hiremate_ai.agents.root.types import CandidateRow, ChatItem, ChatStatus

type ProgressEvent = tuple[Literal["status", "item"], ChatStatus | ChatItem]

# 단계 문구에 이름을 모두 쓰는 지원자 수. 넘으면 '김지원 외 3명'으로 줄인다
NAMED = 2


class Step(TypedDict):
    """대화방에 남기는 단계 하나. 체크포인트에 JSON으로 저장한다."""

    text: str
    depth: int


class Progress(Protocol):
    def status(self, text: str, depth: int = 0) -> None: ...

    def item(self, item: ChatItem) -> None: ...


class _Silent:
    def status(self, text: str, depth: int = 0) -> None:
        pass

    def item(self, item: ChatItem) -> None:
        pass


SILENT: Progress = _Silent()


class _Writer:
    def __init__(self, writer: StreamWriter) -> None:
        self._writer = writer

    def status(self, text: str, depth: int = 0) -> None:
        event: ProgressEvent = ("status", ChatStatus(text=text, depth=depth))
        self._writer(event)

    def item(self, item: ChatItem) -> None:
        event: ProgressEvent = ("item", item)
        self._writer(event)


def writer_progress(writer: StreamWriter) -> Progress:
    """LangGraph custom 스트림에 (이벤트 이름, data)를 낸다."""
    return _Writer(writer)


class _Nested:
    def __init__(self, progress: Progress, levels: int) -> None:
        self._progress = progress
        self._levels = levels

    def status(self, text: str, depth: int = 0) -> None:
        self._progress.status(text, depth + self._levels)

    def item(self, item: ChatItem) -> None:
        self._progress.item(item)


def nested(progress: Progress, levels: int = 1) -> Progress:
    """단계를 levels칸 들여 내는 Progress. Root 단계 아래의 도구, 하위 Agent에 넘긴다."""
    return _Nested(progress, levels)


def names(rows: Sequence[CandidateRow]) -> str:
    """단계 문구에 넣을 지원자 이름. 많으면 '김지원 외 3명'으로 줄인다."""
    if len(rows) <= NAMED:
        return " · ".join(row.name for row in rows)
    return f"{rows[0].name} 외 {len(rows) - 1}명"


def step(text: str, depth: int = 0) -> Step:
    return {"text": text, "depth": depth}


def stored_steps(values: Sequence[object]) -> list[Step]:
    """대화방에 남은 단계. 깊이가 생기기 전의 기록은 문구만 있어 Root 단계로 읽는다."""
    steps: list[Step] = []
    for value in values:
        if isinstance(value, str):
            steps.append(step(value))
        elif isinstance(value, dict) and isinstance(value.get("text"), str):
            depth = value.get("depth")
            steps.append(step(value["text"], depth if isinstance(depth, int) else 0))
    return steps


class StepRecorder:
    """알림을 그대로 내면서 단계를 순서대로 모은다. 대화방에 그 턴의 처리 과정으로 남긴다.

    같은 깊이의 같은 문구가 이어지면 한 번만 남긴다. 항목은 답에 남으므로 모으지 않는다.
    """

    def __init__(self, progress: Progress, steps: Sequence[object] | None = None) -> None:
        self._progress = progress
        self.steps: list[Step] = stored_steps(steps or [])

    def status(self, text: str, depth: int = 0) -> None:
        if not self.steps or self.steps[-1] != step(text, depth):
            self.steps.append(step(text, depth))
        self._progress.status(text, depth)

    def item(self, item: ChatItem) -> None:
        self._progress.item(item)
