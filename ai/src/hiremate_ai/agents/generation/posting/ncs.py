"""Posting Agent가 자격 요건 · 우대 사항 초안의 근거로 쓰는 NCS 능력단위.

ncs_units.json은 공공데이터포털의 공통 NCS 정보 API(15150267)에서 능력단위 전체를 한 번 받아,
시연 직무의 세분류만 뽑은 것이다. ai 서버는 실행 중에 외부 API를 부르지 않는다 (아키텍처 규칙 9).
직무를 늘리려면 API에서 다시 받아 세분류를 더해 뽑는다. 뽑을 때 원본을 이렇게 다듬었다.

- 가운뎃점(·)이 전각 물음표(？)로 깨진 곳을 되돌렸다 (예: 유지？관리 → 유지·관리).
- 이름에 (구버전)이 붙은 능력단위는 뺐다. 새 능력단위로 바뀐 것이고,
  정의가 다른 능력단위의 것으로 잘못 들어 있기도 하다.
"""

import re
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DATA_FILE = Path(__file__).with_name("ncs_units.json")

UNIT_CODE = re.compile(r"^\d{10}_\d{2}v\d+$")
"""버전까지 붙은 능력단위코드 (예: 2001020211_23v6). 앞 8자리가 세분류, 뒤 두 자리가 능력단위 번호다."""


class NcsUnit(BaseModel):
    """NCS 능력단위 하나. level은 능력단위 수준(1~8)이다."""

    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    level: int
    definition: str
    major: str
    middle: str
    minor: str
    subdivision: str

    @property
    def classification(self) -> str:
        """대분류 > 중분류 > 소분류 > 세분류."""
        return " > ".join([self.major, self.middle, self.minor, self.subdivision])

    @property
    def citation(self) -> str:
        """초안의 근거로 화면에 보여 주는 이름."""
        return f"NCS {self.subdivision} · {self.name}"


class NcsData(BaseModel):
    """ncs_units.json. retrieved_at은 API에서 받은 날짜다."""

    model_config = ConfigDict(frozen=True)

    source: str
    retrieved_at: str = Field(alias="retrievedAt")
    units: list[NcsUnit]


@cache
def ncs_data() -> NcsData:
    return NcsData.model_validate_json(DATA_FILE.read_text(encoding="utf-8"))


def subdivisions() -> list[str]:
    """자료에 있는 세분류 이름. 능력단위코드 순서다."""
    return list(dict.fromkeys(unit.subdivision for unit in ncs_data().units))


def units_of(subdivision: str) -> list[NcsUnit]:
    return [unit for unit in ncs_data().units if unit.subdivision == subdivision]


def unit_by_code(code: str) -> NcsUnit | None:
    """능력단위코드로 찾는다. 모델이 근거로 든 코드가 실제로 있는지 확인할 때 쓴다 (규칙 7)."""
    return next((unit for unit in ncs_data().units if unit.code == code), None)
