from ncs_context import OTHER_UNIT, UNIT, FakeNcs, task, units
from pydantic import BaseModel

from hiremate_ai.agents.generation.posting.ncs import (
    NCS_NOT_FOUND,
    NCS_REVIEW_FAILED,
    NCS_SOURCES_DROPPED,
    NCS_UNAVAILABLE,
    Cited,
    LineCitation,
    NcsQuery,
    NcsSources,
    SupportReview,
    SupportVerdict,
    cite_lines,
    find_sources,
    keep_supported,
    source_lines,
    sources_block,
)
from hiremate_ai.contract import PostingContent
from hiremate_ai.llm.fake import FakeLlm


class Malformed(BaseModel):
    """모델이 형식에 맞지 않는 답을 냈을 때. FakeLlm이 다른 형식을 받으면 예외를 낸다."""


def query(units: list[str] | None = None) -> NcsQuery:
    return NcsQuery(tasks=["서버 프로그램을 구현 한다"], units=[UNIT] if units is None else units)


async def test_find_sources_drops_unknown_units() -> None:
    ncs = FakeNcs()
    asked = [UNIT, "9999999999_99v9", OTHER_UNIT, UNIT, UNIT, UNIT, UNIT]

    sources, notice = await find_sources(FakeLlm(query(asked)), ncs, "서버 업무 추천해줘", "백엔드 개발")

    assert ncs.searches == [("서버 업무 추천해줘", ["서버 프로그램을 구현 한다"], [UNIT, OTHER_UNIT])]
    assert sources is not None
    assert notice is None


async def test_find_sources_gives_unit_list_and_request_to_model() -> None:
    llm = FakeLlm(query())

    await find_sources(llm, FakeNcs(), "서버 업무 추천해줘", "백엔드 개발")

    user = llm.calls[0].user
    assert f"{UNIT} 서버프로그램 구현: 서버 프로그램 구현하기" in user
    assert "## 응용SW엔지니어링" in user
    assert user.index("<data") < user.index("HR 요청: 서버 업무 추천해줘")
    assert "직무: 백엔드 개발" in user


async def test_find_sources_without_units_skips_model() -> None:
    llm = FakeLlm()

    sources, notice = await find_sources(llm, FakeNcs(unit_list=[]), "서버 업무", "백엔드")

    assert (sources, notice) == (None, NCS_NOT_FOUND)
    assert llm.calls == []


async def test_find_sources_unavailable() -> None:
    assert await find_sources(FakeLlm(query()), FakeNcs(unavailable=True), "서버 업무", "백엔드") == (
        None,
        NCS_UNAVAILABLE,
    )


async def test_find_sources_query_failure_is_unavailable() -> None:
    ncs = FakeNcs()

    result = await find_sources(FakeLlm(Malformed()), ncs, "서버 업무", "백엔드")

    assert result == (None, NCS_UNAVAILABLE)
    assert ncs.searches == []


async def test_find_sources_no_results() -> None:
    assert await find_sources(FakeLlm(query()), FakeNcs(found=[]), "서버 업무", "백엔드") == (None, NCS_NOT_FOUND)


async def test_sources_are_numbered_in_search_order() -> None:
    found = [task("a", ["가 한다", "나 한다"]), task("b", ["다 한다", "라 한다"])]

    sources, _ = await find_sources(FakeLlm(query()), FakeNcs(found=found), "서버 업무", "백엔드")

    assert sources is not None
    assert list(sources.items) == ["S1", "S2", "S3", "S4"]
    assert sources.items["S3"] == (found[1], "다 한다")
    assert "[S3] 응용SW엔지니어링 › 서버프로그램 구현 › 서버 프로그램 구현하기: 다 한다" in sources_block(sources)
    assert sources_block(sources).startswith('<data kind="ncs"')


def sources() -> NcsSources:
    return NcsSources(items={"S1": (task(), "서버 프로그램을 구현 한다")})


def content(duties: list[str]) -> PostingContent:
    return PostingContent(
        title="",
        job_category="",
        employment_type="",
        career="",
        location="",
        intro="",
        duties=duties,
        qualifications=[],
        preferred=[],
        benefits=[],
    )


def clean(line: str) -> str:
    return line.removeprefix("- ").strip()


def test_cited_line_matches_cleaned_item() -> None:
    citation = LineCitation(field="주요 업무", line="- 주문 API 개발", sources=["S1"])

    cited = cite_lines([citation], content(["결제 API 개발", "주문 API 개발"]), ["duties"], sources(), clean)

    assert cited == [Cited(label="주요 업무", number=2, line="주문 API 개발", source="S1")]


def test_citation_of_unchanged_field_or_unknown_source_is_dropped() -> None:
    citations = [
        LineCitation(field="자격 요건", line="주문 API 개발", sources=["S1"]),
        LineCitation(field="주요 업무", line="주문 API 개발", sources=["S9"]),
        LineCitation(field="주요 업무", line="없는 줄", sources=["S1"]),
    ]

    assert cite_lines(citations, content(["주문 API 개발"]), ["duties"], sources(), clean) == []


def test_same_citation_is_kept_once() -> None:
    citation = LineCitation(field="주요 업무", line="주문 API 개발", sources=["S1", "S1"])

    cited = cite_lines([citation, citation], content(["주문 API 개발"]), ["duties"], sources(), clean)

    assert len(cited) == 1


def cited(number: int = 1) -> Cited:
    return Cited(label="주요 업무", number=number, line=f"{number}번 업무", source="S1")


async def test_keep_supported_without_citations_skips_model() -> None:
    llm = FakeLlm()

    assert await keep_supported(llm, [], sources()) == ([], None)
    assert llm.calls == []


async def test_keep_supported_keeps_supported() -> None:
    review = SupportReview(verdicts=[SupportVerdict(index=0, verdict="supports")])

    assert await keep_supported(FakeLlm(review), [cited()], sources()) == ([cited()], None)


async def test_keep_supported_drops_unrelated_with_notice() -> None:
    review = SupportReview(
        verdicts=[SupportVerdict(index=0, verdict="supports"), SupportVerdict(index=1, verdict="unrelated")]
    )

    kept, notice = await keep_supported(FakeLlm(review), [cited(1), cited(2)], sources())

    assert kept == [cited(1)]
    assert notice == NCS_SOURCES_DROPPED


async def test_keep_supported_drops_unjudged() -> None:
    kept, notice = await keep_supported(FakeLlm(SupportReview(verdicts=[])), [cited()], sources())

    assert (kept, notice) == ([], NCS_SOURCES_DROPPED)


async def test_keep_supported_failure_drops_all() -> None:
    llm = FakeLlm(Malformed())

    assert await keep_supported(llm, [cited()], sources()) == ([], NCS_REVIEW_FAILED)


async def test_keep_supported_shows_line_and_source_to_model() -> None:
    llm = FakeLlm(SupportReview(verdicts=[]))

    await keep_supported(llm, [cited()], sources())

    assert "1번 업무" in llm.calls[0].user
    assert "서버 프로그램을 구현 한다" in llm.calls[0].user


def test_source_line_format() -> None:
    line = Cited(label="주요 업무", number=2, line="서버 개발", source="S1")

    assert source_lines([line], sources()) == [
        '주요 업무 2번 ← 응용SW엔지니어링 › 서버프로그램 구현 › 서버 프로그램 구현하기: "서버 프로그램을 구현 한다"'
    ]


def test_units_fixture_is_ordered() -> None:
    assert [unit.code for unit in units()] == [UNIT, OTHER_UNIT]
