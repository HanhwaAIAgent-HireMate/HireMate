"""NCS 표 테스트. 실제 ncs_units.json(응용SW엔지니어링 · DB엔지니어링)을 DB에 넣고 꺼내 본다."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.db.ncs import EMBEDDING_DIM, NcsElementRow, NcsStatementRow, NcsUnitRow, StatementKind
from hiremate_ai.db.ncs_store import (
    get_unit,
    list_duties,
    load_ncs,
    nearest_units,
    set_embedding,
    units_missing_embedding,
    units_of_duty,
)
from hiremate_ai.tools.ncs import NcsData, ncs_data


async def count(session: AsyncSession, table: type[NcsUnitRow | NcsElementRow | NcsStatementRow]) -> int:
    return await session.scalar(select(func.count()).select_from(table)) or 0


def one_hot(index: int) -> list[float]:
    """테스트용 벡터: index 자리만 1이다. 같은 자리끼리는 거리 0, 다른 자리끼리는 거리 1."""
    vector = [0.0] * EMBEDDING_DIM
    vector[index] = 1.0
    return vector


def with_new_version(data: NcsData, code: str, new_code: str, new_definition: str) -> NcsData:
    """능력단위 하나를 새 버전 코드로 바꾼 자료 (NCS 개정 흉내)."""
    units = [
        unit.model_copy(update={"code": new_code, "definition": new_definition}) if unit.code == code else unit
        for unit in data.units
    ]
    return data.model_copy(update={"units": units})


async def test_loads_every_row_of_the_json(db_session: AsyncSession) -> None:
    data = ncs_data()

    result = await load_ncs(db_session, data)

    # json의 개수 그대로 들어간다
    elements = sum(len(unit.elements) for unit in data.units)
    statements = sum(
        len(element.criteria) + len(element.knowledge) + len(element.skills) + len(element.attitudes)
        for unit in data.units
        for element in unit.elements
    )
    assert (result.duties, result.units, result.retired) == (2, 38, [])
    assert await count(db_session, NcsUnitRow) == 38
    assert await count(db_session, NcsElementRow) == elements == 107
    assert await count(db_session, NcsStatementRow) == statements == 355 + 1948


async def test_units_come_back_exactly_as_in_the_json(db_session: AsyncSession) -> None:
    data = ncs_data()
    await load_ncs(db_session, data)
    db_session.expunge_all()  # 메모리를 비우고 DB에서 다시 읽는다

    # DB에서 꺼낸 능력단위가 json의 능력단위와 한 글자도 다르지 않다 (요소 · 수행준거 · KSA 순서까지)
    for unit in data.units:
        assert await get_unit(db_session, unit.code) == unit


async def test_duties_and_units_of_duty(db_session: AsyncSession) -> None:
    await load_ncs(db_session, ncs_data())

    duties = await list_duties(db_session)
    software = await units_of_duty(db_session, "20010202")
    database = await units_of_duty(db_session, "20010204")

    assert [(duty.code, duty.name) for duty in duties] == [
        ("20010202", "응용SW엔지니어링"),
        ("20010204", "DB엔지니어링"),
    ]
    assert (len(software), len(database)) == (27, 11)
    assert software[0].classification == "정보통신 > 정보기술 > 정보기술개발 > 응용SW엔지니어링"


async def test_loading_twice_gives_the_same_rows(db_session: AsyncSession) -> None:
    data = ncs_data()

    await load_ncs(db_session, data)
    await load_ncs(db_session, data)

    assert await count(db_session, NcsUnitRow) == 38
    assert await count(db_session, NcsStatementRow) == 355 + 1948


async def test_new_version_retires_the_old_one(db_session: AsyncSession) -> None:
    data = ncs_data()
    old = data.units[0]
    base = old.code.split("_")[0]
    new_code = f"{base}_99v1"  # 지금 자료보다 새 버전
    await load_ncs(db_session, data)

    result = await load_ncs(db_session, with_new_version(data, old.code, new_code, "개정된 정의"))

    old_row = await db_session.get(NcsUnitRow, old.code)
    by_old_code = await get_unit(db_session, old.code)
    by_wrong_version = await get_unit(db_session, f"{base}_10v1")

    assert result.retired == [old.code]
    assert old_row is not None and old_row.active is False
    # 옛 코드로 찾으면 그 버전이, 버전을 틀리게 적으면 최신 버전이 나온다
    assert by_old_code is not None and by_old_code.definition == old.definition
    assert by_wrong_version is not None and by_wrong_version.code == new_code
    # 직무 목록에는 최신 버전만 나온다
    codes = [unit.code for unit in await units_of_duty(db_session, old.duty_code)]
    assert new_code in codes and old.code not in codes


async def test_embedding_is_kept_on_reload_and_cleared_when_text_changes(db_session: AsyncSession) -> None:
    data = ncs_data()
    first, second = data.units[0], data.units[1]
    await load_ncs(db_session, data)
    await set_embedding(db_session, first.code, one_hot(0))
    await set_embedding(db_session, second.code, one_hot(1))

    # 같은 자료를 다시 넣으면 벡터가 남고, 정의가 바뀐 능력단위만 벡터가 비워진다
    changed = data.model_copy(
        update={"units": [second.model_copy(update={"definition": "바뀐 정의"}), *data.units[2:], first]}
    )
    await load_ncs(db_session, changed)

    missing = [code for code, _ in await units_missing_embedding(db_session)]
    assert first.code not in missing
    assert second.code in missing


async def test_nearest_units_finds_closest_vectors_in_order(db_session: AsyncSession) -> None:
    data = ncs_data()
    await load_ncs(db_session, data)
    a, b, c = data.units[0], data.units[1], data.units[2]
    await set_embedding(db_session, a.code, one_hot(0))
    await set_embedding(db_session, b.code, one_hot(1))
    await set_embedding(db_session, c.code, [0.9 if i == 0 else 0.1 if i == 1 else 0.0 for i in range(EMBEDDING_DIM)])

    hits = await nearest_units(db_session, one_hot(0), limit=2)

    # a(거리 0) → c(a 쪽에 가까움) 순서. 벡터가 없는 나머지 35개는 후보에 들지 않는다
    assert [hit.code for hit in hits] == [a.code, c.code]
    assert hits[0].distance == pytest.approx(0.0, abs=1e-6)


async def test_set_embedding_checks_dimension_and_code(db_session: AsyncSession) -> None:
    await load_ncs(db_session, ncs_data())

    with pytest.raises(ValueError, match="1024"):
        await set_embedding(db_session, ncs_data().units[0].code, [0.1, 0.2])
    with pytest.raises(KeyError):
        await set_embedding(db_session, "0000000000_00v0", one_hot(0))


async def test_missing_embedding_text_is_name_and_definition(db_session: AsyncSession) -> None:
    data = ncs_data()
    await load_ncs(db_session, data)

    missing = dict(await units_missing_embedding(db_session))

    first = data.units[0]
    assert missing[first.code] == f"{first.name}: {first.definition}"
    assert len(missing) == 38


def test_statement_kinds_cover_every_list_of_an_element() -> None:
    assert {kind.value for kind in StatementKind} == {"CRITERION", "KNOWLEDGE", "SKILL", "ATTITUDE"}
