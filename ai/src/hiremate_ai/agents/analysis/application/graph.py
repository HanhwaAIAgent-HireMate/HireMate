"""Application Agent 흐름 (LangGraph). 준비 → 추출 · 합치기 → 판정 → 검토 → 계산.

Application 부분(extract)이 사실과 근거를 뽑고, Assessment 부분(judge · fit)이 공고 조건과 직무 적합도를 본다.
자격요건 · 우대사항(NCS 평가 조건) · 직무 적합도는 동시에 판정하고, 점수는 계산 단계에서 코드가 합친다 (score.py).
입력(지원서 · 공고 · 평가 기준)은 그래프 상태가 아니라 실행 context로 넘긴다. 체크포인터는 쓰지 않는다.
같은 입력이면 저장된 결과를 쓰므로 다시 실행하면 된다.
"""

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from hiremate_ai.agents.analysis.application.career import career_years, last_company
from hiremate_ai.agents.analysis.application.context import readable
from hiremate_ai.agents.analysis.application.extract import extract_documents, merge
from hiremate_ai.agents.analysis.application.fit import judge_fit
from hiremate_ai.agents.analysis.application.judge import PreferenceTask, judge_preferences, judge_qualifications
from hiremate_ai.agents.analysis.application.review import apply_to_facts, fact_claims, review_claims
from hiremate_ai.agents.analysis.application.score import (
    document_score,
    preference_outcome,
    preference_points,
    qualification_passed,
)
from hiremate_ai.agents.analysis.application.types import (
    Actor,
    ApplicationReview,
    CriterionResult,
    Fact,
    FitLine,
    Note,
    Period,
    PreferenceResult,
    PreferenceStatus,
    QualificationResult,
)
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.llm.client import LlmClient

REVIEW_VERSION = "2026-10-21.4"
# 카드의 '눈여겨볼 점' 후보로 검토하는 사실 수
NOTABLE_CANDIDATES = 6
NOTABLE_KINDS = ("ACHIEVEMENT", "PROJECT", "EXPERIENCE")
UNREADABLE = "제출 서류에서 글자를 읽지 못해 평가하지 않았어요. 원본 PDF를 확인해 주세요."
QUALIFICATION_SOURCE = "공고 · 자격요건"
PREFERENCE_SOURCE = "공고 · 우대사항"


@dataclass(frozen=True)
class ReviewInput:
    """한 번의 분석에 쓰는 입력. tasks는 평가 기준과 짝지은 우대사항, related_certificates는 직무 관련 자격증이다."""

    applicant: ApplicantDetail
    posting: PostingContent
    tasks: tuple[PreferenceTask, ...]
    related_certificates: tuple[str, ...]
    input_hash: str
    today: date


class ReviewState(TypedDict, total=False):
    readable: bool
    facts: list[Fact]
    periods: list[Period]
    qualifications: list[QualificationResult]
    criteria: dict[int, list[CriterionResult]]
    fit: list[FitLine]
    review: ApplicationReview


def build_review_graph(llm: LlmClient) -> CompiledStateGraph[ReviewState, ReviewInput, ReviewState, ReviewState]:
    """노드는 llm으로 모델을 부른다. 테스트는 FakeLlm을 넘긴다. 실행할 때 context에 ReviewInput을 준다."""

    def prepare(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        return {"readable": bool(readable(runtime.context.applicant.documents))}

    async def extract(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        context = runtime.context
        documents = readable(context.applicant.documents)
        extracted = await extract_documents(llm, documents, settings.application_concurrency)
        facts, periods = merge(documents, extracted, context.today)
        return {"facts": facts, "periods": periods}

    async def judge(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        context = runtime.context
        documents = readable(context.applicant.documents)
        facts = state.get("facts") or []
        periods = state.get("periods") or []
        full_text = settings.application_full_text_chars
        qualifications, criteria, fit = await asyncio.gather(
            judge_qualifications(
                llm,
                context.posting.qualifications,
                documents,
                facts,
                periods,
                career_years(periods, context.today),
                context.applicant.certificates,
                full_text,
            ),
            judge_preferences(llm, context.tasks, documents, facts, full_text, settings.application_concurrency),
            judge_fit(
                llm,
                context.posting,
                documents,
                facts,
                context.applicant.certificates,
                context.related_certificates,
                full_text,
            ),
        )
        return {"qualifications": qualifications, "criteria": criteria, "fit": fit}

    async def review(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        facts = state.get("facts") or []
        notable = _notable_candidates(facts)
        reviews = await review_claims(llm, fact_claims(notable))
        # notable은 facts의 같은 객체를 고른 것이라 객체 id로 짝을 짓는다 (리스트 필드가 있어 해시할 수 없다)
        reviewed = {id(fact): new for fact, new in zip(notable, apply_to_facts(notable, reviews), strict=True)}
        return {"facts": [reviewed.get(id(fact), fact) for fact in facts]}

    def finalize(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        return {"review": _finalize(state, runtime.context)}

    def after_prepare(state: ReviewState) -> str:
        return "extract" if state.get("readable") else "finalize"

    graph: StateGraph[ReviewState, ReviewInput, ReviewState, ReviewState] = StateGraph(
        ReviewState, context_schema=ReviewInput
    )
    graph.add_node("prepare", prepare)
    graph.add_node("extract", extract)
    graph.add_node("judge", judge)
    graph.add_node("review", review)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", after_prepare)
    graph.add_edge("extract", "judge")
    graph.add_edge("judge", "review")
    graph.add_edge("review", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


async def run_review(llm: LlmClient, context: ReviewInput) -> ApplicationReview:
    state: dict[str, Any] = await build_review_graph(llm).ainvoke({}, context=context)
    result = state.get("review")
    if not isinstance(result, ApplicationReview):
        raise TypeError(f"Application 그래프가 결과를 남기지 않았다: {state.keys()}")
    return result


def _notable_candidates(facts: list[Fact]) -> list[Fact]:
    chosen = [fact for fact in facts if fact.actor == Actor.SELF and fact.kind in NOTABLE_KINDS]
    chosen.sort(key=lambda fact: NOTABLE_KINDS.index(fact.kind))
    return chosen[:NOTABLE_CANDIDATES]


def _finalize(state: ReviewState, context: ReviewInput) -> ApplicationReview:
    application_id: UUID = context.applicant.info.application_id
    if not state.get("readable"):
        return ApplicationReview(
            version=REVIEW_VERSION,
            input_hash=context.input_hash,
            application_id=application_id,
            readable=False,
            held=True,
            holds=[Note(text=UNREADABLE, source="제출 문서")],
        )
    periods = state.get("periods") or []
    qualifications = state.get("qualifications") or []
    criteria = state.get("criteria") or {}
    fit = state.get("fit") or []

    preferences: list[PreferenceResult] = []
    checks: list[Note] = []
    for task in context.tasks:
        results = criteria.get(task.number, [])
        status, value = preference_outcome(results)
        preferences.append(
            PreferenceResult(
                number=task.number,
                text=task.text,
                weight=task.weight,
                unit_code=task.unit.code if task.unit else None,
                unit_name=task.unit.name if task.unit else None,
                criteria=results,
                status=status,
                score=value,
            )
        )
        if status == PreferenceStatus.UNRATED:
            checks.append(
                Note(
                    text=f"우대사항 P{task.number} '{task.text}'은 평가 기준(가중치 · NCS)이 없어 "
                    "점수에 넣지 않았어요.",
                    source=PREFERENCE_SOURCE,
                )
            )
    for result in qualifications:
        if not result.evaluated:
            checks.append(Note(text=f"자격요건 Q{result.number} '{result.text}'은 평가하지 않았어요.", source="공고"))
        elif not result.met:
            checks.append(
                Note(text=f"자격요건 Q{result.number} '{result.text}': {result.reason}", source=QUALIFICATION_SOURCE)
            )
    return ApplicationReview(
        version=REVIEW_VERSION,
        input_hash=context.input_hash,
        application_id=application_id,
        readable=True,
        facts=state.get("facts") or [],
        periods=periods,
        career_years=career_years(periods, context.today),
        last_company=last_company(periods),
        qualifications=qualifications,
        passed=qualification_passed(qualifications),
        preferences=preferences,
        preference_points=preference_points(preferences),
        fit=fit,
        document_score=document_score(preferences, fit),
        checks=checks,
    )
