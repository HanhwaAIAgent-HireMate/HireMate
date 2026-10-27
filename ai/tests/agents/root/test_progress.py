from typing import Any

from hiremate_ai.agents.root.progress import SILENT, StepRecorder, writer_progress
from hiremate_ai.agents.root.types import ChatItem, ChatStatus

ITEM = ChatItem(application_id=None, label="RDBMS", text="Oracle 원장 설계", status="OK")


def test_writer_progress_emits_status_and_item() -> None:
    written: list[Any] = []
    progress = writer_progress(written.append)

    progress.status("요청을 확인하고 있어요")
    progress.item(ITEM)

    assert written == [("status", ChatStatus(text="요청을 확인하고 있어요")), ("item", ITEM)]


def test_silent_does_nothing() -> None:
    # 그래프 밖(단위 테스트, 평가)에서 불러도 예외 없이 지나간다
    SILENT.status("요청을 확인하고 있어요")
    SILENT.item(ITEM)


def test_step_recorder_passes_events_and_keeps_steps_in_order() -> None:
    written: list[Any] = []
    progress = StepRecorder(writer_progress(written.append), ["요청을 확인하고 있어요"])

    progress.status("요청을 확인하고 있어요")
    progress.status("지원자 자료를 확인하고 있어요")
    progress.item(ITEM)
    progress.status("지원자 자료를 확인하고 있어요")
    progress.status("요청을 확인하고 있어요")

    # 화면에는 받은 그대로 내고, 이어진 같은 문구만 한 번으로 남긴다
    assert len(written) == 5
    assert progress.steps == ["요청을 확인하고 있어요", "지원자 자료를 확인하고 있어요", "요청을 확인하고 있어요"]
