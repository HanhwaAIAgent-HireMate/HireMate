"""Application 부분: 제출 문서마다 사실 · 근거 · 경력 기간을 뽑고(모델), 근거가 원문에 있는지 코드가 확인해 합친다.

판단과 점수는 여기서 하지 않는다. 판정은 Assessment 부분(judge)이 이 결과와 원문을 받아 한다.
"""

import asyncio
import re
import unicodedata
from collections.abc import Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.career import months_between
from hiremate_ai.agents.analysis.application.types import Actor, DocumentSection, Fact, Period, Quote
from hiremate_ai.agents.guardrails import evidence_source
from hiremate_ai.contract import ApplicantDocument, DocumentType
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, document_block
from hiremate_ai.llm.recipe import analysis_recipe, fingerprint

EXTRACT_SYSTEM = f"""너는 채용 서류 한 건에서 지원자에 관한 사실을 뽑는다. 판단이나 점수는 매기지 않는다.

- 사실마다 근거 문장(evidence)을 원문 글자 그대로 옮긴다. 원문에 없는 문장을 만들지 않는다.
- statement는 원문보다 부풀리지 않고 한 문장으로 쓴다. '참여'를 '주도'로, 팀 성과를 개인 성과로 바꾸지 않는다.
- statement는 '~했다.', '~한다.', '~이다.'처럼 평어로 끝낸다. '~했습니다', '~했어요', 명사로 끝내기는 쓰지 않는다.
- actor: 본인이 직접 한 일이면 SELF, 팀 · 조직의 성과면 TEAM, 알 수 없으면 UNCLEAR.
- kind: EXPERIENCE(업무 경험), PROJECT(프로젝트), SKILL(기술 · 도구), CERTIFICATE(자격증), ACHIEVEMENT(수치 성과),
  ACTIVITY(교육 · 활동), EDUCATION(학력).
- periods에는 서류에 적힌 근무 · 활동 기간을 모두 뽑는다. start · end는 YYYY-MM이고 재직 중이면 end를 비운다.
  kind는 EMPLOYMENT(정규 · 계약 재직), INTERN, FREELANCE, PROJECT(교육 · 개인 프로젝트), EDUCATION 가운데 하나다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 뽑지 않는다.

{UNTRUSTED_RULE}"""


# 모델이 목록 밖의 종류를 쓰면 형식 오류로 분석 전체가 실패했다. 종류는 글로 받고 코드가 목록에 맞춘다
FACT_KINDS = ("EXPERIENCE", "PROJECT", "SKILL", "CERTIFICATE", "ACHIEVEMENT", "ACTIVITY", "EDUCATION")
PERIOD_KINDS = ("EMPLOYMENT", "INTERN", "FREELANCE", "PROJECT", "EDUCATION")


class ExtractedFact(BaseModel):
    kind: str = Field(description=" · ".join(FACT_KINDS) + " 가운데 하나")
    statement: str = Field(description="사실 한 문장. 원문보다 부풀리지 않는다")
    actor: Literal["SELF", "TEAM", "UNCLEAR"]
    evidence: list[str] = Field(default=[], description="근거 문장. 원문 글자 그대로")


class ExtractedPeriod(BaseModel):
    company: str = Field(description="회사 · 기관 · 프로젝트 이름")
    role: str = Field(default="", description="직무나 역할")
    kind: str = Field(description=" · ".join(PERIOD_KINDS) + " 가운데 하나")
    start: str = Field(description="YYYY-MM")
    end: str | None = Field(default=None, description="YYYY-MM. 재직 중이면 비운다")
    evidence: list[str] = Field(default=[], description="기간이 적힌 원문 문장. 글자 그대로")


class ExtractedSection(BaseModel):
    title: str = Field(description="문항 제목")
    summary: str = Field(description="그 문항에 쓴 내용 요약 1~2문장. 부풀리지 않는다")
    points: list[str] = Field(default=[], description="핵심 2~3개")
    evidence: list[str] = Field(default=[], description="요약을 받치는 원문 문장. 글자 그대로")


class LetterSummary(BaseModel):
    sections: list[ExtractedSection] = []


SUMMARY_SYSTEM = f"""너는 자기소개서 한 건을 문항마다 요약한다. 판단이나 점수는 매기지 않는다.

- 문항마다 하나씩, 문항 순서대로 쓴다. title은 문항 제목(번호와 글자 수 제한은 뺀다)이다.
- summary는 그 문항에 쓴 내용을 부풀리지 않은 1~2문장이다.
- summary 문장은 '~한다.', '~했다.'처럼 평서문으로 끝낸다.
- '~라고 썼다', '~라고 밝혔다'처럼 전하는 말투는 쓰지 않고 '지원자는'으로 시작하지 않는다.
- points는 핵심 2~3개, evidence는 요약을 받치는 원문 문장 1~2개(글자 그대로)다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다.

{UNTRUSTED_RULE}"""


class ExtractedFacts(BaseModel):
    facts: list[ExtractedFact] = []
    periods: list[ExtractedPeriod] = []


def extraction_recipe(llm: LlmClient) -> str | None:
    recipe = analysis_recipe(llm)
    return (
        fingerprint(
            {
                "version": "document-extraction-1",
                "llm": recipe,
                "system": EXTRACT_SYSTEM,
                "schema": ExtractedFacts.model_json_schema(),
            }
        )
        if recipe is not None
        else None
    )


async def extract_documents(
    llm: LlmClient,
    documents: Sequence[ApplicantDocument],
    concurrency: int,
    *,
    cached: Sequence[ExtractedFacts | None] | None = None,
) -> list[ExtractedFacts]:
    """문서마다 한 번씩, 동시에 concurrency개까지 모델을 부른다. 결과는 documents 순서다."""
    gate = asyncio.Semaphore(concurrency)
    previous = list(cached) if cached is not None else [None] * len(documents)
    if len(previous) != len(documents):
        raise ValueError("추출 결과와 문서 수가 다르다")

    async def one(document: ApplicantDocument, saved: ExtractedFacts | None) -> ExtractedFacts:
        if saved is not None:
            return saved
        async with gate:
            return await ask(
                llm,
                ExtractedFacts,
                system=EXTRACT_SYSTEM,
                user=f"{document_block(document)}\n\n위 {document.type.label}에서 사실과 기간을 뽑아 줘.",
            )

    return list(
        await asyncio.gather(*(one(document, saved) for document, saved in zip(documents, previous, strict=True)))
    )


def merge(
    documents: Sequence[ApplicantDocument], extracted: Sequence[ExtractedFacts], today: date
) -> tuple[list[Fact], list[Period]]:
    """원문에서 찾은 근거만 남겨 합친다. 근거가 하나도 남지 않은 사실과 기간은 버린다 (아키텍처 규칙 7)."""
    facts: list[Fact] = []
    periods: list[Period] = []
    seen: set[str] = set()
    for document, result in zip(documents, extracted, strict=True):
        for fact in result.facts:
            quotes = quotes_in([document], fact.evidence)
            key = _normalize(fact.statement)
            if quotes and key not in seen:
                seen.add(key)
                kind = fact.kind.strip().upper()
                facts.append(
                    Fact(
                        kind=kind if kind in FACT_KINDS else "ACTIVITY",
                        statement=fact.statement.strip(),
                        actor=Actor(fact.actor),
                        quotes=quotes,
                    )
                )
        for period in result.periods:
            found = quotes_in([document], period.evidence)
            months = months_between(period.start, period.end, today)
            kind = period.kind.strip().upper()
            if found and months is not None:
                periods.append(
                    Period(
                        company=period.company.strip(),
                        role=period.role.strip(),
                        # 알 수 없는 종류는 경력으로 세지 않는다
                        kind=kind if kind in PERIOD_KINDS else "PROJECT",
                        start=period.start,
                        end=period.end or None,
                        months=months,
                        quote=found[0],
                    )
                )
    return facts, periods


async def summarize(llm: LlmClient, documents: Sequence[ApplicantDocument]) -> list[DocumentSection]:
    """자기소개서 문항별 요약. 사실 추출과 따로 묻는다 (한 번에 받으면 긴 자기소개서에서 출력 한도를 넘었다).

    근거 문장은 원문에서 찾은 것만 남긴다.
    """
    sections = []
    for document in documents:
        if document.type != DocumentType.COVER_LETTER:
            continue
        result = await ask(
            llm,
            LetterSummary,
            system=SUMMARY_SYSTEM,
            user=f"{document_block(document)}\n\n위 자기소개서를 문항마다 요약해 줘.",
        )
        for section in result.sections:
            if section.title.strip() and section.summary.strip():
                sections.append(
                    DocumentSection(
                        document=document.type,
                        title=section.title.strip(),
                        summary=section.summary.strip(),
                        points=[point.strip() for point in section.points if point.strip()][:3],
                        quotes=quotes_in([document], section.evidence),
                    )
                )
    return sections


def quotes_in(documents: Sequence[ApplicantDocument], sentences: Sequence[str]) -> list[Quote]:
    """모델이 낸 근거 문장 가운데 원문에 있는 것만, 원문 글자 그대로 돌려준다. 같은 문장은 한 번만 넣는다."""
    quotes: list[Quote] = []
    for sentence in sentences:
        quote = locate(sentence, documents)
        if quote is not None and quote not in quotes:
            quotes.append(quote)
    return quotes


def locate(sentence: str, documents: Sequence[ApplicantDocument]) -> Quote | None:
    """근거 문장을 원문에서 찾는다. 공백 · 앞뒤 따옴표 차이는 무시하고, 화면 밑줄이 맞도록 원문 글자를 돌려준다."""
    needle = _strip(sentence)
    if len(needle) < 4:
        return None
    for document in documents:
        span = _find(document.text, needle)
        if span is not None:
            return Quote(document=document.type, sentence=document.text[span[0] : span[1]].strip())
    source = evidence_source(sentence, documents)
    return Quote(document=source, sentence=sentence.strip()) if source is not None else None


_EDGE = re.compile(r"^[\s·•\-*\"'“”‘’]+|[\s\"'“”‘’]+$")
_SPACE = re.compile(r"\s+")


def _strip(sentence: str) -> str:
    return _SPACE.sub("", unicodedata.normalize("NFKC", _EDGE.sub("", sentence)))


def _find(text: str, needle: str) -> tuple[int, int] | None:
    """공백을 뺀 needle이 text 어디에 있는지 원문 위치로 돌려준다."""
    positions = [index for index, char in enumerate(text) if not char.isspace()]
    compact = "".join(unicodedata.normalize("NFKC", text[index]) for index in positions)
    if len(compact) != len(positions):
        return None
    start = compact.find(needle)
    if start < 0:
        return None
    return positions[start], positions[start + len(needle) - 1] + 1


def _normalize(text: str) -> str:
    return _SPACE.sub("", text)
