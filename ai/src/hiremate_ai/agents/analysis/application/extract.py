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
from hiremate_ai.agents.guardrails import education_term, evidence_source
from hiremate_ai.contract import ApplicantDocument, DocumentType
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, document_block
from hiremate_ai.llm.recipe import analysis_recipe, fingerprint

# 사실 · 기간 추출 규칙. 서류 읽기(reading)가 서류 정리 규칙과 함께 한 번에 묻는다
EXTRACT_RULES = """- 사실마다 근거 문장(evidence)을 원문 글자 그대로 옮긴다. 원문에 없는 문장을 만들지 않는다.
- statement는 원문보다 부풀리지 않고 한 문장으로 쓴다. '참여'를 '주도'로, 팀 성과를 개인 성과로 바꾸지 않는다.
- 수치 성과는 원문이 붙인 측정 조건 · 출처 · 기여 한계(예: '회사 적용 당시 수치', '같은 기간 다른 개편 효과 포함',
  '로컬 테스트', '팀 공동 작업')를 statement에 그대로 남긴다. 표의 수치는 열 머리와 표 아래 주석까지 보고,
  어느 프로젝트 · 환경의 수치인지 바꾸지 않는다.
- 문제 → 행동 → 결과가 한 문단에 이어지면 결과까지 statement에 담는다 (예: '구조를 바꿨고 그 뒤 문제가 사라졌다').
- 계획 · 예정 · 학습 중인 일은 그렇다고 statement에 쓴다. 한 일처럼 쓰지 않는다.
- statement는 '~했다.', '~한다.', '~이다.'처럼 평어로 끝낸다. '~했습니다', '~했어요', 명사로 끝내기는 쓰지 않는다.
- actor: 본인이 직접 한 일이면 SELF, 팀 · 조직의 성과면 TEAM, 알 수 없으면 UNCLEAR.
- kind: EXPERIENCE(업무 경험), PROJECT(프로젝트), SKILL(기술 · 도구), CERTIFICATE(자격증), ACHIEVEMENT(수치 성과),
  ACTIVITY(교육 · 활동), EDUCATION(학력).
- periods에는 서류에 적힌 근무 · 활동 기간을 모두 뽑는다. start · end는 YYYY-MM이고 재직 중이면 end를 비운다.
  start · end는 근거 문장에 적힌 날짜만 쓴다. 적혀 있지 않은 날짜를 기간 · 나이 등으로 계산하거나 짐작하지 않는다.
  kind는 EMPLOYMENT(정규 · 계약 재직), INTERN, FREELANCE, PROJECT(교육 · 개인 프로젝트), EDUCATION,
  OTHER(병역 · 봉사 · 어학연수 · 동아리처럼 재직이 아닌 활동) 가운데 하나다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 뽑지 않는다."""

EXTRACT_SYSTEM = f"""너는 채용 서류 한 건에서 지원자에 관한 사실을 뽑는다. 판단이나 점수는 매기지 않는다.

{EXTRACT_RULES}

{UNTRUSTED_RULE}"""


# 모델이 목록 밖의 종류를 쓰면 형식 오류로 분석 전체가 실패했다. 종류는 글로 받고 코드가 목록에 맞춘다
FACT_KINDS = ("EXPERIENCE", "PROJECT", "SKILL", "CERTIFICATE", "ACHIEVEMENT", "ACTIVITY", "EDUCATION")
PERIOD_KINDS = ("EMPLOYMENT", "INTERN", "FREELANCE", "PROJECT", "EDUCATION", "OTHER")
# 근무로 보는 기간. 날짜가 모두 원문에 적혀 있어야 받는다
WORK_PERIOD_KINDS = ("EMPLOYMENT", "INTERN", "FREELANCE")


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


# 자기소개서 문항별 요약 규칙
SUMMARY_RULES = """- 문항마다 하나씩, 문항 순서대로 쓴다. title은 문항 제목(번호와 글자 수 제한은 뺀다)이다.
- summary는 그 문항에 쓴 내용을 부풀리지 않은 1~2문장이다.
- summary 문장은 '~한다.', '~했다.'처럼 평서문으로 끝낸다.
- '~라고 썼다', '~라고 밝혔다'처럼 전하는 말투는 쓰지 않고 '지원자는'으로 시작하지 않는다.
- points는 핵심 2~3개, evidence는 요약을 받치는 원문 문장 1~2개(글자 그대로)다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다."""

SUMMARY_SYSTEM = f"""너는 자기소개서 한 건을 문항마다 요약한다. 판단이나 점수는 매기지 않는다.

{SUMMARY_RULES}

{UNTRUSTED_RULE}"""


class ExtractedFacts(BaseModel):
    facts: list[ExtractedFact] = []
    periods: list[ExtractedPeriod] = []


def extraction_recipe(llm: LlmClient) -> str | None:
    """사실 추출만 따로 묻는 결과(Root의 서류 검토)를 다시 쓸 때의 레시피. 원문 대조 검토 칸은 비운 채로 두어
    저장된 추출 결과의 지문을 바꾸지 않는다."""
    recipe = analysis_recipe(llm)
    return (
        fingerprint(
            {
                "version": "document-extraction-1",
                "llm": recipe,
                "system": EXTRACT_SYSTEM,
                "schema": ExtractedFacts.model_json_schema(),
                "review": None,
                "review_version": None,
                "review_schema": None,
                "claim_review": None,
                "claim_schema": None,
                "claim_batch_size": None,
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
    """문서마다 한 번씩, 동시에 concurrency개까지 사실만 뽑는다. 결과는 documents 순서다 (Root의 서류 검토가 쓴다)."""
    gate = asyncio.Semaphore(concurrency)
    previous = list(cached) if cached is not None else [None] * len(documents)
    if len(previous) != len(documents):
        raise ValueError("추출 결과와 문서 수가 다르다")

    async def one(document: ApplicantDocument, saved: ExtractedFacts | None) -> ExtractedFacts:
        if saved is not None:
            return saved
        async with gate:
            return await extract_one(llm, document)

    return list(
        await asyncio.gather(*(one(document, saved) for document, saved in zip(documents, previous, strict=True)))
    )


async def extract_one(llm: LlmClient, document: ApplicantDocument) -> ExtractedFacts:
    """서류 하나의 사실 · 기간만 묻는다."""
    return await ask(
        llm,
        ExtractedFacts,
        system=EXTRACT_SYSTEM,
        user=f"{document_block(document)}\n\n위 {document.type.label}에서 사실과 기간을 뽑아 줘.",
    )


def merge(
    documents: Sequence[ApplicantDocument], extracted: Sequence[ExtractedFacts], today: date, *, blind: bool = False
) -> tuple[list[Fact], list[Period]]:
    """원문에서 찾은 근거만 남겨 합친다. 근거가 하나도 남지 않은 사실과 기간은 버린다 (아키텍처 규칙 7).

    블라인드 채용(blind)이면 출신 학교와 학력 수준(학위 · 학점 등)이 드러나는 사실과 학력 기간을 버린다.
    서류의 학교 이름 · 학점은 저장할 때 "○○"로 가려 두므로, 전공이나 공부한 과목처럼 직무와 관련된 학력 사실은 남긴다.
    근거 문장은 원문 그대로여야 해서 낱말만 가리지 않고 그 사실을 통째로 뺀다 (규칙 7).
    """
    facts: list[Fact] = []
    periods: list[Period] = []
    seen: set[str] = set()
    for document, result in zip(documents, extracted, strict=True):
        for fact in result.facts:
            quotes = quotes_in([document], fact.evidence)
            key = _normalize(fact.statement)
            kind = fact.kind.strip().upper()
            if blind and _mentions_education(fact.statement, quotes):
                continue
            if quotes and key not in seen:
                seen.add(key)
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
            # 학력 기간은 다닌 햇수로 학력 수준을 짐작할 수 있어 통째로 뺀다
            if blind and (kind == "EDUCATION" or _mentions_education(f"{period.company} {period.role}", found)):
                continue
            # 시작 · 끝 날짜가 근거 문장에 적혀 있어야 받는다. 모델이 서술에서 날짜를 계산해 넣으면
            # 같은 서류라도 실행마다 경력이 달라졌다
            if found and months is not None and _dates_written(period, found):
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


def _dates_written(period: ExtractedPeriod, quotes: Sequence[Quote]) -> bool:
    """날짜가 근거 문장에 적혀 있는가. 2024.05 · 2024-05 · 2024년 5월을 같게 본다.

    경력으로 세는 근무 기간(재직 · 인턴 · 프리랜서)은 시작 날짜와 (재직 중이 아니면) 끝 날짜가 모두 적혀 있어야 한다.
    학력 · 프로젝트 같은 그 밖의 기간은 경력으로 세지 않으므로 날짜 하나만 적혀 있어도 받는다 (예: 졸업 연월만 적힘).
    """
    text = " ".join(quote.sentence for quote in quotes)
    written = {
        (int(year), int(month))
        for year, month in re.findall(r"((?:19|20)\d{2})\s*(?:[.\-/]|년)\s*(\d{1,2})", text)
        if 1 <= int(month) <= 12
    }
    matched = [_year_month(value) in written for value in (period.start, period.end) if value]
    work = period.kind.strip().upper() in WORK_PERIOD_KINDS
    return all(matched) if work else any(matched)


def _year_month(value: str) -> tuple[int, int] | None:
    found = re.match(r"((?:19|20)\d{2})\D+(\d{1,2})", value)
    return (int(found.group(1)), int(found.group(2))) if found else None


def _mentions_education(text: str, quotes: Sequence[Quote]) -> bool:
    """블라인드 채용에서 빼는 내용인지. 글이나 근거 문장에 출신 학교나 학력 수준(학위 · 학점 등) 낱말이 나온다."""
    return any(education_term(part) for part in [text, *(quote.sentence for quote in quotes)])


async def summarize(
    llm: LlmClient, documents: Sequence[ApplicantDocument], *, blind: bool = False
) -> list[DocumentSection]:
    """자기소개서 문항별 요약만 묻는다. 서류 읽기(reading)가 추출과 함께 묻다가 출력 한도에서 잘리면 쓴다."""
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
        sections += letter_sections(document, result.sections, blind=blind)
    return sections


def letter_sections(
    document: ApplicantDocument, extracted: Sequence[ExtractedSection], *, blind: bool = False
) -> list[DocumentSection]:
    """모델이 쓴 문항 요약에서 근거 문장은 원문에서 찾은 것만 남긴다. 블라인드 채용(blind)이면 학력 · 출신 학교가
    나오는 요점과 근거 문장을 빼고, 제목이나 요약에 나오는 문항은 통째로 뺀다 (merge와 같은 기준)."""
    sections = []
    for section in extracted:
        if blind and education_term(f"{section.title} {section.summary}"):
            continue
        if section.title.strip() and section.summary.strip():
            points = [point.strip() for point in section.points if point.strip()]
            quotes = quotes_in([document], section.evidence)
            sections.append(
                DocumentSection(
                    document=document.type,
                    title=section.title.strip(),
                    summary=section.summary.strip(),
                    points=[point for point in points if not (blind and education_term(point))][:3],
                    quotes=[quote for quote in quotes if not (blind and education_term(quote.sentence))],
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
