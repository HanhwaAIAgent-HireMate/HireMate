"""로컬 NCS 벡터 SQLite 파일을 ai 스키마의 참고자료에 적재한다.

기존 BGE-M3 벡터를 옮기며 다시 임베딩하지 않는다. 실패하면 전체 트랜잭션을 되돌린다.
"""

import argparse
import asyncio
import itertools
from pathlib import Path

from sqlalchemy import text

from hiremate_ai.db.session import session_factory
from hiremate_ai.ncs_search.store import read_reference_source, replace_reference_chunks

EXPECTED = 136_954


async def load(paths: list[Path]) -> int:
    records = itertools.chain.from_iterable(read_reference_source(path) for path in paths)
    async with session_factory()() as session, session.begin():
        count = await replace_reference_chunks(session, records)
        if count != EXPECTED:
            raise ValueError(f"NCS 총 건수 불일치: {count} / {EXPECTED}")
        await session.execute(text("ANALYZE ai.ncs_reference_chunks"))
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs=2)
    args = parser.parse_args()
    print(asyncio.run(load(args.paths)))


if __name__ == "__main__":
    main()
