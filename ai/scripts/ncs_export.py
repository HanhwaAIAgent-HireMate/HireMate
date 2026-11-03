"""로컬 NCS 실험 인덱스(ncs_t06)에서 정보기술 '책임 및 역할' 묶음과 벡터를 적재 파일로 내보낸다.

ai 폴더에서: uv run python scripts/ncs_export.py --out ~/Downloads/ncs_tasks.jsonl.gz
다시 임베딩하지 않고 인덱스의 BGE-M3 벡터를 그대로 옮긴다. 만든 파일은 git에 넣지 않고 따로 공유한다.
"""

import argparse
import gzip
import sys
from pathlib import Path

import psycopg

from hiremate_ai.ncs_search.types import NcsTaskRecord, QueryVectors

DSN = "host=127.0.0.1 port=55432 dbname=ncs_t06 user=postgres"
EXPECTED = (2301, 691)
"""정보기술 '책임 및 역할' 묶음 수와 능력단위 수."""

QUERY = """
SELECT chunk_id, embedding_text, context, dense::real[], sparse::text
FROM ncs_experiment.chunks
WHERE left(context->>'duty_code', 4) = '2001' AND context->>'kind_code' = 'report_responsibility'
ORDER BY chunk_id
"""


def sentences(embedding_text: str) -> list[str]:
    """임베딩 글은 머리(직무 분야, 능력단위, 주요 업무, 내용 종류)와 빈 줄 뒤의 문장들이다."""
    _, _, body = embedding_text.partition("\n\n")
    return [line.strip() for line in body.splitlines() if line.strip()]


def sparse(literal: str) -> dict[int, float]:
    """pgvector sparsevec 글('{1:0.5,8:0.2}/250002', 1부터 센 번호)을 0부터 센 번호로 바꾼다."""
    pairs = literal.split("}", 1)[0].lstrip("{")
    return {int(key) - 1: float(value) for key, value in (pair.split(":") for pair in pairs.split(",") if pair)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DSN)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    units: set[str] = set()
    count = 0
    with psycopg.connect(args.dsn) as db, gzip.open(args.out, "wt", encoding="utf-8") as out:
        for chunk_id, text, context, dense, sparse_text in db.execute(QUERY):
            record = NcsTaskRecord(
                chunk_id=chunk_id,
                duty_code=context["duty_code"],
                duty_name=context["duty_name"],
                unit_code=context["unit_code"],
                unit_name=context["unit_name"],
                task_name=context["group_label"],
                sentences=sentences(text),
                vectors=QueryVectors(dense=dense, sparse=sparse(sparse_text)),
            )
            out.write(record.model_dump_json() + "\n")
            units.add(record.unit_code)
            count += 1
    print(count, len(units))
    if (count, len(units)) != EXPECTED:
        sys.exit(f"묶음 · 능력단위 수가 {EXPECTED}와 다릅니다.")


if __name__ == "__main__":
    main()
