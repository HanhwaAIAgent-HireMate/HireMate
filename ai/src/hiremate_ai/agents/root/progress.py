"""Root 처리 중 진행 알림. 단계 문구(status)와 검증을 마친 항목(item)만 낸다.

모델이 쓴 문장을 검사 전에 내보내지 않는다 (규칙 6, 7). 그래프 노드는 runtime.stream_writer를 감싸 넘기고,
그래프 밖에서 부르는 테스트와 평가는 SILENT를 쓴다.
"""

from typing import Literal, Protocol

from langgraph.types import StreamWriter

from hiremate_ai.agents.root.types import ChatItem, ChatStatus

type ProgressEvent = tuple[Literal["status", "item"], ChatStatus | ChatItem]


class Progress(Protocol):
    def status(self, text: str) -> None: ...

    def item(self, item: ChatItem) -> None: ...


class _Silent:
    def status(self, text: str) -> None:
        pass

    def item(self, item: ChatItem) -> None:
        pass


SILENT: Progress = _Silent()


class _Writer:
    def __init__(self, writer: StreamWriter) -> None:
        self._writer = writer

    def status(self, text: str) -> None:
        event: ProgressEvent = ("status", ChatStatus(text=text))
        self._writer(event)

    def item(self, item: ChatItem) -> None:
        event: ProgressEvent = ("item", item)
        self._writer(event)


def writer_progress(writer: StreamWriter) -> Progress:
    """LangGraph custom 스트림에 (이벤트 이름, data)를 낸다."""
    return _Writer(writer)


class StepRecorder:
    """알림을 그대로 내면서 단계 문구를 순서대로 모은다. 대화방에 그 턴의 처리 과정으로 남긴다.

    같은 문구가 이어지면 한 번만 남긴다. 항목은 답에 남으므로 모으지 않는다.
    """

    def __init__(self, progress: Progress, steps: list[str] | None = None) -> None:
        self._progress = progress
        self.steps: list[str] = list(steps or [])

    def status(self, text: str) -> None:
        if not self.steps or self.steps[-1] != text:
            self.steps.append(text)
        self._progress.status(text)

    def item(self, item: ChatItem) -> None:
        self._progress.item(item)
