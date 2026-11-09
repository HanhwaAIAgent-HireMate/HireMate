"""서류 읽기: 서류 하나를 한 번 물어 사실 · 기간 추출과 그 서류의 정리(요약)를 함께 받는다.

추출 규칙(extract)과 정리 규칙(자기소개서 문항 요약, 이력서 · 포트폴리오 정리)은 그대로 두고 한 호출에 묶는다.
같은 서류를 보는 일이라 따로 물으면 서류를 두 번 보내야 했다. 서류 여러 개를 한 호출에 합치지는 않는다 (긴
포트폴리오에서 출력 한도를 넘는다). 묶어 물은 답이 출력 한도에서 잘리면 추출과 정리를 따로 다시 묻는다.
근거 문장이 원문에 있는지 거르는 일은 각 정리 코드가 그대로 한다 (merge, letter_sections, resume_digest …).
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask, truncated
from hiremate_ai.agents.analysis.application.digest import (
    PORTFOLIO_RULES,
    RESUME_RULES,
    PortfolioDigest,
    ResumeDigest,
    digest_document,
    portfolio_digest,
    resume_digest,
)
from hiremate_ai.agents.analysis.application.extract import (
    EXTRACT_RULES,
    SUMMARY_RULES,
    ExtractedFact,
    ExtractedFacts,
    ExtractedPeriod,
    ExtractedSection,
    extract_one,
    letter_sections,
    summarize,
)
from hiremate_ai.agents.analysis.application.types import DocumentDigest, DocumentSection
from hiremate_ai.contract import ApplicantDocument, DocumentType
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, document_block
from hiremate_ai.llm.recipe import analysis_recipe, fingerprint

READING_VERSION = "document-reading-1"


class DocumentReading(BaseModel):
    """서류 하나의 읽기 답. 자격증 사본처럼 따로 정리하지 않는 서류는 사실과 기간만 받는다."""

    facts: list[ExtractedFact] = []
    periods: list[ExtractedPeriod] = []


class ResumeReading(DocumentReading):
    resume: ResumeDigest = Field(default_factory=ResumeDigest, description="이력서 정리 표")


class LetterReading(DocumentReading):
    sections: list[ExtractedSection] = Field(default=[], description="자기소개서 문항별 요약")


class PortfolioReading(DocumentReading):
    portfolio: PortfolioDigest = Field(default_factory=PortfolioDigest, description="포트폴리오 프로젝트 카드")


def _system(field: str, title: str, lead: str, rules: str) -> str:
    return f"""너는 채용 서류 한 건을 읽고 두 가지를 한 번에 정리한다. 판단이나 점수는 매기지 않는다.

# 입력
- 서류: 제출 문서 한 건의 원문.

# 출력 (이 순서로 쓴다)
1. facts, periods: 지원자에 관한 사실과 근무 · 활동 기간.
2. {field}: {title}.

# 공통 원칙
- 서류 처음부터 끝까지 모두 본다. 표 · 목록 · 문단의 내용을 빠뜨리지 않는다.
- 근거 문장(evidence)은 원문 글자 그대로 옮긴다. 원문에 없는 문장을 만들지 않는다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다.

## 1. 사실과 기간 (facts, periods)
{EXTRACT_RULES}

## 2. {title} ({field})
- {lead}
{rules}

{UNTRUSTED_RULE}"""


@dataclass(frozen=True)
class _Kind:
    output: type[DocumentReading]
    system: str
    request: str


_KINDS: dict[DocumentType, _Kind] = {
    DocumentType.RESUME: _Kind(
        ResumeReading,
        _system("resume", "이력서 정리", "이력서 한 건을 담당자가 훑어보기 좋은 표로 정리한다.", RESUME_RULES),
        "위 이력서에서 사실과 기간을 뽑고, 이력서를 표로 정리해 줘.",
    ),
    DocumentType.COVER_LETTER: _Kind(
        LetterReading,
        _system("sections", "자기소개서 요약", "자기소개서 한 건을 문항마다 요약한다.", SUMMARY_RULES),
        "위 자기소개서에서 사실과 기간을 뽑고, 문항마다 요약해 줘.",
    ),
    DocumentType.PORTFOLIO: _Kind(
        PortfolioReading,
        _system("portfolio", "포트폴리오 정리", "포트폴리오 한 건을 프로젝트마다 카드로 정리한다.", PORTFOLIO_RULES),
        "위 포트폴리오에서 사실과 기간을 뽑고, 프로젝트마다 정리해 줘.",
    ),
}


@dataclass(frozen=True)
class Reading:
    """서류 하나를 읽은 결과. extracted는 근거를 거르기 전의 추출(merge가 거른다), 나머지는 거른 정리다."""

    extracted: ExtractedFacts
    sections: list[DocumentSection] = field(default_factory=list)
    digest: DocumentDigest | None = None


def reading_type(document: ApplicantDocument) -> type[DocumentReading]:
    """서류 종류마다 받는 형식. 저장한 읽기 답을 다시 읽을 때도 쓴다."""
    kind = _KINDS.get(document.type)
    return kind.output if kind else DocumentReading


def reading_recipe(llm: LlmClient) -> str | None:
    """저장한 읽기 답을 다시 쓸 수 있는지 가르는 지문. 모델 · 지시문 · 형식이 바뀌면 다시 묻는다."""
    recipe = analysis_recipe(llm)
    if recipe is None:
        return None
    return fingerprint(
        {
            "version": READING_VERSION,
            "llm": recipe,
            "systems": {kind.value: found.system for kind, found in _KINDS.items()},
            "schemas": {kind.value: found.output.model_json_schema() for kind, found in _KINDS.items()},
            "extract": EXTRACT_RULES,
        }
    )


async def read_documents(
    llm: LlmClient,
    documents: Sequence[ApplicantDocument],
    concurrency: int,
    *,
    blind: bool = False,
    cached: Sequence[DocumentReading | None] | None = None,
) -> tuple[list[Reading], list[DocumentReading | None]]:
    """서류마다 한 번씩, 동시에 concurrency개까지 묻는다. (거른 결과, 저장할 답)을 documents 순서로 돌려준다.

    cached에 저장한 답이 있으면 그 서류는 묻지 않는다. 잘려서 따로 받은 서류는 저장할 답이 없다(None).
    """
    gate = asyncio.Semaphore(concurrency)
    previous = list(cached) if cached is not None else [None] * len(documents)
    if len(previous) != len(documents):
        raise ValueError("읽기 결과와 문서 수가 다르다")

    async def one(document: ApplicantDocument, saved: DocumentReading | None) -> tuple[Reading, DocumentReading | None]:
        if saved is not None:
            return settle(document, saved, blind=blind), saved
        async with gate:
            return await _read(llm, document, blind)

    pairs = await asyncio.gather(*(one(document, saved) for document, saved in zip(documents, previous, strict=True)))
    return [reading for reading, _ in pairs], [answer for _, answer in pairs]


async def _read(llm: LlmClient, document: ApplicantDocument, blind: bool) -> tuple[Reading, DocumentReading | None]:
    kind = _KINDS.get(document.type)
    if kind is None:
        extracted = await extract_one(llm, document)
        answer = DocumentReading(facts=extracted.facts, periods=extracted.periods)
        return settle(document, answer, blind=blind), answer
    try:
        user = f"# 서류\n{document_block(document)}\n\n# 요청\n{kind.request}"
        answer = await ask(llm, kind.output, system=kind.system, user=user)
    except Exception as error:
        if not truncated(error):
            raise
        # 묶어 물은 답이 출력 한도에서 잘렸다: 추출과 정리를 따로 묻는다 (이 답은 저장하지 않는다)
        extracted, (sections, digest) = await asyncio.gather(extract_one(llm, document), _summary(llm, document, blind))
        return Reading(extracted, sections, digest), None
    return settle(document, answer, blind=blind), answer


async def _summary(
    llm: LlmClient, document: ApplicantDocument, blind: bool
) -> tuple[list[DocumentSection], DocumentDigest | None]:
    if document.type == DocumentType.COVER_LETTER:
        return await summarize(llm, [document], blind=blind), None
    found = await digest_document(llm, document, blind=blind)
    return [], found if found.sections else None


def settle(document: ApplicantDocument, answer: DocumentReading, *, blind: bool = False) -> Reading:
    """모델 답을 서류 종류에 맞는 정리로 거른다 (근거 문장이 원문에 있는 것만 남긴다)."""
    extracted = ExtractedFacts(facts=answer.facts, periods=answer.periods)
    if isinstance(answer, LetterReading):
        return Reading(extracted, sections=letter_sections(document, answer.sections, blind=blind))
    if isinstance(answer, ResumeReading):
        found = resume_digest(document, answer.resume, blind=blind)
        return Reading(extracted, digest=found if found.sections else None)
    if isinstance(answer, PortfolioReading):
        found = portfolio_digest(document, answer.portfolio, blind=blind)
        return Reading(extracted, digest=found if found.sections else None)
    return Reading(extracted)
