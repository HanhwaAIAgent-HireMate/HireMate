"""Application Agent 흐름 (LangGraph). 준비 → 추출 · 합치기 → 판정 → 검증 → 재확인 → 계산.

Application 부분(extract)은 사실 · 본인 역할 · 수행 범위 · 근거 · 경력 기간을 뽑고 점수를 매기지 않는다.
Assessment 부분(judge)은 자격요건 · 우대사항을 같은 판정 체계로 판정한다. 검증은 인용이 있는 충족 · 부분 충족
판정이 근거로 받쳐지는지 보고, 재확인은 확인 필요(UNKNOWN) 항목만 1차(주변 문맥 · 본인 역할) · 2차(다른 제출 문서)로
다시 판정한다. 점수는 계산 단계에서 코드가 합친다 (score.py). 확인 필요가 남으면 총점을 보류한다.
입력은 그래프 상태가 아니라 실행 context로 넘긴다. 체크포인터는 쓰지 않는다. 같은 입력이면 저장된 결과를 쓴다.
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
from hiremate_ai.agents.analysis.application.extract import extract_documents, extraction_recipe, merge, summarize
from hiremate_ai.agents.analysis.application.judge import (
    Evidence,
    apply_verification,
    judge_criteria,
    recheck_criterion,
    verification_claims,
)
from hiremate_ai.agents.analysis.application.review import apply_to_facts, fact_claims, review_claims
from hiremate_ai.agents.analysis.application.score import qualification_pass, scores
from hiremate_ai.agents.analysis.application.types import (
    VERDICT_LABEL,
    Actor,
    ApplicationReview,
    Criterion,
    CriterionResult,
    DocumentSection,
    Fact,
    Note,
    Period,
)
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CriterionCategory, PostingContent, ScoreStatus, Verdict
from hiremate_ai.db.analysis_store import AnalysisArtifactStore
from hiremate_ai.llm.client import LlmClient

REVIEW_VERSION = "2026-10-26.1"
# 카드의 '눈여겨볼 점' 후보로 검토하는 사실 수
NOTABLE_CANDIDATES = 6
NOTABLE_KINDS = ("ACHIEVEMENT", "PROJECT", "EXPERIENCE")
UNREADABLE = "제출 서류에서 글자를 읽지 못해 평가하지 않았어요. 원본 PDF를 확인해 주세요."
CATEGORY_SOURCE = {CriterionCategory.QUALIFICATION: "공고 · 자격요건", CriterionCategory.PREFERENCE: "공고 · 우대사항"}


@dataclass(frozen=True)
class ReviewInput:
    """한 번의 분석에 쓰는 입력. criteria는 공고와 짝지은 평가 항목, notes는 짝짓기에서 나온 알림이다.

    deadline은 이벤트 루프 시각으로 본 분석 마감이다. 재확인은 남은 시간을 보고 줄인다.
    """

    applicant: ApplicantDetail
    posting: PostingContent
    criteria: tuple[Criterion, ...]
    criteria_version: str
    notes: tuple[Note, ...]
    input_hash: str
    today: date
    deadline: float | None = None
    company_id: UUID | None = None
    artifacts: AnalysisArtifactStore | None = None


class ReviewState(TypedDict, total=False):
    readable: bool
    facts: list[Fact]
    periods: list[Period]
    sections: list[DocumentSection]
    results: list[CriterionResult]
    review: ApplicationReview


def build_review_graph(llm: LlmClient) -> CompiledStateGraph[ReviewState, ReviewInput, ReviewState, ReviewState]:
    """노드는 llm으로 모델을 부른다. 테스트는 FakeLlm을 넘긴다. 실행할 때 context에 ReviewInput을 준다."""

    def prepare(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        return {"readable": bool(readable(runtime.context.applicant.documents))}

    async def extract(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        context = runtime.context
        documents = readable(context.applicant.documents)
        artifacts = context.artifacts
        recipe = extraction_recipe(llm)
        cached = None
        if artifacts is not None and recipe is not None and context.company_id is not None:
            cached = [
                await artifacts.find_extraction(
                    company_id=context.company_id,
                    recruitment_id=context.applicant.info.recruitment_id,
                    application_id=context.applicant.info.application_id,
                    document=document,
                    recipe_hash=recipe,
                )
                for document in documents
            ]
        extracted, sections = await asyncio.gather(
            extract_documents(llm, documents, settings.application_concurrency, cached=cached),
            summarize(llm, documents),
        )
        if artifacts is not None and recipe is not None and context.company_id is not None:
            for document, result in zip(documents, extracted, strict=True):
                await artifacts.save_extraction(
                    company_id=context.company_id,
                    recruitment_id=context.applicant.info.recruitment_id,
                    application_id=context.applicant.info.application_id,
                    document=document,
                    recipe_hash=recipe,
                    extracted=result,
                )
        facts, periods = merge(documents, extracted, context.today)
        return {"facts": facts, "periods": periods, "sections": sections}

    async def judge(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        evidence = _evidence(state, runtime.context)
        results = await judge_criteria(llm, runtime.context.criteria, evidence, settings.application_full_text_chars)
        return {"results": results}

    async def verify(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        """카드에 보일 사실과, 인용이 있는 충족 · 부분 충족 판정을 한 번에 검증한다."""
        facts = state.get("facts") or []
        results = state.get("results") or []
        notable = _notable_candidates(facts)
        reviews = await review_claims(llm, [*fact_claims(notable), *verification_claims(results)])
        # notable은 facts의 같은 객체를 고른 것이라 객체 id로 짝을 짓는다 (리스트 필드가 있어 해시할 수 없다)
        reviewed = {id(fact): new for fact, new in zip(notable, apply_to_facts(notable, reviews), strict=True)}
        return {
            "facts": [reviewed.get(id(fact), fact) for fact in facts],
            "results": apply_verification(results, reviews),
        }

    async def recheck(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        """확인 필요 항목만 1차 · 2차로 다시 판정한다. 항목마다 최대 settings.application_rechecks번, 시간 안에서."""
        context = runtime.context
        evidence = _evidence(state, context)
        criteria = {criterion.criterion_id: criterion for criterion in context.criteria}
        results = list(state.get("results") or [])
        gate = asyncio.Semaphore(settings.application_concurrency)

        async def one(result: CriterionResult, round_no: int) -> CriterionResult:
            criterion = criteria.get(result.criterion_id)
            if criterion is None or result.verdict != Verdict.UNKNOWN or result.certificate_status is not None:
                return result
            async with gate:
                again = await recheck_criterion(llm, criterion, result, evidence, round_no)
            return again or result

        for round_no in range(1, settings.application_rechecks + 1):
            if not any(result.verdict == Verdict.UNKNOWN for result in results) or not _has_time(context):
                break
            results = list(await asyncio.gather(*(one(result, round_no) for result in results)))
        return {"results": results}

    def finalize(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        return {"review": _finalize(state, runtime.context)}

    def after_prepare(state: ReviewState) -> str:
        return "extract" if state.get("readable") else "finalize"

    def after_verify(state: ReviewState) -> str:
        unknown = any(result.verdict == Verdict.UNKNOWN for result in state.get("results") or [])
        return "recheck" if unknown and settings.application_rechecks > 0 else "finalize"

    graph: StateGraph[ReviewState, ReviewInput, ReviewState, ReviewState] = StateGraph(
        ReviewState, context_schema=ReviewInput
    )
    graph.add_node("prepare", prepare)
    graph.add_node("extract", extract)
    graph.add_node("judge", judge)
    graph.add_node("verify", verify)
    graph.add_node("recheck", recheck)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", after_prepare)
    graph.add_edge("extract", "judge")
    graph.add_edge("judge", "verify")
    graph.add_conditional_edges("verify", after_verify)
    graph.add_edge("recheck", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


async def run_review(llm: LlmClient, context: ReviewInput) -> ApplicationReview:
    state: dict[str, Any] = await build_review_graph(llm).ainvoke({}, context=context)
    result = state.get("review")
    if not isinstance(result, ApplicationReview):
        raise TypeError(f"Application 그래프가 결과를 남기지 않았다: {state.keys()}")
    return result


def _evidence(state: ReviewState, context: ReviewInput) -> Evidence:
    return Evidence(
        documents=readable(context.applicant.documents),
        facts=state.get("facts") or [],
        periods=state.get("periods") or [],
        certificates=context.applicant.certificates,
        today=context.today,
    )


def _has_time(context: ReviewInput) -> bool:
    if context.deadline is None:
        return True
    return context.deadline - asyncio.get_running_loop().time() > settings.application_recheck_reserve_seconds


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
            criteria_version=context.criteria_version,
            score_status=ScoreStatus.HELD,
            holds=[Note(text=UNREADABLE, source="제출 문서")],
            checks=list(context.notes),
        )
    periods = state.get("periods") or []
    results = state.get("results") or []
    computed = scores(results)
    status, rate = qualification_pass(results)
    holds = [
        Note(
            text=f"{result.criterion_id} '{result.text}' {VERDICT_LABEL[Verdict.UNKNOWN]}: {result.reason}",
            source=CATEGORY_SOURCE[result.category],
        )
        for result in results
        if result.verdict == Verdict.UNKNOWN
    ]
    if not results:
        holds.append(Note(text="평가할 자격요건 · 우대사항이 없어 점수를 매기지 않았어요.", source="공고"))
    checks = list(context.notes)
    checks += [
        Note(
            text=f"{result.criterion_id} '{result.text}': {result.reason}",
            source=CATEGORY_SOURCE[result.category],
        )
        for result in results
        if result.verdict in (Verdict.NOT_MET, Verdict.PARTIAL) and result.category == CriterionCategory.QUALIFICATION
    ]
    return ApplicationReview(
        version=REVIEW_VERSION,
        input_hash=context.input_hash,
        application_id=application_id,
        readable=True,
        criteria_version=context.criteria_version,
        facts=state.get("facts") or [],
        periods=periods,
        sections=state.get("sections") or [],
        career_years=career_years(periods, context.today) if periods else None,
        last_company=last_company(periods),
        criteria=results,
        qualification_status=status,
        qualification_rate=rate,
        qualification_score=computed.qualification_score,
        qualification_max=computed.qualification_max,
        preference_score=computed.preference_score,
        preference_max=computed.preference_max,
        score_status=ScoreStatus.CONFIRMED if computed.total is not None and not holds else ScoreStatus.HELD,
        document_score=computed.total if not holds else None,
        holds=holds,
        checks=checks,
    )
