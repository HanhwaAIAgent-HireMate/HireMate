"""NCS(국가직무능력표준) 능력단위 자료. 공고 작성, 서류 평가, 면접에서 같은 자료를 쓴다.

ncs_units.json은 scripts/ncs_download.py가 공공데이터포털 "한국산업인력공단_국가직무능력표준 정보_GW"(15157547)에서
고른 직무(세분류)의 자료를 받아 만든 것이다. ai 서버는 실행 중에 외부 API를 부르지 않는다 (아키텍처 규칙 9).
직무를 늘리려면 스크립트로 다시 받는다. 출처를 밝히고 쓴다.
"""

import re
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

DATA_FILE = Path(__file__).with_name("ncs_units.json")

UNIT_CODE = re.compile(r"^\d{10}_\d{2}v\d+$")
"""버전까지 붙은 능력단위코드 (예: 2001020211_23v6). 앞 8자리가 세분류, 그다음 두 자리가 능력단위 번호다."""


class NcsModel(BaseModel):
    model_config = ConfigDict(frozen=True, alias_generator=to_camel, validate_by_name=True, validate_by_alias=True)


class NcsElement(NcsModel):
    """능력단위요소 하나와 그 수행준거, 지식 · 기술 · 태도."""

    number: int
    name: str
    criteria: list[str] = Field(description="수행준거. '~할 수 있다' 문장")
    knowledge: list[str]
    skills: list[str]
    attitudes: list[str]


class BasicCompetency(NcsModel):
    """직업기초능력 하나 (예: 의사소통능력)와 하위 능력."""

    name: str
    subs: list[str]


class NcsSurvey(NcsModel):
    """NCS 사이트의 "중요도 및 활용도" 현장 조사. 항목마다 상 · 중 · 하로 답한 응답자 비율(%)이다.

    2019년 이후 개발 · 개선된 능력단위만 조사해서 없는 능력단위가 있다 (예: DB엔지니어링).
    """

    importance: list[int] = Field(description="중요도 상 · 중 · 하 비율")
    frequency: list[int] = Field(description="활용빈도 상 · 중 · 하 비율")
    difficulty: list[int] = Field(description="난이도 상 · 중 · 하 비율")


class NcsUnit(NcsModel):
    """NCS 능력단위 하나. level은 능력단위 수준(1~8)이다."""

    code: str
    name: str
    level: int
    definition: str
    duty_code: str
    major: str
    middle: str
    minor: str
    subdivision: str
    elements: list[NcsElement]
    scope: dict[str, list[str]] = Field(
        description="적용범위 및 작업상황 (고려사항, 자료 및 관련 서류, 장비 및 도구 등)"
    )
    evaluation_points: list[str] = Field(description="평가 시 고려사항")
    basic_competencies: list[BasicCompetency]

    @property
    def classification(self) -> str:
        """대분류 > 중분류 > 소분류 > 세분류."""
        return " > ".join([self.major, self.middle, self.minor, self.subdivision])

    @property
    def citation(self) -> str:
        """근거로 화면에 보여 주는 이름."""
        return f"NCS {self.subdivision} · {self.name}"


class NcsDuty(NcsModel):
    """NCS 직무(세분류). code는 8자리 세분류 코드다."""

    code: str
    name: str
    definition: str


class NcsData(NcsModel):
    """ncs_units.json. retrieved_at은 API에서 받은 날짜다.

    중요도 및 활용도 조사(surveys)는 API가 아니라 NCS 사이트에서 받은 자료라 능력단위와 따로 두고
    출처(survey_source)도 따로 적는다.
    """

    source: str
    survey_source: str = ""
    retrieved_at: str
    duties: list[NcsDuty]
    units: list[NcsUnit]
    surveys: dict[str, NcsSurvey] = Field(default={}, description="능력단위코드 → 조사. 조사한 능력단위만 있다")


@cache
def ncs_data() -> NcsData:
    return NcsData.model_validate_json(DATA_FILE.read_text(encoding="utf-8"))


def subdivisions() -> list[str]:
    """자료에 있는 직무(세분류) 이름. 능력단위코드 순서다."""
    return list(dict.fromkeys(unit.subdivision for unit in ncs_data().units))


def units_of(subdivision: str) -> list[NcsUnit]:
    return [unit for unit in ncs_data().units if unit.subdivision == subdivision]


IMPORTANCE_WEIGHT = 0.7
"""조사 점수에서 중요도의 비중. 나머지는 활용빈도다 (중요도 중심, 활용빈도 보조)."""


def survey_score(survey: NcsSurvey) -> float:
    """중요도와 활용빈도를 각각 상 3 · 중 2 · 하 1로 평균 내 7:3으로 합친 점수 (1~3).

    높을수록 현장에서 중요하고 자주 쓴다고 본 능력단위다. 자격 요건 · 우대 사항을 쓸 때 능력단위의 우선순위가 된다.
    """
    return IMPORTANCE_WEIGHT * _average(survey.importance) + (1 - IMPORTANCE_WEIGHT) * _average(survey.frequency)


def _average(rates: list[int]) -> float:
    high, middle, low = rates
    return (3 * high + 2 * middle + 1 * low) / (high + middle + low)


def unit_by_code(code: str) -> NcsUnit | None:
    """능력단위코드로 찾는다. 모델이 근거로 든 코드가 실제로 있는지 확인할 때 쓴다 (규칙 7).

    버전(_ 뒤)이 다르면 같은 능력단위의 자료 버전으로 찾는다. 모델이 코드를 옮기며 버전을 잘못 적곤 한다.
    """
    units = ncs_data().units
    if exact := next((unit for unit in units if unit.code == code), None):
        return exact
    base = code.split("_")[0]
    return next((unit for unit in units if unit.code.split("_")[0] == base), None) if len(base) == 10 else None
