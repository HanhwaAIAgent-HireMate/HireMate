"""공고 수정 테스트가 같이 쓰는 가짜 NCS 참고 조회와 묶음."""

from hiremate_ai.ncs_search.reference import NcsUnavailable
from hiremate_ai.ncs_search.types import NcsTask, NcsUnit

UNIT = "2001020211_23v6"
OTHER_UNIT = "2001020212_23v6"


def task(chunk_id: str = "chunk:1", sentences: list[str] | None = None, unit: str = UNIT) -> NcsTask:
    return NcsTask(
        chunk_id=chunk_id,
        duty_name="응용SW엔지니어링",
        unit_code=unit,
        unit_name="서버프로그램 구현",
        task_name="서버 프로그램 구현하기",
        sentences=sentences or ["서버 프로그램을 구현 한다"],
    )


def units() -> list[NcsUnit]:
    return [
        NcsUnit(
            code=UNIT, name="서버프로그램 구현", duty_name="응용SW엔지니어링", task_names=["서버 프로그램 구현하기"]
        ),
        NcsUnit(
            code=OTHER_UNIT, name="인터페이스 구현", duty_name="응용SW엔지니어링", task_names=["인터페이스 구현하기"]
        ),
    ]


class FakeNcs:
    """단위 목록과 검색 결과를 정해 두고, 검색에 받은 인자를 기록한다. unavailable이면 검색이 실패한다."""

    def __init__(
        self,
        found: list[NcsTask] | None = None,
        *,
        unit_list: list[NcsUnit] | None = None,
        unavailable: bool = False,
    ) -> None:
        self.found = [task()] if found is None else found
        self.unit_list = units() if unit_list is None else unit_list
        self.unavailable = unavailable
        self.searches: list[tuple[str, list[str], list[str]]] = []

    async def units(self) -> list[NcsUnit]:
        return self.unit_list

    async def search(self, request: str, tasks: list[str], units: list[str]) -> list[NcsTask]:
        self.searches.append((request, tasks, units))
        if self.unavailable:
            raise NcsUnavailable("down")
        return self.found
