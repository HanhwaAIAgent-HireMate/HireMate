"""분석 결과 원본(ApplicationReview)을 backend 계약과 지원자 프로필 항목으로 바꾼다. 모델을 부르지 않는다."""

import re
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from hiremate_ai.agents.analysis.application.score import Weights, allotted
from hiremate_ai.agents.analysis.application.types import (
    VERDICT_LABEL,
    ApplicationAnalysis,
    ApplicationReview,
    Fact,
    Quote,
)
from hiremate_ai.agents.guardrails import verified_evidence
from hiremate_ai.contract import (
    ApplicantDocument,
    CandidateAnalysis,
    Condition,
    CriterionCategory,
    CriterionLine,
    Evidence,
    Finding,
    QualificationStatus,
    SummarySection,
    Verdict,
)
from hiremate_ai.db.profile import ItemCategory, ProfileStatus
from hiremate_ai.db.profile_store import NewItem, ProfileFields

AGENT_NAME = "Application Agent"
NOTABLE_LIMIT = 3
CATEGORY_LABEL = {CriterionCategory.QUALIFICATION: "자격요건", CriterionCategory.PREFERENCE: "우대사항"}

_LABEL_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9+#.]*")
_LABEL_STOP = {"경험", "있으신", "있는", "이상", "관련", "기반", "또는", "등의", "등", "작성한", "개발", "경력", "분"}


def to_analysis(review: ApplicationReview) -> ApplicationAnalysis:
    return ApplicationAnalysis(
        career_years=review.career_years if review.readable else None,
        last_company=review.last_company,
        criteria_version=review.criteria_version or None,
        qualification_status=review.qualification_status,
        qualification_rate=review.qualification_rate,
        qualification_score=review.qualification_score,
        qualification_max=review.qualification_max,
        preference_score=review.preference_score,
        preference_max=review.preference_max,
        document_score=None if review.held else review.document_score,
        passed=review.passed,
        held=review.held,
        shortfalls=shortfalls(review),
    )


def shortfalls(review: ApplicationReview) -> list[str]:
    """미충족 · 확인 필요 자격요건의 짧은 표시. 점수가 높아도 숨기지 않는다."""
    return [result.shortfall for result in review.qualifications if result.shortfall and result.verdict != Verdict.MET]


def to_candidate_analysis(
    review: ApplicationReview, documents: Sequence[ApplicantDocument], weights: Weights
) -> CandidateAnalysis:
    conditions = [
        Condition(label=label(result.text), met=result.verdict == Verdict.MET, requirement=result.text)
        for result in review.qualifications
    ]
    facts = notable_facts(review.facts)
    notable = [Finding(text=fact.statement, source=fact.quotes[0].document.label) for fact in facts]
    quotes: list[Quote] = [
        quote for result in review.criteria if result.verdict != Verdict.NOT_MET for quote in result.quotes
    ]
    quotes += [quote for fact in facts for quote in fact.quotes]
    highlights = verified_evidence(
        dict.fromkeys(Evidence(document=quote.document, sentence=quote.sentence) for quote in quotes), list(documents)
    )
    return CandidateAnalysis(
        conditions=conditions,
        notable=notable[:NOTABLE_LIMIT],
        checks=[Finding(text=note.text, source=note.source) for note in review.checks],
        holds=[Finding(text=note.text, source=note.source) for note in review.holds],
        criteria_version=review.criteria_version or None,
        score_status=review.score_status,
        document_score=None if review.held else review.document_score,
        qualification_status=review.qualification_status,
        qualification_rate=review.qualification_rate,
        qualification_score=review.qualification_score,
        qualification_max=review.qualification_max,
        preference_score=review.preference_score,
        preference_max=review.preference_max,
        criteria=criterion_lines(review, weights),
        summaries=[
            SummarySection(
                document=section.document,
                title=section.title,
                summary=section.summary,
                points=section.points,
                evidence=[Evidence(document=quote.document, sentence=quote.sentence) for quote in section.quotes],
            )
            for section in review.sections
        ],
        highlights=highlights,
        agent=AGENT_NAME,
        stub=False,
    )


def criterion_lines(review: ApplicationReview, weights: Weights) -> list[CriterionLine]:
    """항목별 판정: 충족도 · 배점 · 획득 점수 · 이유 · 충족 / 미충족 / 확인되지 않은 부분 · 근거 · 재확인 횟수."""
    if not review.readable:
        return []
    lines = []
    for result in review.criteria:
        share = allotted(result, review.criteria, weights)
        fulfillment = result.fulfillment
        lines.append(
            CriterionLine(
                criterion_id=result.criterion_id,
                category=result.category,
                text=result.text,
                important=result.important,
                criterion_type=result.criterion_type,
                verdict=result.verdict,
                fulfillment=fulfillment,
                allotted=_one(share),
                earned=None if fulfillment is None else _one(share * Decimal(str(fulfillment))),
                reason=result.reason,
                satisfied_parts=result.satisfied_parts,
                unsatisfied_parts=result.unsatisfied_parts,
                unknown_parts=result.unknown_parts,
                evidence=[Evidence(document=quote.document, sentence=quote.sentence) for quote in result.quotes],
                recheck_count=result.recheck_count,
                career_years=None if result.career_months is None else result.career_months // 12,
                certificate_status=result.certificate_status,
            )
        )
    return lines


def to_profile(review: ApplicationReview) -> tuple[ProfileFields, list[NewItem]]:
    """지원자 프로필(db.profile)에 넣을 요약 값과 항목. passed는 75% 통과 판단이고 판단 보류면 None이다."""
    if review.held:
        summary = "서류 점수 보류"
    elif review.document_score is not None:
        summary = f"서류 평가 {review.document_score:g}점"
    else:
        summary = "서류 점수 없음"
    fields = ProfileFields(
        status=ProfileStatus.DONE if review.readable and not review.held else ProfileStatus.CHECK,
        career_years=review.career_years if review.readable else None,
        last_company=review.last_company,
        document_score=None if review.held else review.document_score,
        passed=None if review.qualification_status == QualificationStatus.UNDETERMINED else review.passed,
        summary=summary,
    )
    items = [
        NewItem(
            category=ItemCategory.QUALIFICATION if result.verdict != Verdict.UNKNOWN else ItemCategory.CHECK,
            content=f"{CATEGORY_LABEL[result.category]} {result.text}: {VERDICT_LABEL[result.verdict]}"
            + (" (중요)" if result.important else ""),
            evidence=result.quotes[0].sentence if result.quotes else None,
            source=result.quotes[0].document.label if result.quotes else f"공고 · {CATEGORY_LABEL[result.category]}",
        )
        for result in review.criteria
    ]
    items += [
        NewItem(
            category=ItemCategory.SKILL if fact.kind == "SKILL" else ItemCategory.EXPERIENCE,
            content=fact.statement,
            evidence=fact.quotes[0].sentence,
            source=fact.quotes[0].document.label,
        )
        for fact in review.facts
        if fact.supported and fact.kind in ("SKILL", "EXPERIENCE", "PROJECT", "ACHIEVEMENT")
    ]
    items += [NewItem(category=ItemCategory.CHECK, content=note.text, source=note.source) for note in review.holds]
    return fields, items


def notable_facts(facts: Sequence[Fact]) -> list[Fact]:
    """눈여겨볼 점: 검토를 통과한, 본인이 한 성과 · 프로젝트 · 경험."""
    order = ("ACHIEVEMENT", "PROJECT", "EXPERIENCE")
    chosen = [fact for fact in facts if fact.supported and fact.actor.value == "SELF" and fact.kind in order]
    return sorted(chosen, key=lambda fact: order.index(fact.kind))[:NOTABLE_LIMIT]


def label(text: str) -> str:
    """조건 칩 이름. 앞쪽 낱말 두 개를 가운뎃점으로 잇는다."""
    words = [word for word in _LABEL_WORD.findall(text) if word not in _LABEL_STOP][:2]
    return "·".join(words) if words else text[:12]


def _one(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
