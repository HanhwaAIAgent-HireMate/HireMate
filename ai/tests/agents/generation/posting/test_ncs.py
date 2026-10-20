from hiremate_ai.agents.generation.posting.ncs import UNIT_CODE, ncs_data, subdivisions, unit_by_code, units_of


def test_data_records_its_source_and_date() -> None:
    data = ncs_data()

    assert "공통 NCS 정보" in data.source
    assert data.retrieved_at == "2026-10-20"


def test_data_has_demo_subdivisions_in_code_order() -> None:
    assert subdivisions() == ["응용SW엔지니어링", "DB엔지니어링"]
    assert all(units_of(name) for name in subdivisions())


def test_units_have_valid_unique_codes_and_clean_text() -> None:
    units = ncs_data().units
    codes = [unit.code for unit in units]

    assert all(UNIT_CODE.match(code) for code in codes)
    assert len(codes) == len(set(codes))
    assert all(1 <= unit.level <= 8 for unit in units)
    assert not any("？" in unit.name or "？" in unit.definition for unit in units)
    assert not any("(구버전)" in unit.name for unit in units)


def test_each_definition_explains_its_own_unit() -> None:
    """원본에는 다른 능력단위의 정의가 잘못 들어 있는 것이 있었다. 정의는 'OO이란'으로 자기 이름부터 시작한다."""
    for unit in ncs_data().units:
        assert unit.definition.replace(" ", "").startswith(unit.name.replace(" ", "")), unit.code


def test_unit_by_code_finds_unit_with_definition_and_citation() -> None:
    unit = unit_by_code("2001020211_23v6")

    assert unit is not None
    assert unit.name == "서버프로그램 구현"
    assert unit.level == 5
    assert unit.definition.startswith("서버프로그램 구현이란")
    assert unit.classification == "정보통신 > 정보기술 > 정보기술개발 > 응용SW엔지니어링"
    assert unit.citation == "NCS 응용SW엔지니어링 · 서버프로그램 구현"


def test_unit_by_code_finds_the_data_version_when_version_differs() -> None:
    unit = unit_by_code("2001020211_19v1")

    assert unit is not None
    assert unit.code == "2001020211_23v6"


def test_unit_by_code_returns_none_for_unknown_code() -> None:
    assert unit_by_code("2001020299_23v6") is None
    assert unit_by_code("서버프로그램 구현") is None


def test_units_of_unknown_subdivision_is_empty() -> None:
    assert units_of("없는 세분류") == []
