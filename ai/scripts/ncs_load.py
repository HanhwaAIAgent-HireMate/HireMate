"""src/hiremate_ai/tools/ncs_units.json을 ai 스키마의 NCS 표에 넣는다.

사용법 (ai 폴더에서, 먼저 uv run alembic upgrade head):
    uv run python scripts/ncs_load.py

- DB 주소는 ai/.env의 DATABASE_URL (없으면 로컬 compose 기본값)이다.
- 여러 번 실행해도 결과가 같다. 같은 능력단위는 내용만 바뀌고 임베딩은 남는다 (이름 · 정의가 바뀌면 비움).
- 직무를 늘리려면 scripts/ncs_download.py로 json을 다시 만든 뒤 이 스크립트를 실행한다.
"""

import asyncio

from hiremate_ai.db.ncs_store import load_ncs
from hiremate_ai.db.session import session_factory
from hiremate_ai.tools.ncs import ncs_data


async def main() -> None:
    data = ncs_data()
    factory = session_factory()
    async with factory() as session:
        result = await load_ncs(session, data)
        await session.commit()
    await factory.kw["bind"].dispose()
    print(f"직무 {result.duties}개, 능력단위 {result.units}개를 넣었다 (자료 받은 날짜 {data.retrieved_at}).")
    if result.retired:
        print(f"새 버전이 들어와 비활성이 된 능력단위: {', '.join(result.retired)}")


if __name__ == "__main__":
    # Windows 기본 루프(ProactorEventLoop)에서는 psycopg가 async로 DB에 붙지 못해 SelectorEventLoop로 돌린다
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
