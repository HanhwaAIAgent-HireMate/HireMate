"""NCS 적재 파일(scripts/ncs_export.py가 만든 것)을 ai DB의 ai.ncs_tasks 표에 통째로 바꿔 넣는다.

ai 폴더에서: uv run alembic upgrade head && uv run python scripts/ncs_load.py ~/Downloads/ncs_tasks.jsonl.gz
DB 주소는 ai/.env의 DATABASE_URL을 쓴다.
"""

import argparse
import asyncio
from pathlib import Path

from hiremate_ai.db.session import session_factory
from hiremate_ai.ncs_search.store import read_export, replace_tasks


async def load(path: Path) -> int:
    records = read_export(path)
    async with session_factory()() as session:
        count = await replace_tasks(session, records)
        await session.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(asyncio.run(load(args.path)))


if __name__ == "__main__":
    main()
