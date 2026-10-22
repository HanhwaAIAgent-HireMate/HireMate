import pytest

from hiremate_ai.tools.ncs import UNIT_CODE, NcsSurvey, ncs_data, subdivisions, survey_score, unit_by_code, units_of


def test_data_records_its_source_and_date() -> None:
    data = ncs_data()

    assert "국가직무능력표준 정보_GW" in data.source
    assert "15157547" in data.source
    assert "NCS 중요도 및 활용도" in data.survey_source
    assert data.retrieved_at == "2026-10-22"


def test_data_has_demo_duties_with_definitions() -> None:
    duties = {duty.code: duty for duty in ncs_data().duties}

    assert list(duties) == ["20010202", "20010204"]
    assert duties["20010202"].name == "응용SW엔지니어링"
    assert duties["20010202"].definition.startswith("응용SW엔지니어링은")
    assert subdivisions() == ["응용SW엔지니어링", "DB엔지니어링"]
    assert all(units_of(name) for name in subdivisions())


def test_units_have_valid_unique_codes_matching_their_duty() -> None:
    units = ncs_data().units
    codes = [unit.code for unit in units]

    assert all(UNIT_CODE.match(code) for code in codes)
    assert len(codes) == len(set(codes))
    assert all(unit.code.startswith(unit.duty_code) for unit in units)
    assert all(1 <= unit.level <= 8 for unit in units)


def test_texts_are_cleaned() -> None:
    """원본의 깨진 가운뎃점과 앞 번호("1.", "11.")를 떼고 저장한다."""
    for unit in ncs_data().units:
        texts = [unit.name, unit.definition, *unit.evaluation_points]
        for element in unit.elements:
            texts += [element.name, *element.criteria, *element.knowledge, *element.skills, *element.attitudes]
        assert not any("？" in text or "･" in text for text in texts), unit.code
        assert not any(text[:1].isdigit() and "." in text[:4] for text in texts), unit.code
        assert "(구버전)" not in unit.name


def test_each_definition_explains_its_own_unit() -> None:
    """정의는 'OO이란'으로 자기 이름부터 시작한다. 다른 능력단위의 정의가 잘못 들어간 것을 잡는다."""
    for unit in ncs_data().units:
        assert unit.definition.replace(" ", "").startswith(unit.name.replace(" ", "")), unit.code


def test_every_unit_has_elements_with_criteria_and_skills() -> None:
    for unit in ncs_data().units:
        assert unit.elements, unit.code
        assert [element.number for element in unit.elements] == sorted(element.number for element in unit.elements)
        assert all(element.criteria and element.knowledge and element.skills for element in unit.elements), unit.code


def test_server_program_unit_has_full_detail() -> None:
    unit = unit_by_code("2001020211_23v6")

    assert unit is not None
    assert unit.name == "서버프로그램 구현"
    assert unit.level == 5
    assert unit.classification == "정보통신 > 정보기술 > 정보기술개발 > 응용SW엔지니어링"
    assert unit.citation == "NCS 응용SW엔지니어링 · 서버프로그램 구현"
    assert [element.name for element in unit.elements] == [
        "개발환경 구축하기",
        "공통 모듈 구현하기",
        "서버 프로그램 구현하기",
        "배치 프로그램 구현하기",
    ]
    server = unit.elements[2]
    assert server.criteria[0] == "업무 프로세스 맵과 세부 업무 프로세스를 확인할 수 있다."
    assert "데이터베이스 연동 기술" in server.skills
    assert unit.elements[0].skills[:2] == [
        "컴파일러 사용 능력",
        "IDE(Integrated Development Environment) 도구 활용 능력",
    ]
    assert set(unit.scope) >= {"고려사항", "장비 및 도구"}
    assert unit.evaluation_points


def test_basic_competencies_are_grouped() -> None:
    unit = unit_by_code("2001020413_19v4")

    assert unit is not None
    assert unit.name == "SQL활용"
    assert unit.basic_competencies
    assert unit.basic_competencies[0].name == "의사소통능력"
    assert unit.basic_competencies[0].subs


def test_unit_by_code_finds_the_data_version_when_version_differs() -> None:
    unit = unit_by_code("2001020211_19v1")

    assert unit is not None
    assert unit.code == "2001020211_23v6"


def test_unit_by_code_returns_none_for_unknown_code() -> None:
    assert unit_by_code("2001020299_23v6") is None
    assert unit_by_code("서버프로그램 구현") is None


def test_units_of_unknown_subdivision_is_empty() -> None:
    assert units_of("없는 세분류") == []


def test_survey_covers_software_units_but_not_db_units() -> None:
    """DB엔지니어링은 2019년 이후 개선되지 않아 중요도 및 활용도 조사가 없다."""
    surveys = ncs_data().surveys

    assert set(surveys) == {unit.code for unit in units_of("응용SW엔지니어링")}
    assert not any(unit.code in surveys for unit in units_of("DB엔지니어링"))


def test_survey_rates_are_high_middle_low_percentages() -> None:
    for code, survey in ncs_data().surveys.items():
        for rates in (survey.importance, survey.frequency, survey.difficulty):
            assert len(rates) == 3, code
            assert 95 <= sum(rates) <= 101, code


def test_server_program_unit_has_its_survey() -> None:
    survey = ncs_data().surveys["2001020211_23v6"]  # 서버프로그램 구현

    assert survey == NcsSurvey(importance=[40, 40, 19], frequency=[32, 47, 20], difficulty=[18, 58, 23])


def test_survey_score_weights_importance_seven_to_frequency_three() -> None:
    """상 3 · 중 2 · 하 1로 평균 내고 중요도 0.7, 활용빈도 0.3으로 합친다."""
    survey = NcsSurvey(importance=[100, 0, 0], frequency=[0, 0, 100], difficulty=[0, 100, 0])

    assert survey_score(survey) == 0.7 * 3 + 0.3 * 1
    assert survey_score(NcsSurvey(importance=[50, 50, 0], frequency=[50, 50, 0], difficulty=[0, 0, 0])) == 2.5


def test_survey_score_orders_software_units() -> None:
    """조사 점수가 가장 높은 것은 애플리케이션 테스트 수행, 가장 낮은 것은 제품소프트웨어 패키징이다."""
    surveys = ncs_data().surveys
    ranked = sorted(surveys, key=lambda code: -survey_score(surveys[code]))

    assert ranked[0] == "2001020227_23v6"
    assert ranked[-1] == "2001020209_23v6"
    assert survey_score(surveys["2001020211_23v6"]) == pytest.approx(2.1848, abs=1e-4)  # 서버프로그램 구현
