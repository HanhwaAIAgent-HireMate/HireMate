"""우대사항 판정에 쓰는 NCS 평가 조건. 능력단위의 수행준거 한 문장이 평가 조건 하나다.

능력단위는 ai 스키마의 NCS 표(db.ncs)에서 읽는다. 적재는 scripts/ncs_load.py로 한다.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.db.ncs_store import get_unit
from hiremate_ai.tools.ncs import NcsUnit


@dataclass(frozen=True)
class Criterion:
    no: str  # 능력단위요소 번호-수행준거 순서 (예: 1-2)
    element: str  # 능력단위요소 (예: 인터페이스 요구사항 확인하기)
    text: str  # 수행준거 ('~할 수 있다')


def criteria_of(unit: NcsUnit) -> list[Criterion]:
    return [
        Criterion(no=f"{element.number}-{order}", element=element.name, text=text)
        for element in unit.elements
        for order, text in enumerate(element.criteria, start=1)
    ]


async def ncs_units(session: AsyncSession, codes: Sequence[str]) -> dict[str, NcsUnit]:
    """능력단위코드마다 능력단위를 읽는다. 키는 요청한 코드이고, 없는 코드는 빠진다.

    버전(_ 뒤)이 다르면 같은 능력단위의 최신 버전으로 찾는다 (ncs_store.get_unit).
    """
    found: dict[str, NcsUnit] = {}
    for code in dict.fromkeys(codes):
        unit = await get_unit(session, code)
        if unit is not None:
            found[code] = unit
    return found
