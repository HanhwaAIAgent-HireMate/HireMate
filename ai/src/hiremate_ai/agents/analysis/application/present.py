"""분석 결과 원본(ApplicationReview)을 backend 계약과 지원자 프로필 항목으로 바꾼다. 모델을 부르지 않는다."""

import re
from collections.abc import Sequence

from hiremate_ai.agents.analysis.application.types import (
    Actor,
    ApplicationAnalysis,
    ApplicationReview,
    Fact,
    Quote,
)
from hiremate_ai.agents.analysis.plain import plain
from hiremate_ai.agents.guardrails import verified_evidence
from hiremate_ai.contract import (
    ApplicantDocument,
    CandidateAnalysis,
    Condition,
    CriterionCategory,
    CriterionLine,
    DigestRow,
    DigestSection,
    DocumentDigest,
    Evidence,
    Finding,
    SummarySection,
    Verdict,
)
from hiremate_ai.db.profile import ItemCategory, ProfileStatus, Verification
from hiremate_ai.db.profile_store import NewItem, ProfileFields

AGENT_NAME = "Application Agent"
NOTABLE_LIMIT = 3
CATEGORY_LABEL = {CriterionCategory.QUALIFICATION: "자격요건", CriterionCategory.PREFERENCE: "우대사항"}
# 프로필 항목은 평어 문장으로 쓴다. 화면의 판정 칩은 types.VERDICT_LABEL(충족 · 미충족 …)을 그대로 쓴다
VERDICT_SENTENCE = {
    Verdict.MET: "충족한다",
    Verdict.PARTIAL: "일부 충족한다",
    Verdict.NOT_MET: "충족하지 않는다",
    Verdict.UNKNOWN: "충족 여부를 확인해야 한다",
}

_LABEL_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9+#.]*")
_LABEL_STOP = {"경험", "있으신", "있는", "이상", "관련", "기반", "또는", "등의", "등", "작성한", "개발", "경력", "분"}


def to_analysis(review: ApplicationReview) -> ApplicationAnalysis:
    return ApplicationAnalysis(
        career_years=review.career_years if review.readable else None,
        last_company=review.last_company,
        criteria_version=review.criteria_version or None,
        shortfalls=shortfalls(review),
        criterion_marks={result.criterion_id: result.verdict for result in review.criteria},
    )


def shortfalls(review: ApplicationReview) -> list[str]:
    """미충족 · 확인 필요 자격요건의 짧은 표시."""
    return [result.shortfall for result in review.qualifications if result.shortfall and result.verdict != Verdict.MET]


def to_candidate_analysis(review: ApplicationReview, documents: Sequence[ApplicantDocument]) -> CandidateAnalysis:
    conditions = [
        Condition(label=label(result.text), met=result.verdict == Verdict.MET, requirement=result.text)
        for result in review.qualifications
    ]
    facts = notable_facts(review.facts)
    notable = [
        Finding(text=note.text, source=note.source, title=note.title, detail=note.detail, metric=note.metric)
        for note in review.notable
    ] or [Finding(text=fact.statement, source=fact.quotes[0].document.label) for fact in facts]
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
        checks=[
            Finding(text=note.text, source=note.source, title=note.title, warning=note.warning)
            for note in review.checks
            if not (note.title == "회사명 불일치" and re.search(r"불일치\s*(?:가\s*)?(?:없|아니|않)", note.text))
        ],
        holds=[Finding(text=note.text, source=note.source) for note in review.holds],
        criteria_version=review.criteria_version or None,
        criteria=criterion_lines(review),
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
        digests=[
            DocumentDigest(
                document=digest.document,
                sections=[
                    DigestSection(
                        title=section.title,
                        layout=section.layout,
                        columns=section.columns,
                        rows=[
                            DigestRow(
                                title=row.title,
                                cells=row.cells,
                                tags=row.tags,
                                evidence=[
                                    Evidence(document=quote.document, sentence=quote.sentence) for quote in row.quotes
                                ],
                            )
                            for row in section.rows
                        ],
                        tags=section.tags,
                        items=section.items,
                    )
                    for section in digest.sections
                ],
            )
            for digest in review.digests
        ],
    )


def criterion_lines(review: ApplicationReview) -> list[CriterionLine]:
    """항목별 판정: 이유 · 충족 / 미충족 / 확인되지 않은 부분 · 근거 · 재확인 횟수 · 정량 지표. 점수는 매기지 않는다."""
    if not review.readable:
        return []
    lines = []
    for result in review.criteria:
        lines.append(
            CriterionLine(
                criterion_id=result.criterion_id,
                category=result.category,
                text=result.text,
                important=result.important,
                criterion_type=result.criterion_type,
                verdict=result.verdict,
                reason=result.reason,
                satisfied_parts=result.satisfied_parts,
                unsatisfied_parts=result.unsatisfied_parts,
                unknown_parts=result.unknown_parts,
                evidence=[Evidence(document=quote.document, sentence=quote.sentence) for quote in result.quotes],
                recheck_count=result.recheck_count,
                career_years=None if result.career_months is None else result.career_months // 12,
                certificate_status=result.certificate_status,
                metric=result.metric,
                no_record=result.no_record,
                brief=result.brief,
                setting_note=result.setting_note,
            )
        )
    return lines


def to_profile(review: ApplicationReview) -> tuple[ProfileFields, list[NewItem]]:
    """지원자 프로필(db.profile)에 넣을 요약 값과 항목. 확인 필요가 남으면 확인 상태로 둔다. 점수는 매기지 않는다."""
    if not review.readable:
        summary = "서류를 읽지 못함"
    elif review.holds:
        summary = f"서류 분석 · 확인 필요 {len(review.holds)}건"
    else:
        summary = "서류 분석 완료"
    fields = ProfileFields(
        status=ProfileStatus.DONE if review.readable and not review.holds else ProfileStatus.CHECK,
        career_years=review.career_years if review.readable else None,
        last_company=review.last_company,
        summary=summary,
    )
    items = [
        NewItem(
            category=ItemCategory.QUALIFICATION if result.verdict != Verdict.UNKNOWN else ItemCategory.CHECK,
            content=f"{CATEGORY_LABEL[result.category]} {result.text}: {VERDICT_SENTENCE[result.verdict]}.",
            evidence=result.quotes[0].sentence if result.quotes else None,
            source=result.quotes[0].document.label if result.quotes else f"공고 · {CATEGORY_LABEL[result.category]}",
        )
        for result in review.criteria
    ]
    # 팀 성과와 역할이 불분명한 사실은 원문에 근거가 있어도 본인 경험으로 확인되지 않았다 (규칙 7)
    items += [
        NewItem(
            category=ItemCategory.SKILL if fact.kind == "SKILL" else ItemCategory.EXPERIENCE,
            content=plain(fact.statement),
            evidence=fact.quotes[0].sentence,
            source=fact.quotes[0].document.label,
            verification=None if fact.actor is Actor.SELF else Verification.UNCONFIRMED,
        )
        for fact in review.facts
        if fact.supported and fact.kind in ("SKILL", "EXPERIENCE", "PROJECT", "ACHIEVEMENT")
    ]
    items += [
        NewItem(category=ItemCategory.CHECK, content=plain(note.text), source=note.source) for note in review.holds
    ]
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
