"""Report Agent 실제 모델 평가. LLM_EVAL=true일 때만 돈다: `LLM_EVAL=true uv run pytest tests/eval/report -s`.

사례(cases.json)마다 RUNS번 리포트를 만들고 정답 판정표(gold.json)와 맞춰 자동 채점한다. 결과는 돌릴 때마다
out/<날짜-시간>/에 따로 남아, 채우던 사람 채점표를 덮어쓰지 않는다.
- summary.json: 사례별 · 전체 지표와 위반 목록
- runs.json: 회차마다 센 값과 다시 쓰게 한 까닭
- review.csv: 사람 채점표. '사람 판정' 칸을 채운 뒤 score_review.py로 집계한다
- outputs.jsonl: 회차마다 모델이 낸 설계서 · 해설 원본
지원자는 모두 가상 인물이라 외부 모델로 보내도 된다.
"""

import json
import logging
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from hiremate_ai.agents.generation.report import compose_report, explain_distribution
from hiremate_ai.config import settings
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm

from .dataset import bundle, cases, distribution
from .scoring import TARGETS, RunScore, review_rows, score_distribution, score_report, summarize, write_review

pytestmark = [
    pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때만 실제 모델로 돈다"),
    pytest.mark.asyncio(loop_scope="module"),
]

RUNS = 3
"""사례마다 돌리는 횟수. 모델은 같은 입력에도 다르게 답하므로 한 번으로는 정확도를 말할 수 없다."""
ROOT = Path(__file__).resolve().parent / "out"


class Rewrites(logging.Handler):
    """compose가 남기는 '설계서 검사에 걸림' 로그. 첫 시도에 통과하지 못한 까닭이다."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if "검사에 걸림" in record.getMessage():
            self.messages.append(record.getMessage().split(": ", 1)[-1])


class MemoryCallLog:
    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def record(self, record: CallRecord) -> None:
        self.records.append(record)


async def test_report_agent_matches_gold() -> None:
    llm = build_llm(MemoryCallLog())
    compose_log = logging.getLogger("hiremate_ai.agents.generation.report.compose")
    compose_log.setLevel(logging.INFO)
    scores: list[RunScore] = []
    rows: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    for case in cases():
        for run in range(1, RUNS + 1):
            rewrites = Rewrites()
            compose_log.addHandler(rewrites)
            try:
                if case.kind == "DISTRIBUTION":
                    assert case.target is not None
                    facts = distribution(case.target)
                    note = await explain_distribution(facts, llm)
                    score = score_distribution(case, facts, note, run)
                    rows += review_rows(case, None, score)
                    output: dict[str, Any] = note.model_dump(mode="json")
                else:
                    data = bundle(case)
                    composed = await compose_report(data, llm)
                    score = score_report(case, data, composed, run)
                    rows += review_rows(case, data, score)
                    output = {"spec": composed.spec.model_dump(mode="json"), "steps": composed.steps}
            finally:
                compose_log.removeHandler(rewrites)
            score.rewrites = rewrites.messages
            outputs.append({"case": case.id, "run": run, **output})
            scores.append(score)
            print(f"{case.id} #{run}: 위반 {len(score.violations)}건, 기본 구성 {score.fallback}")

    ROOT.mkdir(exist_ok=True)
    (ROOT / ".gitignore").write_text("*\n", encoding="utf-8")
    OUT = ROOT / datetime.now().strftime("%Y%m%d-%H%M")
    OUT.mkdir()
    write_review(OUT / "review.csv", rows)
    lines = [json.dumps(line, ensure_ascii=False) for line in outputs]
    (OUT / "outputs.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    overall = summarize(scores)
    by_case = {case.id: summarize([s for s in scores if s.case == case.id]) for case in cases()}
    violations = [f"{s.case} #{s.run} {v}" for s in scores for v in s.violations]
    report = {"model": settings.llm_model, "runs": RUNS, "overall": overall, "cases": by_case, "violations": violations}
    (OUT / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "runs.json").write_text(
        json.dumps([{**asdict(s), "sentences": len(s.sentences)} for s in scores], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n모델 {settings.llm_model} · 사례 {len(by_case)}개 × {RUNS}번")
    for name, value in overall.items():
        goal = TARGETS.get(name)
        if value is None:
            print(f"  {name:18} 측정 안 됨 (잴 문장이 없었다. 사람 채점으로 본다)")
            continue
        mark = "" if goal is None else (" ✓" if (value <= goal if name == "fallback_rate" else value >= goal) else " ✗")
        print(f"  {name:18} {value:.2f}" + (f" (목표 {goal:.2f}){mark}" if goal is not None else ""))
    reasons = Counter(reason.split(":")[0] for s in scores for message in s.rewrites for reason in message.split(" | "))
    for reason, count in reasons.most_common(8):
        print(f"  다시 쓰게 한 까닭 {count}번: {reason}")
    for score in scores:
        for line in score.misplaced:
            print(f"  다른 차트 숫자: {score.case} #{score.run} {line}")
    for line in violations:
        print(f"  위반: {line}")
    print(f"사람 채점표: {OUT / 'review.csv'}")

    assert not violations, f"금지 표현 · 숫자 · 말투 위반 {len(violations)}건"
    failed = [
        name
        for name, goal in TARGETS.items()
        if (value := overall[name]) is not None and (value > goal if name == "fallback_rate" else value < goal)
    ]
    assert not failed, f"목표에 못 미친 지표: {', '.join(failed)}"
