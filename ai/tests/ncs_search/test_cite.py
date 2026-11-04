from ncs_context import UNIT, FakeNcs, task
from pydantic import BaseModel

from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.ncs_search.cite import NcsQuery, find_sources, source_path, sources_block

SYSTEM = "면접 확인할 점을 NCS 업무 문장으로 바꾼다."


class Malformed(BaseModel):
    """모델이 형식에 맞지 않는 답을 냈을 때."""


def query(units: list[str] | None = None) -> NcsQuery:
    return NcsQuery(tasks=["배치 프로그램을 구현 한다"], units=[UNIT] if units is None else units)


async def test_prefix_numbers_sources() -> None:
    found = [task(sentences=["가 한다", "나 한다"]), task("chunk:2", ["다 한다"])]
    sources, miss = await find_sources(
        FakeLlm(query()), FakeNcs(found=found), "배치 질문", "백엔드", agent="interview", system=SYSTEM, prefix="N"
    )
    assert miss is None
    assert sources is not None
    assert list(sources.items) == ["N1", "N2", "N3"]
    assert sources.items["N3"] == (found[1], "다 한다")


async def test_default_prefix_is_s() -> None:
    sources, _ = await find_sources(FakeLlm(query()), FakeNcs(), "배치", "백엔드", agent="interview", system=SYSTEM)
    assert sources is not None
    assert list(sources.items) == ["S1"]


async def test_uses_given_system_and_agent() -> None:
    llm = FakeLlm(query())
    await find_sources(llm, FakeNcs(), "배치 질문", "백엔드", agent="interview", system=SYSTEM)
    assert llm.calls[0].agent == "interview"
    assert llm.calls[0].system == SYSTEM
    assert "배치 질문" in llm.calls[0].user


async def test_drops_unknown_units() -> None:
    ncs = FakeNcs()
    await find_sources(FakeLlm(query([UNIT, "9999"])), ncs, "배치", "백엔드", agent="interview", system=SYSTEM)
    assert ncs.searches[0][2] == [UNIT]


async def test_unavailable_returns_miss() -> None:
    result = await find_sources(
        FakeLlm(query()), FakeNcs(unavailable=True), "배치", "백엔드", agent="interview", system=SYSTEM
    )
    assert result == (None, "UNAVAILABLE")


async def test_query_failure_is_unavailable() -> None:
    result = await find_sources(FakeLlm(Malformed()), FakeNcs(), "배치", "백엔드", agent="interview", system=SYSTEM)
    assert result == (None, "UNAVAILABLE")


async def test_no_results_returns_not_found() -> None:
    result = await find_sources(FakeLlm(query()), FakeNcs(found=[]), "배치", "백엔드", agent="interview", system=SYSTEM)
    assert result == (None, "NOT_FOUND")


async def test_without_units_skips_model() -> None:
    llm = FakeLlm()
    result = await find_sources(llm, FakeNcs(unit_list=[]), "배치", "백엔드", agent="interview", system=SYSTEM)
    assert result == (None, "NOT_FOUND")
    assert llm.calls == []


async def test_sources_block_and_path() -> None:
    sources, _ = await find_sources(
        FakeLlm(query()), FakeNcs(), "배치", "백엔드", agent="interview", system=SYSTEM, prefix="N"
    )
    assert sources is not None
    assert source_path(task()) == "응용SW엔지니어링 › 서버프로그램 구현 › 서버 프로그램 구현하기"
    assert sources_block(sources).startswith('<data kind="ncs"')
    line = "[N1] 응용SW엔지니어링 › 서버프로그램 구현 › 서버 프로그램 구현하기: 서버 프로그램을 구현 한다"
    assert line in sources_block(sources)
