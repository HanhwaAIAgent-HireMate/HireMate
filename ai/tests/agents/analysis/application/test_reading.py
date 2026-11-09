"""서류 읽기: 서류마다 한 번 물어 사실 추출과 그 서류의 정리를 함께 받고, 잘리면 나눠 다시 묻는지 본다."""

from uuid import uuid4

from hiremate_ai.agents.analysis.application.ask import ATTEMPTS
from hiremate_ai.agents.analysis.application.digest import PortfolioDigest, _Project
from hiremate_ai.agents.analysis.application.extract import (
    ExtractedFact,
    ExtractedFacts,
    ExtractedSection,
    LetterSummary,
)
from hiremate_ai.agents.analysis.application.reading import (
    LetterReading,
    PortfolioReading,
    ResumeReading,
    read_documents,
    reading_type,
)
from hiremate_ai.contract import ApplicantDocument, DocumentType
from hiremate_ai.llm.fake import FakeLlm, LlmCall
from hiremate_ai.llm.prompt import UNTRUSTED_RULE

API = "카드 결제 승인 API를 Java로 개발했습니다."
MOTIVE = "결제 신뢰를 지키는 일을 하고 싶어 지원했습니다."
CACHE = "Redis 캐시를 도입해 조회 시간을 120ms에서 40ms로 줄였습니다."


def document(kind: DocumentType, text: str) -> ApplicantDocument:
    return ApplicantDocument(type=kind, file_id=uuid4(), file_name=f"{kind.label}.pdf", size=1, text=text)


LETTER = document(DocumentType.COVER_LETTER, f"1. 지원 동기\n{MOTIVE}\n2. 경험\n{API}")
PORTFOLIO = document(DocumentType.PORTFOLIO, f"주문 조회 개선\n{CACHE}")
FACT = ExtractedFact(kind="EXPERIENCE", statement="결제 승인 API를 개발했다.", actor="SELF", evidence=[API])


class LengthFinishReasonError(Exception):
    """openai.LengthFinishReasonError와 이름이 같은 테스트용 오류. 모델 답이 출력 한도에서 잘렸다."""


def cut_off(call: LlmCall) -> LetterReading:
    raise LengthFinishReasonError("length limit was reached")


async def test_each_document_is_read_once_with_its_summary() -> None:
    letter = LetterReading(
        facts=[FACT],
        sections=[ExtractedSection(title="지원 동기", summary="결제 신뢰를 지키고 싶어 지원했다.", evidence=[MOTIVE])],
    )
    project = _Project(title="주문 조회 개선", problem="조회 지연", solution="Redis 캐시 도입", evidence=[CACHE])
    portfolio = PortfolioReading(portfolio=PortfolioDigest(projects=[project]))
    llm = FakeLlm(letter, portfolio)

    readings, answers = await read_documents(llm, [LETTER, PORTFOLIO], 1)

    # 서류마다 한 번 묻고, 한 호출에서 사실과 정리를 함께 받는다
    assert [call.output for call in llm.calls] == [LetterReading, PortfolioReading]
    assert all(UNTRUSTED_RULE in call.system and '<data kind="document"' in call.user for call in llm.calls)
    assert "[사실과 기간]" in llm.calls[0].system and "[자기소개서 요약] sections" in llm.calls[0].system
    assert readings[0].extracted.facts == [FACT]
    assert [section.title for section in readings[0].sections] == ["지원 동기"]
    assert readings[1].digest is not None and readings[1].digest.sections[0].rows[0].title == "주문 조회 개선"
    assert answers == [letter, portfolio]  # 저장할 답


async def test_cut_off_answer_is_asked_again_in_two_parts() -> None:
    summary = LetterSummary(sections=[ExtractedSection(title="지원 동기", summary="지원했다.", evidence=[MOTIVE])])
    llm = FakeLlm(*([cut_off] * ATTEMPTS), ExtractedFacts(facts=[FACT]), summary)

    [reading], [answer] = await read_documents(llm, [LETTER], 1)

    # 묶어 물은 답이 출력 한도에서 잘리면 추출과 요약을 따로 묻고, 그 답은 저장하지 않는다
    assert [call.output for call in llm.calls][ATTEMPTS:] == [ExtractedFacts, LetterSummary]
    assert reading.extracted.facts == [FACT] and [section.title for section in reading.sections] == ["지원 동기"]
    assert answer is None


async def test_saved_reading_is_used_without_asking() -> None:
    saved = ResumeReading(facts=[FACT])
    resume = document(DocumentType.RESUME, API)
    llm = FakeLlm()

    [reading], [answer] = await read_documents(llm, [resume], 1, cached=[saved])

    assert llm.calls == []
    assert reading.extracted.facts == [FACT] and answer == saved
    assert reading_type(resume) is ResumeReading
