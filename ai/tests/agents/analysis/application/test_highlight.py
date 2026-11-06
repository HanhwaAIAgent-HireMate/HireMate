from uuid import uuid4

from hiremate_ai.agents.analysis.application.highlight import _Highlight, _Highlights, check_highlights, highlight
from hiremate_ai.agents.analysis.application.judge import verification_claims
from hiremate_ai.agents.analysis.application.types import Actor, CriterionResult, Fact, Note, Quote
from hiremate_ai.contract import ApplicantDocument, CriterionCategory, CriterionType, DocumentType, Verdict
from hiremate_ai.llm.fake import FakeLlm


def fact(statement: str, sentence: str, actor: Actor = Actor.SELF) -> Fact:
    return Fact(
        kind="EXPERIENCE",
        statement=statement,
        actor=actor,
        quotes=[Quote(document=DocumentType.PORTFOLIO, sentence=sentence)],
    )


BUILD = fact("정산 배치를 작성했다", "정산 배치 코드를 작성했습니다.")
TUNE = fact("배치 처리 시간을 줄였다", "쿼리를 나눠 처리 시간이 40분에서 12분으로 줄었습니다.")
TEAM = fact("팀이 정산 시스템을 이관했다", "팀이 정산 시스템을 이관했습니다.", Actor.TEAM)


async def test_same_work_is_grouped_with_its_metric() -> None:
    grouped = _Highlight(title="정산 배치 개선", detail="배치 작성", metric="40분 → 12분", sources=["F1", "F2"])
    llm = FakeLlm(_Highlights(items=[grouped]))

    notes = await highlight(llm, [BUILD, TUNE, TEAM])

    # 화면 카드가 제목 · 내용 · 지표를 따로 보이도록 나눠 담고, text는 셋을 이은 한 줄이다
    assert notes == [
        Note(
            text="정산 배치 개선 — 배치 작성. 40분 → 12분",
            source=DocumentType.PORTFOLIO.label,
            title="정산 배치 개선",
            detail="배치 작성",
            metric="40분 → 12분",
        )
    ]
    # 팀 경험은 묶을 후보로 넘기지 않는다
    assert "팀이 정산 시스템을 이관했다" not in llm.calls[0].user


async def test_one_own_fact_needs_no_grouping() -> None:
    llm = FakeLlm()

    assert await highlight(llm, [BUILD, TEAM]) == []
    assert llm.calls == []


def test_groups_with_unknown_sources_or_invented_numbers_are_dropped() -> None:
    facts = {1: BUILD, 2: TUNE}
    items = [
        _Highlight(title="없는 근거", detail="배치 작성", sources=["F9"]),
        _Highlight(title="지어낸 숫자", detail="처리 시간 70% 단축", sources=["F2"]),
        _Highlight(title="정산 배치 개선", detail="처리 시간 40분 → 12분", sources=["f2"]),
    ]

    assert [note.text for note in check_highlights(facts, items)] == ["정산 배치 개선 — 처리 시간 40분 → 12분"]


def test_verification_sees_the_paragraph_of_each_quote() -> None:
    document = ApplicantDocument(
        type=DocumentType.PORTFOLIO,
        file_id=uuid4(),
        file_name="",
        size=1,
        text="## 담당 범위\nAPI를 구현했습니다. 운영 중 쿼리를 고쳤습니다.\n\n## 기록\n응답 시간이 줄었습니다.",
    )
    result = CriterionResult(
        criterion_id="Q-01",
        category=CriterionCategory.QUALIFICATION,
        text="API를 개발하고 운영한 경험",
        important=False,
        criterion_type=CriterionType.COMPOSITE,
        verdict=Verdict.MET,
        reason="구현과 운영",
        metric="응답 시간 단축",
        quotes=[Quote(document=DocumentType.PORTFOLIO, sentence="API를 구현했습니다.")],
    )

    [claim, _] = verification_claims([result], [document])

    # 인용은 한 문장이어도 같은 문단의 운영 문장을 맥락으로 함께 넘기고, 다른 문단은 넘기지 않는다
    # (지표가 빈 항목은 성과 수치를 찾느라 맥락을 더 넓게 준다: test_judge)
    assert claim.context == "## 담당 범위 API를 구현했습니다. 운영 중 쿼리를 고쳤습니다."


def test_dropped_measurement_condition_is_put_back() -> None:
    # 원문 괄호 속 단서(다른 효과 포함)를 지표에서 빼면 성과가 과장돼 보여 다시 붙인다
    tuned = fact("대기 시간을 줄였다", "평균 대기 38초 → 21초(같은 시기 보상 개편 효과 포함)로 줄었습니다.")
    item = _Highlight(title="매칭 개선", detail="매칭 구조 개선", metric="평균 대기 38초 → 21초", sources=["F1", "F2"])

    [note] = check_highlights({1: BUILD, 2: tuned}, [item])

    assert note.metric == "평균 대기 38초 → 21초 (같은 시기 보상 개편 효과 포함)"


def test_team_work_paragraph_is_marked_when_own_role_is_missing() -> None:
    # 같은 문단이 공동 작업이라고 적었는데 본인 역할이 없으면 본인 성과처럼 보이지 않게 밝힌다
    text = (
        "재고 시스템 재구축\n3명이 함께 재고 집계 배치를 다시 만들었습니다.\n집계 시간이 2시간에서 30분으로 줄었습니다."
    )
    document = ApplicantDocument(type=DocumentType.PORTFOLIO, file_id=uuid4(), file_name="", size=1, text=text)
    rebuilt = fact("집계 배치를 다시 만들었다", "3명이 함께 재고 집계 배치를 다시 만들었습니다.")
    faster = fact("집계 시간을 줄였다", "집계 시간이 2시간에서 30분으로 줄었습니다.", Actor.UNCLEAR)
    item = _Highlight(title="재고 집계 재구축", detail="집계 배치 재작성", metric="2시간 → 30분", sources=["F1", "F2"])

    [note] = check_highlights({1: rebuilt, 2: faster}, [item], [document])

    assert note.detail == "집계 배치 재작성 (3명 공동 작업, 본인 역할 확인 필요)"


def test_team_project_shows_the_stated_own_role() -> None:
    # 이력서 표처럼 인원과 본인 역할이 적힌 공동 작업은 역할을 함께 보인다 (팀 성과를 본인 성과로 읽지 않게)
    text = (
        "재고 집계 재구축 (사내) | 역할: 설계 · 구현 리드 (운영팀 3명) | 인원: 3명\n"
        "집계 시간을 2시간에서 30분으로 줄였습니다."
    )
    document = ApplicantDocument(type=DocumentType.PORTFOLIO, file_id=uuid4(), file_name="", size=1, text=text)
    rebuilt = fact(
        "집계 배치를 재구축했다", "재고 집계 재구축 (사내) | 역할: 설계 · 구현 리드 (운영팀 3명) | 인원: 3명"
    )
    faster = fact("집계 시간을 줄였다", "집계 시간을 2시간에서 30분으로 줄였습니다.")
    item = _Highlight(title="재고 집계 재구축", detail="집계 배치 재작성", metric="2시간 → 30분", sources=["F1", "F2"])

    [note] = check_highlights({1: rebuilt, 2: faster}, [item], [document])

    assert note.detail == "집계 배치 재작성 (3명 프로젝트 · 본인 역할: 설계 · 구현 리드)"
