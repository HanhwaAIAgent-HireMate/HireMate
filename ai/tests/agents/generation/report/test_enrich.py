from datetime import UTC, datetime
from uuid import UUID, uuid4

from hiremate_ai.agents.analysis.application.types import ApplicationReview, CriterionResult, Quote
from hiremate_ai.agents.generation.report.bundle import (
    BundleApplicant,
    BundleStage,
    ReportBundle,
    ReportKind,
    Strength,
)
from hiremate_ai.agents.generation.report.enrich import StageItem, enrich
from hiremate_ai.contract import CriterionCategory, CriterionType, DocumentType, StageType, Verdict

COMPANY, RECRUITMENT, STAGE, APPLICATION = uuid4(), uuid4(), uuid4(), uuid4()


class Reviews:
    """application_id로 가장 최근 분석 결과를 돌려주는 저장소."""

    def __init__(self, reviews: dict[UUID, ApplicationReview]) -> None:
        self.reviews = reviews
        self.scopes: list[tuple[UUID, UUID]] = []

    async def latest(self, application_id: UUID, *, company_id: UUID, recruitment_id: UUID) -> ApplicationReview | None:
        self.scopes.append((company_id, recruitment_id))
        return self.reviews.get(application_id)


def criterion(criterion_id: str, verdict: Verdict, quotes: list[Quote]) -> CriterionResult:
    return CriterionResult(
        criterion_id=criterion_id,
        category=CriterionCategory.QUALIFICATION,
        text="Git 코드 리뷰 · 협업",
        important=False,
        criterion_type=CriterionType.CONDITION,
        verdict=verdict,
        reason="팀 PR 리뷰 규칙을 만든 경험이 확인돼요." if quotes else "협업 방식에 대한 서술이 없어요.",
        quotes=quotes,
    )


def bundle() -> ReportBundle:
    return ReportBundle(
        kind=ReportKind.COMPARE,
        company_id=COMPANY,
        recruitment_id=RECRUITMENT,
        stage_id=STAGE,
        title="백엔드 개발자",
        as_of=datetime(2026, 10, 27, tzinfo=UTC),
        focus="",
        brief=False,
        stages=[BundleStage(stage_id=STAGE, name="서류 전형", type=StageType.DOCUMENT, confirmed_at=None)],
        applicants=[
            BundleApplicant(number="A-0017", application_id=APPLICATION, career_years=5, last_company=None),
            BundleApplicant(number="A-0026", application_id=None, career_years=None, last_company=None),
        ],
        targets=["A-0017", "A-0026"],
        total_key=None,
        areas=[],
        metrics=[],
        facts=[],
        evidence=[],
    )


async def test_enrich_adds_document_verdicts_and_evidence_from_the_ai_store() -> None:
    quote = Quote(document=DocumentType.COVER_LETTER, sentence="팀 PR 리뷰 규칙을 만들었다")
    review = ApplicationReview(
        version="v1",
        input_hash="h",
        application_id=APPLICATION,
        readable=True,
        criteria=[criterion("Q-04", Verdict.MET, [quote]), criterion("Q-05", Verdict.UNKNOWN, [])],
    )
    reviews = Reviews({APPLICATION: review})

    enriched = await enrich(bundle(), reviews)

    assert reviews.scopes == [(COMPANY, RECRUITMENT)]  # 채용 범위로만 찾고, application_id가 없는 지원자는 건너뛴다
    facts = {(fact.applicant, fact.key): fact.value for fact in enriched.facts}
    assert facts == {
        ("A-0017", "document.criterion.Q-04"): "MET",
        ("A-0017", "document.criterion.Q-05"): "UNKNOWN",
    }
    met, unknown = enriched.evidence
    assert met.id == "e-A-0017-Q-04"
    assert met.source == "자기소개서" and met.quote == "팀 PR 리뷰 규칙을 만들었다"
    assert "원문" not in met.text  # 판단과 원문을 섞지 않는다
    assert (met.label, met.verdict) == ("Git 코드 리뷰 · 협업", "MET")
    assert met.strength is Strength.CLAIM
    assert unknown.source == "서류 전체" and unknown.strength is None


async def test_enrich_prefers_a_quantified_quote_over_the_first_one() -> None:
    claim = Quote(document=DocumentType.RESUME, sentence="MySQL 예약 테이블을 설계했습니다")
    quant = Quote(document=DocumentType.PORTFOLIO, sentence="조회 응답 시간을 800ms에서 120ms로 줄였습니다")
    review = ApplicationReview(
        version="v1",
        input_hash="h",
        application_id=APPLICATION,
        readable=True,
        criteria=[criterion("Q-03", Verdict.MET, [claim, quant])],
    )

    (evidence,) = (await enrich(bundle(), Reviews({APPLICATION: review}))).evidence

    assert (evidence.quote, evidence.source) == (quant.sentence, "포트폴리오")
    assert evidence.strength is Strength.QUANT
    assert '원문(정량): "조회 응답 시간' in evidence.line()


async def test_enrich_leaves_bundles_without_a_document_stage() -> None:
    other = bundle().model_copy(
        update={"stages": [BundleStage(stage_id=STAGE, name="1차 면접", type=StageType.INTERVIEW, confirmed_at=None)]}
    )
    assert await enrich(other, Reviews({})) == other


class Items:
    def __init__(self, items: dict[UUID, list[StageItem]]) -> None:
        self.items = items

    async def stage_items(
        self, *, company_id: UUID, recruitment_id: UUID, application_ids: list[UUID]
    ) -> dict[UUID, list[StageItem]]:
        return {key: value for key, value in self.items.items() if key in application_ids}


async def test_enrich_adds_interview_strengths_checks_and_evidence_per_stage() -> None:
    first, second = uuid4(), uuid4()
    stages = [
        BundleStage(stage_id=first, name="1차 면접", type=StageType.INTERVIEW, confirmed_at=None),
        BundleStage(stage_id=second, name="2차 면접", type=StageType.INTERVIEW, confirmed_at=None),
    ]
    items = Items(
        {
            APPLICATION: [
                StageItem(
                    first, "interview", "STRENGTH", "배치 병렬화를 주도했어요", "제가 설계를 맡았습니다", "면접 답변"
                ),
                StageItem(first, "interview", "CHECK", "조율 방법은 확인되지 않았어요", None, "면접 답변"),
                StageItem(second, "interview", "STRENGTH", "장애 회고를 이끌었어요", None, "면접 답변"),
            ]
        }
    )
    enriched = await enrich(bundle().model_copy(update={"stages": stages}), Reviews({}), items)

    facts = {fact.key: fact.value for fact in enriched.facts}
    assert facts == {
        "interview.strengths": 1.0,
        "interview.checks": 1.0,
        "interview2.strengths": 1.0,
        "interview2.checks": 0.0,
    }
    assert [item.id for item in enriched.evidence] == [
        "e-A-0017-interview-1",
        "e-A-0017-interview-2",
        "e-A-0017-interview2-1",
    ]
    first_evidence = enriched.evidence[0]
    assert first_evidence.quote == "제가 설계를 맡았습니다" and "원문" not in first_evidence.text
    assert first_evidence.label in ("강점", "확인할 점")
