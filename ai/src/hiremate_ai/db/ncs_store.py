"""NCS 자료를 DB에 넣고 꺼내는 함수.

- load_ncs: ncs_units.json(NcsData)을 DB에 넣는다. 같은 코드는 내용만 바꾸고 임베딩은 남긴다.
- get_unit · units_of_duty · list_duties: tools/ncs.py와 같은 모양(NcsUnit · NcsDuty)으로 돌려준다.
  Posting Agent가 JSON 대신 DB를 읽게 바꿀 때 받는 쪽 코드를 거의 고치지 않아도 된다.
- units_missing_embedding · set_embedding · nearest_units: 임베딩 담당이 벡터를 채우고,
  직무명으로 능력단위를 찾을 때 쓴다.

커밋은 부르는 쪽이 한다 (db.session 규칙). 이 파일의 함수는 flush까지만 한다.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.db.ncs import (
    EMBEDDING_DIM,
    NcsDutyRow,
    NcsElementRow,
    NcsStatementRow,
    NcsUnitRow,
    StatementKind,
)
from hiremate_ai.tools.ncs import BasicCompetency, NcsData, NcsDuty, NcsElement, NcsUnit

_VERSION = re.compile(r"_(\d{2})v(\d+)$")

# NcsElement의 목록 칸 ↔ 문장 종류
_KIND_FIELDS = {
    StatementKind.CRITERION: "criteria",
    StatementKind.KNOWLEDGE: "knowledge",
    StatementKind.SKILL: "skills",
    StatementKind.ATTITUDE: "attitudes",
}


@dataclass(frozen=True)
class LoadResult:
    """load_ncs가 넣은 것. retired는 새 버전이 들어와 active=False가 된 옛 능력단위 코드다."""

    duties: int
    units: int
    retired: list[str]


@dataclass(frozen=True)
class UnitHit:
    """벡터 검색으로 찾은 능력단위. distance는 코사인 거리(0에 가까울수록 비슷)다."""

    code: str
    name: str
    duty_code: str
    distance: float


# ---------------------------------------------------------------------------
# 넣기
# ---------------------------------------------------------------------------


async def load_ncs(session: AsyncSession, data: NcsData) -> LoadResult:
    """NcsData를 DB에 넣는다. 여러 번 넣어도 결과가 같다 (같은 코드는 덮어쓰기)."""
    # 1) 직무(세분류): 대 · 중 · 소분류 이름은 능력단위에 들어 있으므로 그 직무의 첫 능력단위에서 가져온다
    first_unit = {unit.duty_code: unit for unit in reversed(data.units)}
    for duty in data.duties:
        unit = first_unit.get(duty.code)
        duty_row = await session.get(NcsDutyRow, duty.code) or NcsDutyRow(code=duty.code)
        duty_row.name = duty.name
        duty_row.definition = duty.definition
        duty_row.major = unit.major if unit else ""
        duty_row.middle = unit.middle if unit else ""
        duty_row.minor = unit.minor if unit else ""
        duty_row.source = data.source
        duty_row.retrieved_at = data.retrieved_at
        session.add(duty_row)
    await session.flush()

    # 2) 능력단위: 있으면 내용만 바꾸고(임베딩 유지), 없으면 새로 만든다
    for unit in data.units:
        row = await session.get(NcsUnitRow, unit.code)
        if row is None:
            row = NcsUnitRow(code=unit.code, active=True, embedding=None, elements=[])
            session.add(row)
        else:
            # 이름이나 정의가 바뀌면 예전 글로 만든 벡터는 맞지 않으므로 비운다 (임베딩 담당이 다시 채움)
            if (row.name, row.definition) != (unit.name, unit.definition):
                row.embedding = None
            # 요소를 바꾸기 전에 옛 요소를 먼저 지운다. 같은 번호를 지우고 넣는 일이 한 번에 일어나면
            # (unit_code, number) 고유 제약에 걸리기 때문이다
            if row.elements:
                row.elements.clear()
                await session.flush()
        row.base_code = unit.code.split("_")[0]
        row.duty_code = unit.duty_code
        row.name = unit.name
        row.level = unit.level
        row.definition = unit.definition
        row.scope = unit.scope
        row.evaluation_points = unit.evaluation_points
        row.basic_competencies = [competency.model_dump() for competency in unit.basic_competencies]
        row.retrieved_at = data.retrieved_at
        row.elements = [_element_row(element) for element in unit.elements]
    await session.flush()

    # 3) 버전 정리: 같은 능력단위(base_code)에서 가장 새 버전만 active=True
    retired = await _refresh_active(session, {unit.code.split("_")[0] for unit in data.units})
    return LoadResult(duties=len(data.duties), units=len(data.units), retired=retired)


def _element_row(element: NcsElement) -> NcsElementRow:
    """NcsElement 하나를 요소 행 + 문장 행들로 바꾼다. position은 원래 목록 순서다."""
    statements = [
        NcsStatementRow(kind=kind, position=position, text=text)
        for kind, field in _KIND_FIELDS.items()
        for position, text in enumerate(getattr(element, field))
    ]
    return NcsElementRow(number=element.number, name=element.name, statements=statements)


async def _refresh_active(session: AsyncSession, base_codes: set[str]) -> list[str]:
    """base_code마다 가장 새 버전만 active로 두고, 새로 비활성이 된 코드를 돌려준다."""
    rows = (await session.scalars(select(NcsUnitRow).where(NcsUnitRow.base_code.in_(base_codes)))).all()
    latest: dict[str, NcsUnitRow] = {}
    for row in rows:
        current = latest.get(row.base_code)
        if current is None or _version(row.code) > _version(current.code):
            latest[row.base_code] = row
    retired = []
    for row in rows:
        active = latest[row.base_code] is row
        if row.active and not active:
            retired.append(row.code)
        row.active = active
    await session.flush()
    return sorted(retired)


def _version(code: str) -> tuple[int, int]:
    """'2001020211_23v6' → (23, 6). 버전 표기가 없으면 가장 옛것으로 본다."""
    match = _VERSION.search(code)
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


# ---------------------------------------------------------------------------
# 꺼내기 (tools/ncs.py와 같은 모양)
# ---------------------------------------------------------------------------


async def list_duties(session: AsyncSession) -> list[NcsDuty]:
    """DB에 있는 직무(세분류). 코드 순서다."""
    rows = (await session.scalars(select(NcsDutyRow).order_by(NcsDutyRow.code))).all()
    return [NcsDuty(code=row.code, name=row.name, definition=row.definition) for row in rows]


async def units_of_duty(session: AsyncSession, duty_code: str, *, active_only: bool = True) -> list[NcsUnit]:
    """직무 하나의 능력단위. 기본은 최신 버전만, 코드 순서다."""
    query = select(NcsUnitRow).where(NcsUnitRow.duty_code == duty_code)
    if active_only:
        query = query.where(NcsUnitRow.active)
    rows = (await session.scalars(query.order_by(NcsUnitRow.code))).all()
    duty = await session.get(NcsDutyRow, duty_code)
    return [_to_unit(row, duty) for row in rows]


async def get_unit(session: AsyncSession, code: str) -> NcsUnit | None:
    """능력단위 코드로 찾는다. 버전이 다르면 같은 능력단위의 최신 버전으로 찾는다.

    모델이 근거로 든 코드가 실제로 있는지 확인할 때 쓴다 (규칙 7). tools.ncs.unit_by_code와 같은 동작이다.
    """
    row = await session.get(NcsUnitRow, code)
    base = code.split("_")[0]
    if row is None and len(base) == 10:
        row = await session.scalar(select(NcsUnitRow).where(NcsUnitRow.base_code == base, NcsUnitRow.active))
    if row is None:
        return None
    return _to_unit(row, await session.get(NcsDutyRow, row.duty_code))


def _to_unit(row: NcsUnitRow, duty: NcsDutyRow | None) -> NcsUnit:
    """능력단위 행(+ 요소 · 문장)을 tools.ncs.NcsUnit으로 되돌린다."""
    elements = []
    for element in row.elements:
        # 문장을 종류별로 나누고 원래 순서(position)대로 둔다
        lists: dict[str, list[str]] = {field: [] for field in _KIND_FIELDS.values()}
        for statement in sorted(element.statements, key=lambda statement: (statement.kind, statement.position)):
            lists[_KIND_FIELDS[StatementKind(statement.kind)]].append(statement.text)
        elements.append(
            NcsElement(
                number=element.number,
                name=element.name,
                criteria=lists["criteria"],
                knowledge=lists["knowledge"],
                skills=lists["skills"],
                attitudes=lists["attitudes"],
            )
        )
    return NcsUnit(
        code=row.code,
        name=row.name,
        level=row.level,
        definition=row.definition,
        duty_code=row.duty_code,
        major=duty.major if duty else "",
        middle=duty.middle if duty else "",
        minor=duty.minor if duty else "",
        subdivision=duty.name if duty else "",
        elements=elements,
        scope=row.scope,
        evaluation_points=row.evaluation_points,
        basic_competencies=[BasicCompetency.model_validate(item) for item in row.basic_competencies],
    )


# ---------------------------------------------------------------------------
# 임베딩 (bge-m3 벡터는 임베딩 담당이 만들어 넣는다)
# ---------------------------------------------------------------------------


async def units_missing_embedding(session: AsyncSession) -> list[tuple[str, str]]:
    """아직 벡터가 없는 최신 능력단위의 (코드, 임베딩할 글). 글은 '이름: 정의'다."""
    rows = (
        await session.scalars(
            select(NcsUnitRow).where(NcsUnitRow.active, NcsUnitRow.embedding.is_(None)).order_by(NcsUnitRow.code)
        )
    ).all()
    return [(row.code, f"{row.name}: {row.definition}") for row in rows]


async def set_embedding(session: AsyncSession, code: str, vector: Sequence[float]) -> None:
    """능력단위 하나의 벡터를 넣는다. 차원이 다르면 넣지 않는다."""
    if len(vector) != EMBEDDING_DIM:
        raise ValueError(f"임베딩 차원은 {EMBEDDING_DIM}이어야 한다 (받은 값: {len(vector)})")
    row = await session.get(NcsUnitRow, code)
    if row is None:
        raise KeyError(f"없는 능력단위 코드다: {code}")
    row.embedding = list(vector)
    await session.flush()


async def nearest_units(session: AsyncSession, vector: Sequence[float], *, limit: int = 30) -> list[UnitHit]:
    """벡터와 가장 가까운 최신 능력단위. 직무명으로 능력단위 후보를 찾을 때 쓴다 (공고 작성 '후보 찾기').

    벡터가 아직 없는 능력단위는 빠진다. 같은 거리면 코드 순서라 같은 질문에는 같은 결과가 나온다.
    """
    distance = NcsUnitRow.embedding.cosine_distance(list(vector)).label("distance")
    result = await session.execute(
        select(NcsUnitRow.code, NcsUnitRow.name, NcsUnitRow.duty_code, distance)
        .where(NcsUnitRow.active, NcsUnitRow.embedding.is_not(None))
        .order_by(distance, NcsUnitRow.code)
        .limit(limit)
    )
    return [
        UnitHit(code=code, name=name, duty_code=duty_code, distance=float(dist))
        for code, name, duty_code, dist in result
    ]
