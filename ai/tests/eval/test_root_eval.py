"""Root Agent 실제 모델 평가. LLM_EVAL=true일 때만 돈다: `LLM_EVAL=true uv run pytest tests/eval -v -s`.

문항마다 분류 결과를 기대값과 맞춰 보고 종류별 정확도를 출력한다. needs_assessment · needs_interview는
모든 문항에서 확인한다(필요 없는 자료를 표시하면 "아직 평가 결과가 없어요" 같은 잘못된 되묻기로 이어진다).
"""

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from root_context import make_context

from hiremate_ai.agents.root.graph import run_plan
from hiremate_ai.agents.root.route import RootRoute, classify, required_data
from hiremate_ai.agents.root.targets import resolve
from hiremate_ai.agents.root.types import ChatContext, Intent
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm

pytestmark = pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때만 실제 모델로 돈다")

CASES: list[dict[str, Any]] = json.loads((Path(__file__).parent / "root_cases.json").read_text(encoding="utf-8"))
MIN_ACCURACY = 0.8
# 찾기 문항은 같은 질문을 여러 번 돌려 같은 후보가 나오는지 본다
FIND_RUNS = 3


class MemoryCallLog:
    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def record(self, record: CallRecord) -> None:
        self.records.append(record)


def context_for(
    case: dict[str, Any], applicants: dict[str, ApplicantDetail], company: CompanyProfile, posting: PostingContent
) -> ChatContext:
    return make_context(
        applicants,
        company,
        posting,
        message=case["message"],
        stage_type=StageType(case.get("stage_type", "DOCUMENT")),
        previous_types=[StageType(stage) for stage in case.get("previous_types", [])],
        mentions=case.get("mentions", []),
        checked=case.get("checked", []),
    )


def mismatches(route: RootRoute, message: str, expect: dict[str, Any]) -> list[str]:
    """필요한 자료는 precheck가 실제로 쓰는 값(required_data)으로 비교한다."""
    required = required_data(route, message)
    actual = {
        **route.model_dump(mode="json"),
        "needs_assessment": StageType.ASSESSMENT in required,
        "needs_interview": StageType.INTERVIEW in required,
    }
    checked = {"needs_assessment": False, "needs_interview": False, **expect}
    return [f"{key}={actual[key]!r} (기대 {value!r})" for key, value in checked.items() if actual[key] != value]


async def test_root_route_cases(
    sample_applicants: dict[str, ApplicantDetail], sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    llm = build_llm(MemoryCallLog())
    passed: Counter[str] = Counter()
    total: Counter[str] = Counter()
    seconds = []
    for case in CASES:
        context = context_for(case, sample_applicants, sample_company, sample_posting)
        started = time.perf_counter()
        route = await classify(llm, context, resolve(context))
        seconds.append(time.perf_counter() - started)
        wrong = mismatches(route, case["message"], case["expect"])
        kind = case["expect"]["kind"]
        total[kind] += 1
        passed[kind] += not wrong
        print(f"{'OK ' if not wrong else 'BAD'} {seconds[-1]:4.1f}s {case['id']}: {'; '.join(wrong)}")

    for kind in sorted(total):
        print(f"{kind}: {passed[kind]}/{total[kind]}")
    accuracy = sum(passed.values()) / len(CASES)
    print(f"전체 {sum(passed.values())}/{len(CASES)} ({accuracy:.0%}), 평균 {sum(seconds) / len(seconds):.1f}초")
    assert accuracy >= MIN_ACCURACY


async def test_root_find_cases(
    sample_applicants: dict[str, ApplicantDetail], sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    llm = build_llm(MemoryCallLog())
    cases = [case for case in CASES if "include" in case]
    passed = 0
    for case in cases:
        context = context_for(case, sample_applicants, sample_company, sample_posting)
        by_id = {row.application_id: row.name for row in context.candidates}
        runs = []
        started = time.perf_counter()
        for _ in range(FIND_RUNS):
            plan = await run_plan(llm, context)
            runs.append((plan.intent, [by_id[application_id] for application_id in plan.targets]))
        seconds = (time.perf_counter() - started) / FIND_RUNS
        problems = []
        for intent, chosen in runs:
            if intent is not Intent.FIND:
                problems.append(f"intent={intent}")
            if missing := set(case["include"]) - set(chosen):
                problems.append(f"빠짐 {sorted(missing)}")
            if extra := set(case.get("exclude", [])) & set(chosen):
                problems.append(f"섞임 {sorted(extra)}")
        if any(chosen != runs[0][1] for _, chosen in runs):
            problems.append(f"결과가 달라짐 {[chosen for _, chosen in runs]}")
        passed += not problems
        print(f"{'OK ' if not problems else 'BAD'} {seconds:4.1f}s {case['id']}: {runs[0][1]} {'; '.join(problems)}")
    print(f"찾기 {passed}/{len(cases)}")
    assert passed / len(cases) >= MIN_ACCURACY
