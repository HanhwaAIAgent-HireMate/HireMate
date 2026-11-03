"""정답 판정표(gold.json)를 사람이 검토하기 쉬운 표(gold_table.md)로 옮긴다.

    uv run python tests/eval/report/make_table.py


gold.json을 고치면 다시 돌린다. 표는 읽기용이고 평가는 gold.json만 읽는다.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYMBOLS = {"MET": "●", "PARTIAL": "◐", "NOT_MET": "○", "UNKNOWN": "?"}
CREDIT = {"MET": 1.0, "PARTIAL": 0.5}


def main() -> None:
    gold = json.loads((HERE / "gold.json").read_text(encoding="utf-8"))
    ids = [criterion["criterionId"] for criterion in gold["criteria"]]
    lines = [
        "# 정답 판정표 검토용",
        "",
        "`gold.json`을 사람이 보기 쉽게 옮긴 표다 (`make_table.py`가 만든다). "
        "● 충족 · ◐ 부분 충족 · ○ 미충족 · ? 확인 필요. ⚠는 경계 판정(아래 목록).",
        "",
        "| 번호 | 이름 | 경력 | " + " | ".join(ids) + " | 자격 | 우대 | 메모 |",
        "|" + "---|" * (len(ids) + 6),
    ]
    for applicant in gold["applicants"]:
        cells = applicant["criteria"]
        years, months = divmod(applicant["careerMonths"], 12)
        career = f"{years}년 {months}개월" if applicant["careerMonths"] else "없음"
        marks = [SYMBOLS[cells[cid]["verdict"]] + ("⚠" if cells[cid]["borderline"] else "") for cid in ids]
        qualification = sum(CREDIT.get(cells[cid]["verdict"], 0) for cid in ids if cid.startswith("Q-"))
        preference = sum(CREDIT.get(cells[cid]["verdict"], 0) for cid in ids if cid.startswith("P-"))
        lines.append(
            f"| {applicant['number']} | {applicant['name']} | {career} | "
            + " | ".join(marks)
            + f" | {qualification:g}/5 | {preference:g}/5 | {applicant['note']} |"
        )
    lines += ["", "## 경계 판정 (먼저 검토할 칸)", ""]
    for applicant in gold["applicants"]:
        for cid in ids:
            cell = applicant["criteria"][cid]
            if cell["borderline"]:
                symbol = SYMBOLS[cell["verdict"]]
                lines.append(f"- **{applicant['name']} {cid}** ({symbol}): {cell['reason']} → {cell['borderline']}")
    (HERE / "gold_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
