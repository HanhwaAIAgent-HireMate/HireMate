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


SCHOOL_TEXT = (
    "학력\n한빛대학교 컴퓨터공학과 2016.03 ~ 2020.02 졸업\n"
    "한빛대학교 캡스톤 프로젝트에서 결제 앱을 만들었습니다.\n"
    "Java와 Spring Boot로 정산 API를 개발했습니다."
)
SCHOOL_DOCUMENT = ApplicantDocument(
    type=DocumentType.RESUME, file_id=uuid4(), file_name="이력서.pdf", size=1, text=SCHOOL_TEXT
)
SCHOOL_FACTS = ExtractedFacts(
    facts=[
        ExtractedFact(
            kind="EDUCATION", statement="컴퓨터공학을 전공했다", actor="SELF", evidence=["한빛대학교 컴퓨터공학과"]
        ),
        ExtractedFact(
            kind="PROJECT",
            statement="캡스톤 프로젝트에서 결제 앱을 만들었다",
            actor="SELF",
            evidence=["한빛대학교 캡스톤 프로젝트에서 결제 앱을 만들었습니다."],
        ),
        ExtractedFact(
            kind="SKILL",
            statement="Java로 정산 API를 개발했다",
            actor="SELF",
            evidence=["Java와 Spring Boot로 정산 API를 개발했습니다."],
        ),
    ],
    periods=[
        ExtractedPeriod(
            company="한빛대학교",
            kind="EDUCATION",
            start="2016-03",
            end="2020-02",
            evidence=["한빛대학교 컴퓨터공학과 2016.03 ~ 2020.02 졸업"],
        )
    ],
)


def test_merge_drops_education_facts_only_for_blind_hiring() -> None:
    """블라인드 채용이면 학력 사실과, 근거 문장에 학교가 나오는 사실을 통째로 뺀다 (근거는 원문 그대로여야 한다)."""
    facts, periods = merge([SCHOOL_DOCUMENT], [SCHOOL_FACTS], TODAY, blind=True)

    assert [fact.statement for fact in facts] == ["Java로 정산 API를 개발했다"]
    assert periods == []

    facts, periods = merge([SCHOOL_DOCUMENT], [SCHOOL_FACTS], TODAY)

    assert len(facts) == 3
    assert [period.company for period in periods] == ["한빛대학교"]
