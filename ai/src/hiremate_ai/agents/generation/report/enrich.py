"""묶음에 ai가 저장한 분석 판정 · 근거를 붙인다. compose 전에 코드가 하고, Report Agent는 DB를 읽지 않는다.

backend는 업무 데이터(지원자번호, 결정, 점수, 지표)로 묶음 뼈대를 만들고, 분석 결과는 ai가 저장하므로
(아키텍처 규칙 3) 여기서 지원자의 application_id로 찾아 붙인다. 찾지 못한 지원자는 그대로 둔다.

- 서류 전형: 항목 판정(document.criterion.<항목>)과 판정 이유 · 원문 근거 (정량 원문을 먼저 고른다)
- 평가 · 면접 전형: 분석 Agent가 프로필에 남긴 강점 · 확인할 점 수(<전형>.strengths · <전형>.checks)와 그 근거

값 key 앞부분은 전형 종류(document · assessment · interview)이고,
범위에 같은 종류가 또 있으면 interview2처럼 번호를 붙인다.
backend도 같은 규칙으로 점수 · 결정 key를 만든다 (stage_prefix).
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.analysis.application.types import Actor, ApplicationReview, CriterionResult
from hiremate_ai.agents.generation.report.bundle import BundleStage, Evidence, Fact, ReportBundle, Strength
from hiremate_ai.agents.generation.report.strength import quote_strength
from hiremate_ai.contract import StageType
from hiremate_ai.db.profile import CandidateProfile, ItemAgent, ItemCategory

APPLICATION_AGENT = "application"
_DOCUMENT_LABELS = {
    "RESUME": "이력서",
    "COVER_LETTER": "자기소개서",
    "PORTFOLIO": "포트폴리오",
    "CERTIFICATE": "자격증",
}

_ITEM_LABELS: dict[str, str] = {ItemCategory.STRENGTH: "강점", ItemCategory.CHECK: "확인할 점"}


class Reviews(Protocol):
    """지원서 분석 결과 저장소에서 쓰는 부분 (ReviewStore.latest)."""

    async def latest(
        self, application_id: UUID, *, company_id: UUID, recruitment_id: UUID
    ) -> ApplicationReview | None: ...


@dataclass(frozen=True)
class StageItem:
    """평가 · 면접 분석 Agent가 프로필에 남긴 항목 하나."""

    stage_id: UUID
    agent: str
    category: str
    content: str
    evidence: str | None
    source: str


class StageItems(Protocol):
    async def stage_items(
        self, *, company_id: UUID, recruitment_id: UUID, application_ids: list[UUID]
    ) -> dict[UUID, list[StageItem]]: ...


class DbStageItems:
    """지원자 프로필에서 평가 · 면접 항목을 읽는다. 기업 · 채용 범위로만 읽는다 (아키텍처 규칙 4)."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def stage_items(
        self, *, company_id: UUID, recruitment_id: UUID, application_ids: list[UUID]
    ) -> dict[UUID, list[StageItem]]:
        if not application_ids:
            return {}
        async with self._sessions() as session:
            profiles = await session.scalars(
                select(CandidateProfile).where(
                    CandidateProfile.application_id.in_(application_ids),
                    CandidateProfile.company_id == company_id,
                    CandidateProfile.recruitment_id == recruitment_id,
                )
            )
            return {
                profile.application_id: [
                    StageItem(item.stage_id, item.agent, item.category, item.content, item.evidence, item.source)
                    for item in profile.items
                    if item.agent in (ItemAgent.ASSESSMENT, ItemAgent.INTERVIEW) and item.stage_id is not None
                ]
                for profile in profiles
            }


def stage_prefix(stages: list[BundleStage], stage: BundleStage) -> str:
    """값 key 앞부분. 전형 종류 이름이고, 범위에 같은 종류가 앞에 또 있으면 번호를 붙인다 (interview2)."""
    same = [other.stage_id for other in stages if other.type is stage.type]
    order = same.index(stage.stage_id) + 1
    name = stage.type.value.lower()
    return name if order == 1 else f"{name}{order}"


def criterion_key(criterion_id: str) -> str:
    return f"document.criterion.{criterion_id}"


async def enrich(bundle: ReportBundle, reviews: Reviews, items: StageItems | None = None) -> ReportBundle:
    """범위 안 전형의 분석 판정 · 근거를 붙인 묶음. 이미 있는 값 · 근거는 바꾸지 않는다."""
    bundle = await _document(bundle, reviews)
    if items is not None:
        bundle = await _stage_items(bundle, items)
    return bundle


async def _stage_items(bundle: ReportBundle, source: StageItems) -> ReportBundle:
    stages = [stage for stage in bundle.stages if stage.type is not StageType.DOCUMENT]
    numbers = {a.application_id: a.number for a in bundle.applicants if a.application_id is not None}
    if not stages or not numbers:
        return bundle
    found = await source.stage_items(
        company_id=bundle.company_id, recruitment_id=bundle.recruitment_id, application_ids=list(numbers)
    )
    facts, evidence = list(bundle.facts), list(bundle.evidence)
    have = {(fact.applicant, fact.key) for fact in facts}
    for application_id, number in numbers.items():
        for stage in stages:
            mine = [item for item in found.get(application_id, []) if item.stage_id == stage.stage_id]
            if not mine:
                continue
            prefix = stage_prefix(bundle.stages, stage)
            counts = {
                "strengths": ("강점", sum(1 for item in mine if item.category == ItemCategory.STRENGTH)),
                "checks": ("확인할 점", sum(1 for item in mine if item.category == ItemCategory.CHECK)),
            }
            for name, (label, count) in counts.items():
                if (number, f"{prefix}.{name}") not in have:
                    facts.append(
                        Fact(
                            id=f"{number}-{prefix}-{name}",
                            applicant=number,
                            stage_id=stage.stage_id,
                            key=f"{prefix}.{name}",
                            label=f"{stage.name} {label} 수",
                            value=float(count),
                        )
                    )
            for index, item in enumerate(mine, start=1):
                evidence.append(
                    Evidence(
                        id=f"e-{number}-{prefix}-{index}",
                        applicant=number,
                        stage_id=stage.stage_id,
                        agent=item.agent,
                        text=item.content,
                        source=item.source,
                        quote=item.evidence,
                        label=_ITEM_LABELS.get(item.category),
                        strength=quote_strength(item.evidence),
                    )
                )
    return bundle.model_copy(update={"facts": facts, "evidence": evidence})


async def _document(bundle: ReportBundle, reviews: Reviews) -> ReportBundle:
    document = next((stage for stage in bundle.stages if stage.type is StageType.DOCUMENT), None)
    if document is None:
        return bundle
    facts, evidence = list(bundle.facts), list(bundle.evidence)
    have = {(fact.applicant, fact.key) for fact in facts}
    evidence_ids = {item.id for item in evidence}
    for applicant in bundle.applicants:
        if applicant.application_id is None:
            continue
        review = await reviews.latest(
            applicant.application_id, company_id=bundle.company_id, recruitment_id=bundle.recruitment_id
        )
        if review is None:
            continue
        for result in review.criteria:
            key = criterion_key(result.criterion_id)
            if (applicant.number, key) not in have:
                facts.append(
                    Fact(
                        id=f"{applicant.number}-{result.criterion_id}",
                        applicant=applicant.number,
                        stage_id=document.stage_id,
                        key=key,
                        label=f"{result.criterion_id} {result.text}",
                        value=result.verdict.value,
                    )
                )
            item = _evidence(applicant.number, document.stage_id, result)
            if item.id not in evidence_ids:
                evidence.append(item)
                evidence_ids.add(item.id)
    return bundle.model_copy(update={"facts": facts, "evidence": evidence})


def _evidence(number: str, stage_id: UUID, result: CriterionResult) -> Evidence:
    """항목 판정 이유(서류 Agent의 판단)와 원문 한 문장. 정량 원문이 있으면 그 문장을, 없으면 첫 문장을 고른다.
    원문이 있으면 그 서류를 출처로 쓴다."""
    quote = next(
        (item for item in result.quotes if quote_strength(item.sentence) is Strength.QUANT),
        result.quotes[0] if result.quotes else None,
    )
    source = _DOCUMENT_LABELS.get(quote.document.value, quote.document.value) if quote else "서류 전체"
    return Evidence(
        id=f"e-{number}-{result.criterion_id}",
        applicant=number,
        stage_id=stage_id,
        agent=APPLICATION_AGENT,
        text=result.reason,
        source=source,
        quote=quote.sentence if quote else None,
        label=result.text,
        verdict=result.verdict.value,
        strength=quote_strength(quote.sentence) if quote else None,
        detail=_detail(result),
        role=result.role.value if result.role else None,
    )


_ROLE_LABELS = {Actor.SELF: "본인이 직접", Actor.TEAM: "팀 · 조직의 성과", Actor.UNCLEAR: "본인 역할 불분명"}


def _detail(result: CriterionResult) -> str | None:
    """판정 세부 한 줄. 서류 Agent가 남긴 충족한 부분 · 못 채운 부분 · 확인 필요한 부분 · 역할 · 수행 범위다."""
    parts = []
    if result.satisfied_parts:
        parts.append(f"충족한 부분 {', '.join(result.satisfied_parts)}")
    if result.unsatisfied_parts:
        parts.append(f"못 채운 부분 {', '.join(result.unsatisfied_parts)}")
    if result.unknown_parts:
        parts.append(f"확인 필요한 부분 {', '.join(result.unknown_parts)}")
    if result.role:
        parts.append(f"역할 {_ROLE_LABELS[result.role]}")
    if result.scope:
        parts.append(f"수행 범위 {result.scope}")
    return " · ".join(parts) or None
