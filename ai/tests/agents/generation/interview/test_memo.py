from uuid import uuid4

import pytest

from hiremate_ai.agents.generation.interview.agent import MemoQuestion, _memo_question
from hiremate_ai.contract import (
    InterviewerMemo,
    InterviewQuestion,
    InterviewView,
    PostingContent,
    PreviousInterview,
    QuestionSource,
)
from hiremate_ai.llm.fake import FakeLlm


@pytest.fixture
def memo_record() -> tuple[InterviewerMemo, InterviewView, MemoQuestion]:
    stage_id, question_id = uuid4(), uuid4()
    memo = InterviewerMemo(
        stage_id=stage_id, stage_name="1차 면접", text="장애 복구 때 본인이 직접 수행한 작업은 확인 못 함"
    )
    question = InterviewQuestion(
        question_id=question_id,
        text="서비스 장애에 대응한 경험을 설명해 주세요.",
        source=QuestionSource.AI,
        answer="팀에서 재처리 스크립트를 만들어 복구했습니다.",
    )
    interview = InterviewView(
        application_id=uuid4(),
        schedule=None,
        questions=[],
        previous=[PreviousInterview(stage_id=stage_id, stage_name="1차 면접", schedule=None, questions=[question])],
    )
    result = MemoQuestion(
        actionable=True,
        memo_quote=memo.text,
        question_id=question_id,
        answer_quote=question.answer,
        question="말씀하신 복구 작업에서 직접 작성한 부분과 다른 구성원이 맡은 부분을 구분해 설명해 주세요.",
        purpose="본인이 직접 작성한 복구 작업 범위 확인",
    )
    return memo, interview, result


async def test_memo_question_preserves_source_without_treating_note_as_fact(
    memo_record: tuple[InterviewerMemo, InterviewView, MemoQuestion],
    sample_posting: PostingContent,
) -> None:
    memo, interview, result = memo_record
    llm = FakeLlm(result)
    found = await _memo_question(llm, memo, interview, sample_posting, "메모의 본인 작업 범위를 확인")
    assert len(found) == 1
    assert found[0].reason and "출처: 면접관메모" in found[0].reason
    assert "이전 면접 답변:" in found[0].reason
    assert "주관적 기록" in llm.calls[0].system
    assert '<data kind="interviewer_memo">' in llm.calls[0].user


@pytest.mark.parametrize("failure", ["abstract", "quote", "answer", "question_id", "duplicate"])
async def test_invalid_memo_candidate_never_falls_back_to_unrelated_questions(
    failure: str,
    memo_record: tuple[InterviewerMemo, InterviewView, MemoQuestion],
    sample_posting: PostingContent,
) -> None:
    memo, interview, result = memo_record
    updates: dict[str, dict[str, object]] = {
        "abstract": {"actionable": False},
        "quote": {"memo_quote": "원문에 없는 역할"},
        "answer": {"answer_quote": "제가 혼자 복구했습니다."},
        "question_id": {"question_id": uuid4()},
        "duplicate": {"question": interview.previous[0].questions[0].text},
    }
    found = await _memo_question(
        llm=FakeLlm(result.model_copy(update=updates[failure])),
        memo=memo,
        interview=interview,
        posting=sample_posting,
        focus="메모 참고",
    )
    assert found == []


async def test_no_answer_or_blocked_focus_does_not_invent_a_memo_question(
    memo_record: tuple[InterviewerMemo, InterviewView, MemoQuestion],
    sample_posting: PostingContent,
) -> None:
    memo, interview, _ = memo_record
    llm = FakeLlm()
    assert await _memo_question(llm, memo, interview, sample_posting, "") == []
    assert llm.calls == []
