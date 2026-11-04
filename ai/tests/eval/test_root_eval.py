"""LLM_EVAL=true일 때 실제 모델로 Root Agent의 요청 종류별 흐름을 평가한다 (tests/eval/root_cases.json).

가상 지원자(tests/samples)의 더미 프로필을 DB에 저장해 AI 워커가 미리 분석한 상태를 재현한다.
케이스마다 종류, 대상, 근거 상태가 기대와 맞는지 보고, 모델 호출 수와 걸린 시간을 함께 표로 출력한다.
"""

import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from root_context import SAMPLE_PROFILES, extra_row, make_context, save_sample_profiles
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from hiremate_ai.agents.root.graph import RootThread, run_plan
from hiremate_ai.agents.root.toolkit import profile_toolkit
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Decision, Intent
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, InterviewerMemo, PostingContent, StageType
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm

pytestmark = pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때 실제 모델로 평가한다")

CASES: list[dict[str, Any]] = json.loads((Path(__file__).parent / "root_cases.json").read_text(encoding="utf-8"))
MIN_ACCURACY = 0.8

type Applicants = dict[str, ApplicantDetail]


class CountingLog:
    def __init__(self) -> None:
        self.count = 0

    async def record(self, record: CallRecord) -> None:
        self.count += 1


def case_context(
    applicants: Applicants, company: CompanyProfile, posting: PostingContent, case: dict[str, Any], turn: dict[str, Any]
) -> ChatContext:
    stage = StageType[case.get("stage", "DOCUMENT")]
    context = make_context(
        applicants,
        company,
        posting,
        message=turn["message"],
        stage_type=stage,
        previous_types=(StageType.DOCUMENT,) if stage is StageType.INTERVIEW else (),
        mentions=turn.get("mentions", []),
        checked=turn.get("checked", []),
        selected=turn.get("selected", []),
        extra_rows=[extra_row(name) for name in case.get("extra_rows", [])],
    )
    passed = set(case.get("passed", []))
    # backend는 분석을 마친 지원자의 경력과 마지막 회사를 목록에 싣는다. 더미 프로필 값으로 같은 상태를 만든다
    analyzed = {profile.name: profile.fields for profile in SAMPLE_PROFILES}
    candidates = []
    for index, row in enumerate(context.candidates):
        fields = analyzed.get(row.name) if index < len(applicants) else None
        update: dict[str, Any] = {"decision": Decision.PASS} if row.name in passed and index < len(applicants) else {}
        if fields is not None:
            update |= {"career_years": fields.career_years, "last_company": fields.last_company}
        candidates.append(row.model_copy(update=update))
    by_name = {row.name: row.application_id for row in reversed(context.candidates)}
    memos = {
        by_name[name]: [InterviewerMemo(stage_id=context.stage_id, stage_name=context.stage_name, text=text)]
        for name, text in case.get("memos", {}).items()
    }
    return context.model_copy(
        update={"candidates": candidates, "selectable": case.get("selectable", True), "interviewer_memos": memos}
    )


def failures(plan: ChatPlan, expect: dict[str, Any], context: ChatContext) -> list[str]:
    names = {row.application_id: row.name for row in context.candidates}
    targets = {names[value] for value in plan.targets if value in names}
    answered = {names[item.application_id] for item in plan.items if item.application_id in names}
    questioned = {names[value] for value in plan.question_targets if value in names}
    covered = targets | answered | questioned
    text = " ".join([plan.message, *(item.text for item in plan.items)])
    found: list[str] = []
    if "intent" in expect and plan.intent.value not in expect["intent"]:
        found.append(f"intent {plan.intent.value}")
    if "edit" in expect and (plan.edit.value if plan.edit else None) != expect["edit"]:
        found.append(f"edit {plan.edit}")
    if "targets" in expect:
        actual = targets if plan.intent in (Intent.FIND, Intent.EDIT) else targets | answered
        if actual != set(expect["targets"]):
            found.append(f"targets {sorted(actual)}")
    if not set(expect.get("includes", [])) <= covered:
        found.append(f"includes {sorted(covered)}")
    if set(expect.get("excludes", [])) & (targets | answered):
        found.append(f"excludes {sorted(targets | answered)}")
    if "question_targets" in expect and questioned != set(expect["question_targets"]):
        found.append(f"question_targets {sorted(questioned)}")
    if expect.get("question_replace") is not None and plan.question_replace != expect["question_replace"]:
        found.append(f"question_replace {plan.question_replace}")
    if "question_ncs" in expect and plan.question_ncs != expect["question_ncs"]:
        found.append(f"question_ncs {plan.question_ncs}")
    for name, status in expect.get("statuses", {}).items():
        owned = [
            item for item in plan.items if item.application_id is not None and names.get(item.application_id) == name
        ]
        if any(item.status != status for item in owned):
            found.append(f"status {name}")
    if expect.get("has_check") and not any(item.status == "CHECK" for item in plan.items):
        found.append("no CHECK item")
    if "message_contains" in expect and expect["message_contains"] not in plan.message:
        found.append("message")
    if "not_contains" in expect and expect["not_contains"] in text:
        found.append("not_contains")
    if expect.get("no_items") and plan.items:
        found.append("items")
    return found


async def test_root_cases(
    database_url: str,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    # 앱처럼 연결 풀을 쓴다. 분석 루프가 도구를 함께 부르면 연결도 따로 쓴다
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await save_sample_profiles(session, sample_company, sample_applicants)
        await session.commit()
    rows: list[tuple[str, bool, int, float, str, str]] = []
    for case in CASES:
        log = CountingLog()
        llm = build_llm(log)
        toolkit = profile_toolkit(sessions)
        saver = InMemorySaver()
        context = case_context(sample_applicants, sample_company, sample_posting, case, case["turns"][0])
        thread = RootThread(
            id=f"{context.company.company_id}:{context.stage_id}:{uuid4()}",
            company_id=context.company.company_id,
            stage_id=context.stage_id,
        )
        started = time.monotonic()
        plan = ChatPlan.answer(Intent.CLARIFY, "")
        count = 0
        try:
            for turn in case["turns"]:
                context = case_context(sample_applicants, sample_company, sample_posting, case, turn)
                log.count = 0
                plan = await run_plan(llm, context, toolkit, saver=saver, thread=thread)
                count = log.count
            problems = failures(plan, case["expect"], context)
            if problems:
                problems.append(f"답: {plan.message[:80]}")
        except Exception as error:  # 한 케이스의 오류로 나머지 평가를 멈추지 않는다
            problems = [f"오류 {type(error).__name__}: {error}"[:200]]
        rows.append(
            (case["id"], not problems, count, time.monotonic() - started, plan.intent.value, "; ".join(problems))
        )
    print("\n| 케이스 | 통과 | 마지막 턴 모델 호출 | 시간(초) | 종류 | 어긋난 점 |\n|---|---|---|---|---|---|")
    for case_id, passed, calls, seconds, intent, missed in rows:
        print(f"| {case_id} | {'O' if passed else 'X'} | {calls} | {seconds:.1f} | {intent} | {missed} |")
    await engine.dispose()
    accuracy = sum(passed for _, passed, *_ in rows) / len(rows)
    print(f"\n정확도 {accuracy:.2f} ({sum(passed for _, passed, *_ in rows)}/{len(rows)})")
    assert accuracy >= MIN_ACCURACY
