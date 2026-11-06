from uuid import uuid4

from application_context import TODAY
from pydantic import BaseModel

from hiremate_ai.agents.analysis.application.extract import (
    ExtractedFact,
    ExtractedFacts,
    ExtractedPeriod,
    ExtractedSection,
    LetterSummary,
    locate,
    merge,
    summarize,
)
from hiremate_ai.agents.analysis.application.types import Actor
from hiremate_ai.contract import ApplicantDocument, DocumentType
from hiremate_ai.llm.fake import FakeLlm, LlmCall

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
    assert [(period.company, period.months) for period in periods] == [("한빛카드", 56)]


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


MASKED_TEXT = (
    "학력\n○○학교 컴퓨터공학과 2016.03 ~ 2020.02 졸업, 학점 ○○\n"
    "학업 경험\n○○학교에서 자료구조와 데이터베이스를 깊이 공부했습니다.\n"
    "석사 학위를 받았습니다."
)
MASKED_DOCUMENT = ApplicantDocument(
    type=DocumentType.RESUME, file_id=uuid4(), file_name="이력서.pdf", size=1, text=MASKED_TEXT
)
MASKED_FACTS = ExtractedFacts(
    facts=[
        ExtractedFact(
            kind="EDUCATION", statement="컴퓨터공학을 전공했다", actor="SELF", evidence=["○○학교 컴퓨터공학과"]
        ),
        ExtractedFact(
            kind="EDUCATION",
            statement="자료구조와 데이터베이스를 공부했다",
            actor="SELF",
            evidence=["○○학교에서 자료구조와 데이터베이스를 깊이 공부했습니다."],
        ),
        ExtractedFact(
            kind="EDUCATION", statement="석사 학위를 받았다", actor="SELF", evidence=["석사 학위를 받았습니다."]
        ),
        ExtractedFact(
            kind="ACHIEVEMENT", statement="학점이 높다", actor="SELF", evidence=["2016.03 ~ 2020.02 졸업, 학점 ○○"]
        ),
    ],
    periods=[
        ExtractedPeriod(
            company="○○학교",
            kind="EDUCATION",
            start="2016-03",
            end="2020-02",
            evidence=["○○학교 컴퓨터공학과 2016.03 ~ 2020.02 졸업"],
        )
    ],
)


def test_blind_merge_keeps_what_was_studied_and_drops_degree_and_grades() -> None:
    """학교 이름 · 학점을 가려 저장한 블라인드 서류에서, 전공과 공부한 과목은 직무 역량이라 남긴다.
    학위 · 학점처럼 학력 수준이 드러나는 사실과, 다닌 햇수가 드러나는 학력 기간은 뺀다."""
    facts, periods = merge([MASKED_DOCUMENT], [MASKED_FACTS], TODAY, blind=True)

    assert [fact.statement for fact in facts] == ["컴퓨터공학을 전공했다", "자료구조와 데이터베이스를 공부했다"]
    assert periods == []


LETTER_TEXT = (
    "학업 경험\n학점 4.1/4.5로 졸업했습니다.\n협업 경험\n팀과 정산 배치 구조를 바꿨습니다. 학점 관리도 꾸준히 했습니다."
)
LETTER = ApplicantDocument(
    type=DocumentType.COVER_LETTER, file_id=uuid4(), file_name="자기소개서.pdf", size=1, text=LETTER_TEXT
)
LETTER_SUMMARY = LetterSummary(
    sections=[
        ExtractedSection(
            title="학업 경험", summary="학점 4.1로 졸업했다고 썼다.", evidence=["학점 4.1/4.5로 졸업했습니다."]
        ),
        ExtractedSection(
            title="협업 경험",
            summary="팀과 정산 배치 구조를 바꿨다고 썼다.",
            points=["정산 배치 구조 개선", "학점 관리"],
            evidence=["팀과 정산 배치 구조를 바꿨습니다.", "학점 관리도 꾸준히 했습니다."],
        ),
    ]
)


async def test_summarize_drops_education_only_for_blind_hiring() -> None:
    """블라인드 채용이면 학력 문항은 통째로, 다른 문항의 학력 요점 · 근거는 그것만 뺀다."""
    [section] = await summarize(FakeLlm(LETTER_SUMMARY), [LETTER], blind=True)

    assert section.title == "협업 경험"
    assert section.points == ["정산 배치 구조 개선"]
    assert [quote.sentence for quote in section.quotes] == ["팀과 정산 배치 구조를 바꿨습니다."]

    sections = await summarize(FakeLlm(LETTER_SUMMARY), [LETTER])

    assert [section.title for section in sections] == ["학업 경험", "협업 경험"]
    assert len(sections[1].quotes) == 2


async def test_second_review_corrects_and_adds_document_facts() -> None:
    from hiremate_ai.agents.analysis.application.extract import extract_documents
    from hiremate_ai.agents.analysis.application.review import ClaimReview, ReviewJudgement

    original = ExtractedFacts(
        facts=[
            ExtractedFact(
                kind="EXPERIENCE",
                statement="결제 플랫폼을 혼자 총괄했다",
                actor="SELF",
                evidence=["Java와 Spring Boot로 개발했습니다."],
            )
        ]
    )

    def correction(call: LlmCall) -> BaseModel:
        return call.output.model_validate(
            {
                "facts": [
                    {
                        "index": 1,
                        "replacement": {
                            "kind": "EXPERIENCE",
                            "statement": "결제 API를 개발했다",
                            "actor": "SELF",
                            "evidence": ["Java와 Spring Boot로 개발했습니다."],
                        },
                    }
                ],
                "periods": [],
                "added_facts": [
                    {
                        "kind": "SKILL",
                        "statement": "Spring Boot를 사용했다",
                        "actor": "SELF",
                        "evidence": ["Java와 Spring Boot로 개발했습니다."],
                    },
                    {
                        "kind": "EXPERIENCE",
                        "statement": "가짜 성과",
                        "actor": "SELF",
                        "evidence": ["서류에 없는 내용입니다."],
                    },
                ],
                "added_periods": [],
            }
        )

    supported = ReviewJudgement(
        reviews=[ClaimReview(id="F1", verdict="SUPPORTED"), ClaimReview(id="F2", verdict="SUPPORTED")]
    )
    llm = FakeLlm(original, correction, supported)
    [reviewed] = await extract_documents(llm, [DOCUMENT], 1, review=True)
    facts, _ = merge([DOCUMENT], [reviewed], TODAY)

    assert [fact.statement for fact in facts] == ["결제 API를 개발했다", "Spring Boot를 사용했다"]
    assert len(llm.calls) == 3
    assert "결제 플랫폼을 혼자 총괄했다" in llm.calls[1].user
    assert TEXT in llm.calls[1].user


async def test_second_review_does_not_replace_evidence_with_invented_quote() -> None:
    from hiremate_ai.agents.analysis.application.extract import extract_documents

    original = ExtractedFacts(
        facts=[
            ExtractedFact(
                kind="EXPERIENCE",
                statement="결제 API를 개발했다",
                actor="SELF",
                evidence=["Java와 Spring Boot로 개발했습니다."],
            )
        ]
    )

    def correction(call: LlmCall) -> BaseModel:
        return call.output.model_validate(
            {
                "facts": [
                    {
                        "index": 1,
                        "replacement": {
                            "kind": "EXPERIENCE",
                            "statement": "시스템을 주도했다",
                            "actor": "SELF",
                            "evidence": ["이 문장은 원문에 없습니다."],
                        },
                    }
                ]
            }
        )

    [reviewed] = await extract_documents(FakeLlm(original, correction), [DOCUMENT], 1, review=True)
    facts, _ = merge([DOCUMENT], [reviewed], TODAY)

    assert [fact.statement for fact in facts] == ["결제 API를 개발했다"]


async def test_second_review_drops_claim_not_supported_by_its_real_quote() -> None:
    from hiremate_ai.agents.analysis.application.extract import extract_documents
    from hiremate_ai.agents.analysis.application.review import ClaimReview, ReviewJudgement

    original = ExtractedFacts()

    def correction(call: LlmCall) -> BaseModel:
        return call.output.model_validate(
            {
                "added_facts": [
                    {
                        "kind": "ACHIEVEMENT",
                        "statement": "중복 승인을 0건으로 줄였다",
                        "actor": "SELF",
                        "evidence": ["Java와 Spring Boot로 개발했습니다."],
                    }
                ]
            }
        )

    judgement = ReviewJudgement(reviews=[ClaimReview(id="F1", verdict="UNSUPPORTED", reason="수치 근거 없음")])
    llm = FakeLlm(original, correction, judgement)
    [reviewed] = await extract_documents(llm, [DOCUMENT], 1, review=True)
    facts, _ = merge([DOCUMENT], [reviewed], TODAY)

    assert facts == []


async def test_second_review_preserves_original_if_deletion_is_not_supported() -> None:
    from hiremate_ai.agents.analysis.application.extract import extract_documents
    from hiremate_ai.agents.analysis.application.review import ClaimReview, ReviewJudgement

    original = ExtractedFacts(
        facts=[
            ExtractedFact(
                kind="EXPERIENCE",
                statement="결제 API를 개발했다",
                actor="SELF",
                evidence=["카드 결제 승인 \N{MIDDLE DOT} 정산 API를\nJava와 Spring Boot로 개발했습니다."],
            )
        ]
    )

    def correction(call: LlmCall) -> BaseModel:
        return call.output.model_validate({"facts": [{"index": 1, "replacement": None}]})

    judgment = ReviewJudgement(reviews=[ClaimReview(id="F1", verdict="SUPPORTED")])
    [reviewed] = await extract_documents(FakeLlm(original, correction, judgment), [DOCUMENT], 1, review=True)

    assert [fact.statement for fact in reviewed.facts] == ["결제 API를 개발했다"]


async def test_second_review_keeps_a_quote_that_supports_the_added_fact() -> None:
    from hiremate_ai.agents.analysis.application.extract import extract_documents
    from hiremate_ai.agents.analysis.application.review import ClaimReview, ReviewJudgement

    def correction(call: LlmCall) -> BaseModel:
        return call.output.model_validate(
            {
                "added_facts": [
                    {
                        "kind": "EXPERIENCE",
                        "statement": "Java와 Spring Boot를 사용했다",
                        "actor": "SELF",
                        "evidence": ["한빛카드 결제플랫폼팀 2022.03 ~ 현재", "Java와 Spring Boot로 개발했습니다."],
                    }
                ]
            }
        )

    judgment = ReviewJudgement(
        reviews=[ClaimReview(id="F1", verdict="UNSUPPORTED"), ClaimReview(id="F2", verdict="SUPPORTED")]
    )
    [reviewed] = await extract_documents(FakeLlm(ExtractedFacts(), correction, judgment), [DOCUMENT], 1, review=True)

    assert len(reviewed.facts) == 1
    assert reviewed.facts[0].evidence == ["Java와 Spring Boot로 개발했습니다."]


async def test_second_review_fails_when_claim_verification_is_omitted() -> None:
    import pytest

    from hiremate_ai.agents.analysis.application.extract import extract_documents
    from hiremate_ai.agents.analysis.application.review import ReviewJudgement
    from hiremate_ai.llm.chat import LlmOutputError

    def correction(call: LlmCall) -> BaseModel:
        return call.output.model_validate(
            {
                "added_facts": [
                    {
                        "kind": "SKILL",
                        "statement": "Spring Boot를 사용했다",
                        "actor": "SELF",
                        "evidence": ["Java와 Spring Boot로 개발했습니다."],
                    }
                ]
            }
        )

    with pytest.raises(LlmOutputError):
        await extract_documents(
            FakeLlm(ExtractedFacts(), correction, ReviewJudgement(reviews=[])), [DOCUMENT], 1, review=True
        )
