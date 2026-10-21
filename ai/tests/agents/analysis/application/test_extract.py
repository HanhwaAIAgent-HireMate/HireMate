from uuid import uuid4

from application_context import TODAY

from hiremate_ai.agents.analysis.application.extract import (
    ExtractedFact,
    ExtractedFacts,
    ExtractedPeriod,
    locate,
    merge,
)
from hiremate_ai.agents.analysis.application.types import Actor
from hiremate_ai.contract import ApplicantDocument, DocumentType

TEXT = "경력\n한빛카드 결제플랫폼팀 2022.03 ~ 현재\n- 카드 결제 승인 · 정산 API를\nJava와 Spring Boot로 개발했습니다."
DOCUMENT = ApplicantDocument(type=DocumentType.RESUME, file_id=uuid4(), file_name="이력서.pdf", size=1, text=TEXT)


def test_locate_returns_original_text_across_line_breaks() -> None:
    quote = locate("카드 결제 승인 · 정산 API를 Java와 Spring Boot로 개발했습니다.", [DOCUMENT])

    assert quote is not None
    assert quote.document == DocumentType.RESUME
    assert quote.sentence == "카드 결제 승인 · 정산 API를\nJava와 Spring Boot로 개발했습니다."
    assert quote.sentence in TEXT


def test_locate_drops_sentences_not_in_documents() -> None:
    assert locate("결제 시스템 전체 설계를 주도했습니다.", [DOCUMENT]) is None
    assert locate("API", [DOCUMENT]) is None


def test_merge_keeps_only_facts_and_periods_with_real_quotes() -> None:
    extracted = ExtractedFacts(
        facts=[
            ExtractedFact(
                kind="EXPERIENCE",
                statement="결제 API를 개발했다",
                actor="SELF",
                evidence=["Java와 Spring Boot로 개발했습니다."],
            ),
            ExtractedFact(
                kind="ACHIEVEMENT", statement="설계를 주도했다", actor="SELF", evidence=["전체 설계를 주도했습니다."]
            ),
        ],
        periods=[
            ExtractedPeriod(
                company="한빛카드",
                kind="EMPLOYMENT",
                start="2022-03",
                evidence=["한빛카드 결제플랫폼팀 2022.03 ~ 현재"],
            ),
            ExtractedPeriod(
                company="가상회사", kind="EMPLOYMENT", start="2010-01", evidence=["가상회사 2010.01 ~ 2020.01"]
            ),
        ],
    )

    facts, periods = merge([DOCUMENT], [extracted], TODAY)

    assert [fact.statement for fact in facts] == ["결제 API를 개발했다"]
    assert facts[0].actor == Actor.SELF
    assert [(period.company, period.months) for period in periods] == [("한빛카드", 55)]
