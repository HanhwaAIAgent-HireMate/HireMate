"""지원서 분석 한 번: 평가 기준을 공고와 짝짓고, 저장된 결과가 있으면 쓰고, 없으면 그래프를 돌려 저장한다."""

import asyncio
import re
from datetime import date

from hiremate_ai.agents.analysis.application.graph import REVIEW_VERSION, ReviewInput, run_review
from hiremate_ai.agents.analysis.application.judge import PreferenceTask
from hiremate_ai.agents.analysis.application.store import ReviewStore, input_hash
from hiremate_ai.agents.analysis.application.types import ApplicationReview, ScreeningRubric
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.tools.ncs import NcsUnit


class RubricScopeError(ValueError):
    """평가 기준의 채용과 지원서의 채용이 다를 때. 다른 채용의 기준으로 평가하지 않는다 (아키텍처 규칙 4)."""


async def analyze_application(
    llm: LlmClient,
    store: ReviewStore,
    applicant: ApplicantDetail,
    posting: PostingContent,
    rubric: ScreeningRubric,
    *,
    budget_seconds: float,
    today: date | None = None,
) -> ApplicationReview:
    """지원서를 분석하고 결과 원본을 돌려준다. 같은 입력의 저장 결과가 있으면 모델을 부르지 않는다.

    분석이 budget_seconds 안에 끝나지 않으면 TimeoutError다. 모델 · DB 오류는 그대로 올려
    backend가 분석 실패로 남기게 한다.
    """
    if rubric.recruitment_id != applicant.info.recruitment_id:
        raise RubricScopeError("평가 기준과 지원서의 채용이 다르다")
    units = await store.units([preference.ncs_unit_code for preference in rubric.preferred])
    digest = input_hash(applicant, posting, rubric, units, REVIEW_VERSION)
    stored = await store.find(applicant.info.application_id, digest)
    if stored is not None:
        return stored
    context = ReviewInput(
        applicant=applicant,
        posting=posting,
        tasks=preference_tasks(posting, rubric, units),
        related_certificates=tuple(
            dict.fromkeys(name for preference in rubric.preferred for name in preference.certificates)
        ),
        input_hash=digest,
        today=today or date.today(),
    )
    async with asyncio.timeout(budget_seconds):
        review = await run_review(llm, context)
    await store.save(review, applicant, rubric)
    return review


def preference_tasks(
    posting: PostingContent, rubric: ScreeningRubric, units: dict[str, NcsUnit]
) -> tuple[PreferenceTask, ...]:
    """공고의 우대사항을 평가 기준과 글로 짝짓는다. 짝이 없거나 NCS 기준을 읽지 못하면 판정하지 않는다."""
    by_text = {_compact(preference.text): preference for preference in rubric.preferred}
    tasks = []
    for number, text in enumerate(posting.preferred, start=1):
        found = by_text.get(_compact(text))
        unit = units.get(found.ncs_unit_code) if found else None
        if blocked_attribute(text):
            unit = None
        tasks.append(
            PreferenceTask(
                number=number,
                text=text,
                weight=found.weight if found else None,
                unit=unit,
            )
        )
    return tuple(tasks)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)
