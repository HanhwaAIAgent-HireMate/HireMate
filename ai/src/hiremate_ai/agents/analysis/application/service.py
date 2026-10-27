"""지원서 분석 한 번: 평가 항목을 공고와 짝짓고, 저장된 결과가 있으면 쓰고, 없으면 그래프를 돌려 저장한다."""

import asyncio
import re
from collections.abc import Sequence
from datetime import date
from uuid import uuid4

from hiremate_ai.agents.analysis.application.context import readable
from hiremate_ai.agents.analysis.application.extract import ExtractedFacts, extract_documents, merge
from hiremate_ai.agents.analysis.application.graph import REVIEW_VERSION, ReviewInput, run_review
from hiremate_ai.agents.analysis.application.review import fact_claims, review_claims
from hiremate_ai.agents.analysis.application.store import ReviewStore, input_hash
from hiremate_ai.agents.analysis.application.types import (
    ApplicationReview,
    Criterion,
    EvaluationRules,
    Fact,
    Note,
    ScreeningRubric,
)
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, ApplicantDocument, CriterionCategory, CriterionType, PostingContent
from hiremate_ai.db.analysis_store import AnalysisArtifactStore
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.recipe import analysis_recipe

CRITERIA_SOURCE = "공고 · 평가 기준"


class RubricScopeError(ValueError):
    """평가 기준의 채용과 지원서의 채용이 다를 때. 다른 채용의 기준으로 평가하지 않는다 (아키텍처 규칙 4)."""


async def review_application_documents(
    llm: LlmClient, documents: Sequence[ApplicantDocument], *, extracted: Sequence[ExtractedFacts | None] | None = None
) -> list[Fact]:
    """제출 문서의 사실과 근거를 검토한다. 점수를 매기거나 결과를 저장하지 않는다.

    원문에서 찾은 인용과 본인 역할을 보존하며, 검토에서 명시적으로 뒷받침된 사실만 supported다.
    """
    usable = readable(documents)
    if not usable:
        return []
    if extracted is not None:
        if len(extracted) != len(documents):
            raise ValueError("추출 결과와 문서 수가 다르다")
        extracted = [result for document, result in zip(documents, extracted, strict=True) if document.text.strip()]
    results = await extract_documents(llm, usable, settings.application_concurrency, cached=extracted)
    facts, _ = merge(usable, results, date.today())
    reviews = await review_claims(llm, fact_claims(facts))
    supported = {review.id for review in reviews.values() if review.verdict == "SUPPORTED"}
    return [
        fact.model_copy(update={"supported": f"F{index}" in supported}) for index, fact in enumerate(facts, start=1)
    ]


async def analyze_application(
    llm: LlmClient,
    store: ReviewStore,
    applicant: ApplicantDetail,
    posting: PostingContent,
    rubric: ScreeningRubric,
    *,
    budget_seconds: float,
    today: date | None = None,
    artifacts: AnalysisArtifactStore | None = None,
) -> ApplicationReview:
    """지원서를 분석하고 결과 원본을 돌려준다. 같은 입력의 저장 결과가 있으면 모델을 부르지 않는다.

    분석이 budget_seconds 안에 끝나지 않으면 TimeoutError다. 재확인은 남은 시간을 보고 줄인다.
    모델 · DB 오류는 그대로 올려 backend가 분석 실패(근거 부족에 따른 점수 보류와 다르다)로 남기게 한다.
    """
    if rubric.recruitment_id != applicant.info.recruitment_id:
        raise RubricScopeError("평가 기준과 지원서의 채용이 다르다")
    analysis_date = today or date.today()
    recipe = analysis_recipe(llm)
    digest = input_hash(
        applicant,
        posting,
        rubric,
        REVIEW_VERSION,
        today=analysis_date,
        recipe=recipe if recipe is not None else {"unsupported": str(uuid4())},
    )
    stored = (
        await store.find(
            applicant.info.application_id, digest, company_id=rubric.company_id, recruitment_id=rubric.recruitment_id
        )
        if recipe is not None
        else None
    )
    if stored is not None:
        return stored
    criteria, notes = match_criteria(posting, rubric)
    context = ReviewInput(
        applicant=applicant,
        posting=posting,
        criteria=criteria,
        criteria_version=rubric.criteria_version,
        notes=notes,
        input_hash=digest,
        today=analysis_date,
        deadline=asyncio.get_running_loop().time() + budget_seconds,
        company_id=rubric.company_id,
        artifacts=artifacts if artifacts is not None else store.artifacts,
    )
    async with asyncio.timeout(budget_seconds):
        review = await run_review(llm, context)
    await store.save(review, applicant, rubric)
    return review


def match_criteria(posting: PostingContent, rubric: ScreeningRubric) -> tuple[tuple[Criterion, ...], tuple[Note, ...]]:
    """공고의 자격요건 · 우대사항을 평가 기준 항목과 글로 짝짓는다.

    차별 조건은 평가하지 않는다 (아키텍처 규칙 6). 공고 문장에 맞는 평가 기준이 없으면 평가 설정 오류로 알리고,
    단일 능력 · 경험형(0 · 1)에 중요 표시 없이 공고 문장 그대로 판정한다.
    """
    saved = {(criterion.category, _compact(criterion.text)): criterion for criterion in rubric.criteria}
    criteria: list[Criterion] = []
    notes: list[Note] = []
    for category, texts, prefix in (
        (CriterionCategory.QUALIFICATION, posting.qualifications, "Q"),
        (CriterionCategory.PREFERENCE, posting.preferred, "P"),
    ):
        for number, text in enumerate(texts, start=1):
            if blocked_attribute(text):
                notes.append(
                    Note(text=f"'{text}'은 채용 판단에 쓰면 안 되는 조건이라 평가하지 않았어요.", source="공고")
                )
                continue
            found = saved.get((category, _compact(text)))
            if found is None:
                notes.append(
                    Note(
                        text=f"'{text}'에 맞는 평가 기준이 없어 공고 문장 그대로 충족 · 미충족만 판정했어요.",
                        source=CRITERIA_SOURCE,
                    )
                )
                found = Criterion(
                    criterion_id=f"{prefix}-{number:02d}",
                    category=category,
                    text=text,
                    important=False,
                    criterion_type=CriterionType.SINGLE,
                    evaluation_rules=EvaluationRules(
                        met=f"서류에서 '{text}'을 확인할 수 있다", unmet=f"서류에서 '{text}'이 확인되지 않는다"
                    ),
                )
            criteria.append(found)
    return tuple(criteria), tuple(notes)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)
