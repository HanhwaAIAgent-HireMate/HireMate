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
