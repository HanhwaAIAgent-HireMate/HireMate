"""분석 결과 원본(ApplicationReview)을 backend 계약과 지원자 프로필 항목으로 바꾼다. 모델을 부르지 않는다."""

import re
from collections.abc import Sequence

from hiremate_ai.agents.analysis.application.types import (
    ApplicationAnalysis,
    ApplicationReview,
    Fact,
    Level,
    PreferenceStatus,
    Quote,
)
from hiremate_ai.agents.guardrails import verified_evidence
from hiremate_ai.contract import ApplicantDocument, CandidateAnalysis, Condition, Evidence, Finding, FitLine
from hiremate_ai.db.profile import ItemCategory, ProfileStatus
from hiremate_ai.db.profile_store import NewItem, ProfileFields

AGENT_NAME = "Application Agent"
NOTABLE_LIMIT = 3
PREFERENCE_LABEL = "우대사항 · NCS 평가 조건"

_LABEL_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9+#.]*")
_LABEL_STOP = {"경험", "있으신", "있는", "이상", "관련", "기반", "또는", "등의", "등", "작성한", "개발", "경력", "분"}


def to_analysis(review: ApplicationReview) -> ApplicationAnalysis:
    return ApplicationAnalysis(
        career_years=review.career_years if review.readable else None,
        last_company=review.last_company,
        document_score=None if review.held else review.document_score,
        passed=review.passed,
        held=review.held,
        shortfalls=[
            result.shortfall
            for result in review.qualifications
            if result.evaluated and not result.met and result.shortfall
        ],
    )


def to_candidate_analysis(review: ApplicationReview, documents: Sequence[ApplicantDocument]) -> CandidateAnalysis:
    conditions = [
        Condition(label=label(result.text), met=result.met, requirement=result.text)
        for result in review.qualifications
        if result.evaluated
    ]
    conditions += [
        Condition(
            label=label(preference.text),
            met=bool(preference.score),
            requirement=preference.text,
        )
        for preference in review.preferences
        if preference.status != PreferenceStatus.UNRATED
    ]
    facts = notable_facts(review.facts)
    notable = [Finding(text=fact.statement, source=fact.quotes[0].document.label) for fact in facts]
    quotes: list[Quote] = [quote for result in review.qualifications if result.met for quote in result.quotes]
    quotes += [
        quote for preference in review.preferences for criterion in preference.criteria for quote in criterion.quotes
    ]
    quotes += [quote for fact in facts for quote in fact.quotes]
    quotes += [quote for line in review.fit for quote in line.quotes]
    highlights = verified_evidence(
        dict.fromkeys(Evidence(document=quote.document, sentence=quote.sentence) for quote in quotes), list(documents)
    )
    return CandidateAnalysis(
        conditions=conditions,
        notable=notable[:NOTABLE_LIMIT],
        checks=[Finding(text=note.text, source=note.source) for note in review.checks],
        holds=[Finding(text=note.text, source=note.source) for note in review.holds],
        fit=fit_lines(review),
        highlights=highlights,
        agent=AGENT_NAME,
        stub=False,
    )


def to_profile(review: ApplicationReview) -> tuple[ProfileFields, list[NewItem]]:
    """지원자 프로필(db.profile)에 넣을 요약 값과 항목. passed는 자격요건 75% 통과 여부다."""
    if review.held:
        summary = "서류 점수 보류"
    elif review.document_score is not None:
        summary = f"AI 적합도 {review.document_score}점"
    else:
        summary = "서류 점수 없음"
    fields = ProfileFields(
        status=ProfileStatus.DONE if review.readable and not review.held else ProfileStatus.CHECK,
        career_years=review.career_years if review.readable else None,
        last_company=review.last_company,
        document_score=None if review.held else review.document_score,
        passed=review.passed,
        summary=summary,
    )
    items = [
        NewItem(
            category=ItemCategory.QUALIFICATION,
            content=f"{result.text}: {'충족' if result.met else '미충족'}",
            evidence=result.quotes[0].sentence if result.quotes else None,
            source=result.quotes[0].document.label if result.quotes else "공고 · 자격요건",
        )
        for result in review.qualifications
        if result.evaluated
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


def fit_lines(review: ApplicationReview) -> list[FitLine]:
    """AI 적합도 점수의 항목들. 첫 줄은 우대사항 · NCS 평가 조건(60점), 나머지는 직무 적합도(40점)다."""
    if review.held or not review.readable:
        return []
    rated = [preference for preference in review.preferences if preference.status == PreferenceStatus.SCORED]
    met = sum(sum(criterion.level == Level.MET for criterion in preference.criteria) for preference in rated)
    total = sum(len(preference.criteria) for preference in rated)
    detail = " · ".join(
        f"P{preference.number} {sum(c.level == Level.MET for c in preference.criteria)}/{len(preference.criteria)}"
        f"(가중치 {preference.weight})"
        for preference in rated
    )
    first = FitLine(
        label=PREFERENCE_LABEL,
        points=round(review.preference_points),
        max=60,
        reason=f"평가 조건 {total}개 가운데 {met}개를 만족했어요. {detail}",
    )
    return [
        first,
        *(FitLine(label=line.label, points=line.points, max=line.max, reason=line.reason) for line in review.fit),
    ]


def notable_facts(facts: Sequence[Fact]) -> list[Fact]:
    """눈여겨볼 점: 검토를 통과한, 본인이 한 성과 · 프로젝트 · 경험."""
    order = ("ACHIEVEMENT", "PROJECT", "EXPERIENCE")
    chosen = [fact for fact in facts if fact.supported and fact.actor.value == "SELF" and fact.kind in order]
    return sorted(chosen, key=lambda fact: order.index(fact.kind))[:NOTABLE_LIMIT]


def label(text: str) -> str:
    """조건 칩 이름. 앞쪽 낱말 두 개를 가운뎃점으로 잇는다."""
    words = [word for word in _LABEL_WORD.findall(text) if word not in _LABEL_STOP][:2]
    return "·".join(words) if words else text[:12]
