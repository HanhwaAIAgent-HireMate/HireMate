"""사람 채점표 집계: `uv run python tests/eval/report/score_review.py [채점표 경로]`.

경로를 주지 않으면 out/ 아래 가장 최근 평가의 review.csv를 읽는다.

'사람 판정' 칸에 맞음 · 과장 · 틀림 · 근거 없음 · 어색함 가운데 하나를 적은 줄만 센다. 빈 줄은 아직 안 본 문장이다.
문장 정확도 = 맞음 ÷ 채점한 문장, 사실 오류율 = (틀림 + 근거 없음) ÷ 채점한 문장이다.
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

LABELS = ("맞음", "과장", "틀림", "근거 없음", "어색함")
GOAL_ACCURACY = 0.9
GOAL_FACT_ERRORS = 0.0


def main(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    judged = [row for row in rows if row["사람 판정"].strip()]
    unknown = sorted({row["사람 판정"].strip() for row in judged} - set(LABELS))
    if unknown:
        print(f"알 수 없는 판정: {', '.join(unknown)}. 쓸 수 있는 말: {', '.join(LABELS)}")
        return 1
    print(f"채점 {len(judged)} / 전체 {len(rows)}문장")
    if not judged:
        return 0
    total = Counter(row["사람 판정"].strip() for row in judged)
    accuracy = total["맞음"] / len(judged)
    errors = (total["틀림"] + total["근거 없음"]) / len(judged)
    print(f"문장 정확도 {accuracy:.0%} (목표 {GOAL_ACCURACY:.0%} 이상)")
    print(f"사실 오류율 {errors:.0%} (목표 {GOAL_FACT_ERRORS:.0%})")
    print("판정별: " + ", ".join(f"{label} {total[label]}" for label in LABELS))

    by_case: dict[str, Counter[str]] = defaultdict(Counter)
    for row in judged:
        by_case[row["사례"]][row["사람 판정"].strip()] += 1
    print("\n사례별 (맞음 / 채점)")
    for case, counts in sorted(by_case.items()):
        done = sum(counts.values())
        problems = ", ".join(f"{label} {counts[label]}" for label in LABELS[1:] if counts[label])
        print(f"  {case:4} {counts['맞음']}/{done}" + (f"  ← {problems}" if problems else ""))

    wrong = [row for row in judged if row["사람 판정"].strip() in ("틀림", "근거 없음", "과장")]
    if wrong:
        print("\n고칠 문장 (틀림 · 근거 없음 · 과장)")
        for row in wrong:
            memo = f" / 메모: {row['메모']}" if row["메모"].strip() else ""
            print(f"  [{row['사례']} #{row['회차']} {row['위치']}] {row['사람 판정']}: {row['문장']}{memo}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(main(Path(sys.argv[1])))
    runs = sorted((Path(__file__).resolve().parent / "out").glob("*/review.csv"))
    if not runs:
        print("평가 결과가 없다. 먼저 LLM_EVAL=true uv run pytest tests/eval/report -s 로 돌린다.")
        sys.exit(1)
    print(f"채점표: {runs[-1]}")
    sys.exit(main(runs[-1]))
