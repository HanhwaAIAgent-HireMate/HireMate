"""판정에 넣을 근거 모으기 (Assessment 부분의 첫 단계). 코드만 쓴다.

서류가 짧으면 원문 전체를, 길면 조건과 맞닿은 문장만 넣는다. Application 부분이 뽑은 사실도 함께 넣는다.
재확인할 때는 아직 근거로 쓰지 않은 문장 가운데 평가 조건과 맞닿은 것을 다시 찾는다.
"""

import re
from collections.abc import Iterable, Sequence

from hiremate_ai.agents.analysis.application.types import Fact, Period, Quote
from hiremate_ai.contract import ApplicantDocument
from hiremate_ai.llm.prompt import data_block, documents_block

_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9+#./-]+")
_SENTENCE = re.compile(r"\n+|(?<=[.!?])\s+")
_PARTICLE = re.compile(r"(을|를|이|가|은|는|의|와|과|로|으로|에서|에|도|및)$")
_STOP_WORDS = {
    "있다",
    "있는",
    "있으신",
    "경험",
    "개발하고자",
    "하는",
    "위한",
    "위해",
    "위하여",
    "관련된",
    "대한",
    "대해",
    "따라",
    "필요한",
    "이상",
    "활용하여",
    "응용소프트웨어",
    "응용소프트웨어와",
    "응용소프트웨어의",
    "수행",
}


def readable(documents: Sequence[ApplicantDocument]) -> list[ApplicantDocument]:
    """글자를 읽은 문서만."""
    return [document for document in documents if document.text.strip()]


def terms(texts: Iterable[str]) -> list[str]:
    """조건 문장의 검색어. 두 글자 이상 한글 낱말과 영문 낱말에서 조사를 떼고 흔한 말은 뺀다."""
    found: list[str] = []
    for text in texts:
        for word in _WORD.findall(text):
            word = _PARTICLE.sub("", word) if re.match(r"[가-힣]", word) else word.lower()
            if len(word) >= 2 and word not in _STOP_WORDS and word not in found:
                found.append(word)
    return found


def sentences(documents: Sequence[ApplicantDocument]) -> list[Quote]:
    found: list[Quote] = []
    for document in documents:
        for line in _SENTENCE.split(document.text):
            line = line.strip().lstrip("·•-* ").strip()
            if len(line) >= 6:
                found.append(Quote(document=document.type, sentence=line))
    return found


def related(documents: Sequence[ApplicantDocument], words: Sequence[str], exclude: Iterable[str] = ()) -> list[Quote]:
    """검색어가 두 개 이상(검색어가 하나면 하나) 들어 있는 문장. 이미 근거로 쓴 문장은 뺀다."""
    skip = {_compact(sentence) for sentence in exclude}
    need = 1 if len(words) <= 1 else 2
    found = []
    for quote in sentences(documents):
        lower = quote.sentence.lower()
        if _compact(quote.sentence) not in skip and sum(word in lower for word in words) >= need:
            found.append(quote)
    return found


def evidence_text(
    documents: Sequence[ApplicantDocument], facts: Sequence[Fact], words: Sequence[str], full_text_chars: int
) -> str:
    """판정 프롬프트에 넣을 근거. 모두 자료 블록으로 감싼다 (아키텍처 규칙 5)."""
    usable = readable(documents)
    parts = []
    if sum(len(document.text) for document in usable) <= full_text_chars:
        parts.append(documents_block(usable))
    else:
        lines = "\n".join(f"[{quote.document.label}] {quote.sentence}" for quote in related(usable, words))
        parts.append(data_block("sentences", lines or "(조건과 맞닿은 문장이 없음)"))
    if facts:
        parts.append(data_block("facts", fact_lines(facts)))
    return "\n\n".join(parts)


def fact_lines(facts: Sequence[Fact]) -> str:
    return "\n".join(
        f"- [{fact.kind} · {fact.actor.value}] {fact.statement} (근거: {fact.quotes[0].sentence})" for fact in facts
    )


def career_table(periods: Sequence[Period]) -> str:
    """경력표. 개월 수는 코드가 계산한 값이다."""
    if not periods:
        return "(서류에서 찾은 근무 기간이 없음)"
    return "\n".join(
        f"- {period.company} · {period.role or '역할 미기재'} · {period.kind} · {period.start} ~ {period.end or '현재'}"
        f" · {period.months}개월"
        for period in periods
    )


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)
