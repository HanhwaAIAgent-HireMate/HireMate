from typing import Any

from root_context import extra_row

from hiremate_ai.agents.root.progress import SILENT, StepRecorder, names, nested, stored_steps, writer_progress
from hiremate_ai.agents.root.types import ChatItem, ChatStatus

ITEM = ChatItem(application_id=None, label="RDBMS", text="Oracle 원장 설계", status="OK")


def test_writer_progress_emits_status_and_item() -> None:
    written: list[Any] = []
    progress = writer_progress(written.append)

    progress.status("요청을 확인하고 있어요")
    progress.item(ITEM)

    assert written == [("status", ChatStatus(text="요청을 확인하고 있어요", depth=0)), ("item", ITEM)]


def test_silent_does_nothing() -> None:
    # 그래프 밖(단위 테스트, 평가)에서 불러도 예외 없이 지나간다
    SILENT.status("요청을 확인하고 있어요")
    SILENT.item(ITEM)


def test_step_recorder_passes_events_and_keeps_steps_in_order() -> None:
    written: list[Any] = []
    progress = StepRecorder(writer_progress(written.append), [{"text": "요청을 확인하고 있어요", "depth": 0}])

    progress.status("요청을 확인하고 있어요")
    progress.status("지원자 자료를 확인하고 있어요")
    progress.item(ITEM)
    progress.status("지원자 자료를 확인하고 있어요")
    progress.status("지원자 자료를 확인하고 있어요", 1)
    progress.status("요청을 확인하고 있어요")

    # 화면에는 받은 그대로 내고, 이어진 같은 깊이의 같은 문구만 한 번으로 남긴다
    assert len(written) == 6
    assert progress.steps == [
        {"text": "요청을 확인하고 있어요", "depth": 0},
        {"text": "지원자 자료를 확인하고 있어요", "depth": 0},
        {"text": "지원자 자료를 확인하고 있어요", "depth": 1},
        {"text": "요청을 확인하고 있어요", "depth": 0},
    ]


def test_nested_progress_indents_each_level() -> None:
    written: list[Any] = []
    root = writer_progress(written.append)
    agent = nested(root)

    root.status("요청에 맞는 답변을 준비하고 있어요")
    agent.status("서류 Agent · 정유민의 제출 문서 2건을 검토하고 있어요")
    agent.status("근거 문장 3개를 찾았어요", 1)
    nested(agent).status("후보 4명을 다시 확인하고 있어요")
    agent.item(ITEM)

    assert [event[1].depth for event in written if event[0] == "status"] == [0, 1, 2, 2]
    assert written[-1] == ("item", ITEM)


def test_names_shortens_long_lists() -> None:
    assert names([extra_row("정유민")]) == "정유민"
    assert names([extra_row("정유민"), extra_row("김하늘")]) == "정유민 · 김하늘"
    assert names([extra_row("정유민"), extra_row("김하늘"), extra_row("한예린")]) == "정유민 외 2명"


def test_stored_steps_reads_old_text_only_steps_as_root_steps() -> None:
    # 깊이가 생기기 전의 대화방에는 문구만 남아 있다
    assert stored_steps(["요청을 확인하고 있어요", {"text": "정유민의 프로필을 읽고 있어요", "depth": 1}, 3]) == [
        {"text": "요청을 확인하고 있어요", "depth": 0},
        {"text": "정유민의 프로필을 읽고 있어요", "depth": 1},
    ]
