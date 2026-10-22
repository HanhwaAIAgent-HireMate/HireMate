from typing import Any

from hiremate_ai.agents.root.progress import SILENT, writer_progress
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
