import unicodedata
from uuid import uuid4

from hiremate_ai.agents.analysis.application.highlight import Highlight, check_highlights, experiences
from hiremate_ai.agents.analysis.application.judge import paragraphs, verification_claims
from hiremate_ai.agents.analysis.application.review import Claim, claim_lines
from hiremate_ai.agents.analysis.application.types import Actor, CriterionResult, Fact, Note, Quote
from hiremate_ai.contract import ApplicantDocument, CriterionCategory, CriterionType, DocumentType, Verdict


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


def test_same_work_is_grouped_with_its_metric() -> None:
    grouped = Highlight(title="정산 배치 개선", detail="배치 작성", metric="40분 → 12분", sources=["F1", "F2"])
    numbered = experiences([BUILD, TUNE, TEAM])

    notes = check_highlights(dict(numbered), [grouped])

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
    assert [number for number, _ in numbered] == [1, 2]


def test_one_own_fact_needs_no_grouping() -> None:
    assert experiences([BUILD, TEAM]) == []


def test_groups_with_unknown_sources_or_invented_numbers_are_dropped() -> None:
    facts = {1: BUILD, 2: TUNE}
    items = [
        Highlight(title="없는 근거", detail="배치 작성", sources=["F9"]),
        Highlight(title="지어낸 숫자", detail="처리 시간 70% 단축", sources=["F2"]),
        Highlight(title="정산 배치 개선", detail="처리 시간 40분 → 12분", sources=["f2"]),
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
        quotes=[Quote(document=DocumentType.PORTFOLIO, sentence="API를 구현했습니다.")],
    )

    [claim] = verification_claims([result], [document])

    # 인용은 한 문장이어도 같은 문단의 운영 문장을 맥락으로 함께 넘기고, 다른 문단은 넘기지 않는다
    assert claim.context == "## 담당 범위 API를 구현했습니다. 운영 중 쿼리를 고쳤습니다."


def test_long_paragraph_context_surrounds_the_quote_and_deduplicates() -> None:
    before = "앞 문장 " * 200
    first = "검색 API를 구현했습니다."
    second = "운영 지연을 줄였습니다."
    after = "뒷 문장 " * 200
    document = ApplicantDocument(
        type=DocumentType.PORTFOLIO,
        file_id=uuid4(),
        file_name="",
        size=1,
        text=f"{before}{first} {second}{after}",
    )
    quotes = [Quote(document=DocumentType.PORTFOLIO, sentence=text) for text in (first, second)]

    context = paragraphs(quotes, [document])

    assert first in context and second in context
    assert context.count(first) == 1 and context.count(second) == 1
    assert len(context) <= 600


def test_claims_share_repeated_context_without_losing_references() -> None:
    context = "같은 프로젝트에서 직접 구현하고 운영했습니다."
    first = Claim("Q-01", "구현했다", [], context)
    second = Claim("P-01", "운영했다", [], context)

    prompt = claim_lines([first, second])

    assert prompt.count(context) == 1
    assert "Q-01. 주장: 구현했다" in prompt and "P-01. 주장: 운영했다" in prompt
    assert prompt.count("맥락 C1") == 2


def test_claims_share_individual_contexts_when_their_other_contexts_differ() -> None:
    shared = "공통 근거 문단"
    first = Claim("Q-01", "구현했다", [], context_parts=(shared, "첫 문단"))
    second = Claim("P-01", "운영했다", [], context_parts=(shared, "둘째 문단"))

    prompt = claim_lines([first, second])

    assert prompt.count(shared) == 1
    assert "맥락 C1, 맥락 C2" in prompt
    assert "맥락 C1, 맥락 C3" in prompt


def test_context_finds_quotes_across_line_breaks_and_compatibility_characters() -> None:
    document = ApplicantDocument(
        type=DocumentType.PORTFOLIO,
        file_id=uuid4(),
        file_name="",
        size=1,
        text="앞 문장 " * 200 + "검색 API를\n구현했습니다. 이후 운영했습니다.",
    )
    quote = Quote(document=DocumentType.PORTFOLIO, sentence="검색 ＡＰＩ를 구현했습니다.")

    context = paragraphs([quote], [document])

    assert "검색 API를 구현했습니다. 이후 운영했습니다." in context


def test_long_quote_is_never_truncated_from_its_context() -> None:
    sentence = "근거 내용 " * 150 + "수행 결과입니다."
    document = ApplicantDocument(
        type=DocumentType.PORTFOLIO,
        file_id=uuid4(),
        file_name="",
        size=1,
        text="앞부분 " * 200 + sentence + " 뒤의 설명",
    )
    quote = Quote(document=DocumentType.PORTFOLIO, sentence=sentence)

    assert sentence in paragraphs([quote], [document])


def test_context_finds_decomposed_korean_in_document() -> None:
    sentence = "검색 기능을 구현했습니다."
    document = ApplicantDocument(
        type=DocumentType.PORTFOLIO,
        file_id=uuid4(),
        file_name="",
        size=1,
        text=unicodedata.normalize("NFD", sentence),
    )
    quote = Quote(document=DocumentType.PORTFOLIO, sentence=sentence)

    assert unicodedata.normalize("NFC", paragraphs([quote], [document])) == sentence


def test_dropped_measurement_condition_is_put_back() -> None:
    # 원문 괄호 속 단서(다른 효과 포함)를 지표에서 빼면 성과가 과장돼 보여 다시 붙인다
    tuned = fact("대기 시간을 줄였다", "평균 대기 38초 → 21초(같은 시기 보상 개편 효과 포함)로 줄었습니다.")
    item = Highlight(title="매칭 개선", detail="매칭 구조 개선", metric="평균 대기 38초 → 21초", sources=["F1", "F2"])

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
    item = Highlight(title="재고 집계 재구축", detail="집계 배치 재작성", metric="2시간 → 30분", sources=["F1", "F2"])

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
    item = Highlight(title="재고 집계 재구축", detail="집계 배치 재작성", metric="2시간 → 30분", sources=["F1", "F2"])

    [note] = check_highlights({1: rebuilt, 2: faster}, [item], [document])

    assert note.detail == "집계 배치 재작성 (3명 프로젝트 · 본인 역할: 설계 · 구현 리드)"
