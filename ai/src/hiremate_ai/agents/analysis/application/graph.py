"""Application Agent 흐름 (LangGraph). 준비 → 서류 읽기 → 종합 판정 → 검증 → 재판정 → 정리.

모델 호출은 지원자당 서류 수 + 2번(+ 재판정 1번)이다.
- 서류 읽기(read): 서류마다 한 번, 사실 · 본인 역할 · 근거 · 경력 기간 추출과 그 서류의 정리(요약)를 함께 받는다.
- 종합 판정(assess): 서류 전체를 한 번 보고 자격요건 · 우대사항 판정, 성과 장부, 주의 신호, 직무 관련 경력을 받는다.
- 검증(verify): 종합 판정과 다른 호출로, 인용이 있는 충족 · 부분 충족 판정 · 눈여겨볼 사실 · 성과를 검토하고
  검토를 통과한 본인 경험으로 눈여겨볼 점을 묶는다.
- 재판정(recheck): 확인 필요(UNKNOWN)로 남은 항목만 모아 한 번 다시 판정한다.
점수는 매기지 않고, 정리 단계에서 확인 필요로 남은 항목을 모은다.
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

from hiremate_ai.agents.analysis.application.achievements import (
    achievement_claims,
    apply_achievement_reviews,
    attach,
)
from hiremate_ai.agents.analysis.application.assess import assess
from hiremate_ai.agents.analysis.application.career import career_years, last_company
from hiremate_ai.agents.analysis.application.context import readable
from hiremate_ai.agents.analysis.application.extract import merge
from hiremate_ai.agents.analysis.application.highlight import TEAM_ROLE_CHECK
from hiremate_ai.agents.analysis.application.job_career import JobFit, job_notes, job_periods
from hiremate_ai.agents.analysis.application.judge import (
    Evidence,
    apply_verification,
    recheck_criteria,
    verification_claims,
)
from hiremate_ai.agents.analysis.application.reading import read_documents, reading_recipe, reading_type
from hiremate_ai.agents.analysis.application.review import fact_claims
from hiremate_ai.agents.analysis.application.types import (
    VERDICT_LABEL,
    Achievement,
    Actor,
    ApplicationReview,
    Criterion,
    CriterionResult,
    DocumentDigest,
    DocumentSection,
    Fact,
    Note,
    Period,
)
from hiremate_ai.agents.analysis.application.verify import verify as verify_claims
from hiremate_ai.agents.analysis.application.warnings import code_warnings
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CriterionCategory, PostingContent, Verdict
from hiremate_ai.db.analysis_store import AnalysisArtifactStore
from hiremate_ai.llm.client import LlmClient

REVIEW_VERSION = "2026-11-10.4"
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
    digests: list[DocumentDigest]
    # 지원자 단위 성과 장부. 항목의 지표는 여기서 연결된 성과로만 붙인다
    achievements: list[Achievement]
    results: list[CriterionResult]
    notable: list[Note]
    warnings: list[Note]
    job_fit: dict[int, JobFit] | None
    review: ApplicationReview


def build_review_graph(llm: LlmClient) -> CompiledStateGraph[ReviewState, ReviewInput, ReviewState, ReviewState]:
    """노드는 llm으로 모델을 부른다. 테스트는 FakeLlm을 넘긴다. 실행할 때 context에 ReviewInput을 준다."""

    def prepare(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        return {"readable": bool(readable(runtime.context.applicant.documents))}

    async def read(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        context = runtime.context
        documents = readable(context.applicant.documents)
        artifacts = context.artifacts
        recipe = reading_recipe(llm)
        stored = artifacts is not None and recipe is not None and context.company_id is not None
        cached = None
        if stored:
            assert artifacts is not None and recipe is not None and context.company_id is not None
            cached = [
                await artifacts.find_reading(
                    reading_type(document),
                    company_id=context.company_id,
                    recruitment_id=context.applicant.info.recruitment_id,
                    application_id=context.applicant.info.application_id,
                    document=document,
                    recipe_hash=recipe,
                )
                for document in documents
            ]
        readings, answers = await read_documents(
            llm, documents, settings.application_concurrency, blind=context.posting.blind, cached=cached
        )
        if stored:
            assert artifacts is not None and recipe is not None and context.company_id is not None
            for document, answer, saved in zip(documents, answers, cached or [], strict=True):
                if answer is not None and saved is None:
                    await artifacts.save_reading(
                        answer,
                        company_id=context.company_id,
                        recruitment_id=context.applicant.info.recruitment_id,
                        application_id=context.applicant.info.application_id,
                        document=document,
                        recipe_hash=recipe,
                    )
        facts, periods = merge(
            documents, [reading.extracted for reading in readings], context.today, blind=context.posting.blind
        )
        return {
            "facts": facts,
            "periods": periods,
            "sections": [section for reading in readings for section in reading.sections],
            "digests": [reading.digest for reading in readings if reading.digest is not None],
        }

    async def judge(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        """항목 판정 · 성과 장부 · 주의 신호 · 직무 관련 경력을 한 번에 받는다."""
        context = runtime.context
        found = await assess(llm, context.criteria, _evidence(state, context), context.posting)
        return {
            "results": found.results,
            "achievements": found.achievements,
            "warnings": found.warnings,
            "job_fit": found.job_fit,
        }

    async def verify(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        """카드에 보일 사실, 인용이 있는 충족 · 부분 충족 판정, 성과를 한 번에 검토하고 눈여겨볼 점을 묶는다."""
        facts = state.get("facts") or []
        results = state.get("results") or []
        documents = runtime.context.applicant.documents
        achievements = state.get("achievements") or []
        # 눈여겨볼 점 후보 사실. 번호는 사실 목록 전체의 위치라 묶을 경험과 같은 번호를 쓴다
        numbers = _notable_numbers(facts)
        # 판정 검증은 그 항목에 연결된 성과 문장까지 근거로 본다 (구현 문장만 보고 운영 · 성과를 과장이라 보지 않게).
        # 성과 자체는 항목마다가 아니라 성과마다 한 번 검증한다
        claims = [
            *fact_claims([facts[number - 1] for number in numbers], numbers),
            *verification_claims(attach(results, achievements, metric=False), documents, runtime.context.criteria),
            *achievement_claims(achievements, documents),
        ]
        checked = await verify_claims(llm, facts, numbers, claims, readable(documents))
        achievements = apply_achievement_reviews(achievements, checked.reviews)
        return {
            "facts": checked.facts,
            "achievements": achievements,
            "results": attach(apply_verification(results, checked.reviews), achievements),
            # 검토를 통과한 본인 경험을 같은 일끼리 묶은 눈여겨볼 점
            "notable": checked.notable,
        }

    async def recheck(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        """확인 필요 항목만 모아 한 번 다시 판정한다 (분석 시간 안에서)."""
        context = runtime.context
        results = list(state.get("results") or [])
        if _has_time(context):
            results = await recheck_criteria(llm, context.criteria, results, _evidence(state, context))
        # 재판정으로 충족이 된 항목에도 같은 장부의 성과를 붙인다
        return {"results": attach(results, state.get("achievements") or [])}

    def finalize(state: ReviewState, runtime: Runtime[ReviewInput]) -> ReviewState:
        return {"review": _finalize(state, runtime.context)}

    def after_prepare(state: ReviewState) -> str:
        return "read" if state.get("readable") else "finalize"

    def after_verify(state: ReviewState) -> str:
        unknown = any(result.verdict == Verdict.UNKNOWN for result in state.get("results") or [])
        return "recheck" if unknown and settings.application_rechecks > 0 else "finalize"

    graph: StateGraph[ReviewState, ReviewInput, ReviewState, ReviewState] = StateGraph(
        ReviewState, context_schema=ReviewInput
    )
    graph.add_node("prepare", prepare)
    graph.add_node("read", read)
    graph.add_node("judge", judge)
    graph.add_node("verify", verify)
    graph.add_node("recheck", recheck)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", after_prepare)
    graph.add_edge("read", "judge")
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
    """판정 자료. 종합 판정 전에는 뽑은 기간 전체를, 직무 관련 경력을 고른 뒤(재판정)에는 그 기간만 경력표에 둔다
    (경력 기간 항목과 경력 연수의 기준을 맞춘다)."""
    periods = state.get("periods") or []
    return Evidence(
        documents=readable(context.applicant.documents),
        facts=state.get("facts") or [],
        periods=job_periods(periods, state.get("job_fit")) if "job_fit" in state else periods,
        certificates=context.applicant.certificates,
        today=context.today,
    )


def _has_time(context: ReviewInput) -> bool:
    if context.deadline is None:
        return True
    return context.deadline - asyncio.get_running_loop().time() > settings.application_recheck_reserve_seconds


def _notable_numbers(facts: list[Fact]) -> list[int]:
    """카드의 '눈여겨볼 점' 후보로 검토할 사실 번호(facts 안의 위치, 1부터).
    본인 경험을 성과 · 프로젝트 · 경험 순으로 고른다."""
    chosen = [
        number for number, fact in enumerate(facts, start=1) if fact.actor == Actor.SELF and fact.kind in NOTABLE_KINDS
    ]
    chosen.sort(key=lambda number: NOTABLE_KINDS.index(facts[number - 1].kind))
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
            holds=[Note(text=UNREADABLE, source="제출 문서")],
            checks=list(context.notes),
        )
    periods = state.get("periods") or []
    results = state.get("results") or []
    holds = [
        Note(
            text=f"{result.criterion_id} '{result.text}' {VERDICT_LABEL[Verdict.UNKNOWN]}: {result.reason}",
            source=CATEGORY_SOURCE[result.category],
        )
        for result in results
        if result.verdict == Verdict.UNKNOWN
    ]
    # 주의 신호를 앞에 둔다: 코드로 찾은 것(잦은 이직 · 기준 없는 수치)과 모델이 찾은 것
    checks = [*code_warnings(periods, context.applicant.documents), *(state.get("warnings") or [])]
    # 경력 연수는 직무 관련 재직 기간만 센다. 뺀 기간은 담당자가 볼 수 있게 알린다
    job_fit = state.get("job_fit")
    checks += job_notes(periods, job_fit)
    # 눈여겨볼 점이 공동 작업이면 본인이 맡은 부분을 확인할 점으로도 알린다
    notable = state.get("notable") or []
    checks += [
        Note(
            text=f"'{note.title}'은 공동 작업으로 적혀 있어 본인이 맡은 부분을 확인해야 해요.",
            source=note.source,
            title="본인 역할",
        )
        for note in notable
        if TEAM_ROLE_CHECK in note.detail
    ]
    checks += list(context.notes)
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
        digests=state.get("digests") or [],
        career_years=career_years(job_periods(periods, job_fit), context.today) if periods else None,
        last_company=last_company(periods),
        criteria=results,
        notable=notable,
        holds=holds,
        checks=checks,
    )
