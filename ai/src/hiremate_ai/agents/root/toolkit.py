"""Root Agent가 쓰는 도구 묶음. 프로필 · 검색 도구가 들어오기 전까지는 ChatContext 문서로 동작하는 임시 구현을 쓴다."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from langchain_core.tools import BaseTool

from hiremate_ai.agents.root.types import ChatContext
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch, SourcedSentence
from hiremate_ai.tools.scope import ToolScope


@dataclass(frozen=True)
class RootToolContext(ToolScope):
    """Root의 도구가 받는 범위. 임시 도구는 chat을 읽고, 다른 역할의 도구는 ToolScope 필드만 읽는다.

    called에는 도구 루프에서 부른 도구 이름이 쌓인다. 답의 agents를 채울 때 쓴다.
    """

    chat: ChatContext
    called: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RootToolkit:
    search: CandidateSearch
    answer_tools: Sequence[BaseTool] = ()


def scope_of(context: ChatContext) -> RootToolContext:
    return RootToolContext(
        company_id=context.company.company_id,
        recruitment_id=context.recruitment_id,
        stage_id=context.stage_id,
        application_ids=frozenset(row.application_id for row in context.candidates),
        chat=context,
    )


_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z+#.]+")
_PARTICLE = re.compile(r"(이|가|을|를|은|는|도|만|의|과|와|에서|에|로|으로|이랑|랑)$")
_SENTENCE = re.compile(r"\n+|(?<=[.!?])\s+")
_STOP_WORDS = {
    "찾아줘",
    "찾아",
    "보여줘",
    "보여",
    "골라줘",
    "지원자",
    "사람",
    "그중",
    "중에서",
    "추가해줘",
    "추가",
    "해줘",
    "경험",
    "있는",
    "있어",
    "있나",
    "드러나는",
    "관련",
    "가진",
    "구체적으로",
    "적힌",
    "현재",
    "결과",
    "좋은",
    "지금",
    "우리",
    "회사",
    "중요하게",
    "보는",
    "요소",
    "도메인",
    "프로젝트",
    "지원서",
    "내용",
    "가장",
    "모두",
    "전체",
    "선택",
    "처리",
    "능력",
    "역량",
    "강조한",
    "강조",
    "해본",
    "해",
    "본",
}
_SYNONYMS = {
    "금융": [
        "금융",
        "은행",
        "카드",
        "페이",
        "증권",
        "보험",
        "결제",
        "정산",
        "뱅킹",
        "pg",
        "finance",
        "bank",
        "payment",
    ],
    "결제": ["결제", "정산", "payment", "settlement"],
    "대용량": ["대용량", "트래픽", "트랜잭션", "traffic", "transaction"],
    "협업": ["협업", "협력", "소통", "함께", "회고", "collaboration", "teamwork"],
    "리더": ["리더", "리드", "주도", "lead"],
}


def concept_terms(concept: str) -> list[str]:
    """조건 하나를 찾을 낱말들. 조사와 흔한 말을 빼고 같은 뜻의 낱말로 넓힌다."""
    terms: list[str] = []
    for match in _WORD.finditer(concept):
        word = _PARTICLE.sub("", match.group()).lower()
        if len(word) < 2 or word in _STOP_WORDS:
            continue
        terms += [term for term in _SYNONYMS.get(word, [word]) if term not in terms]
    return terms


async def keyword_search(scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
    """임시 검색: 제출 문서에서 조건 낱말이 든 문장을 조건마다 하나씩 찾는다. 넓게 모으고 판정은 재확인에 맡긴다."""
    if not isinstance(scope, RootToolContext):
        raise TypeError("keyword_search는 ChatContext가 든 RootToolContext로만 부른다")
    term_sets = [terms for terms in (concept_terms(concept) for concept in concepts) if terms]
    matches = []
    for application_id in pool:
        if application_id not in scope.application_ids:
            continue
        sentences = _sentences(scope.chat, application_id)
        found = []
        for terms in term_sets:
            hit = next(
                (sourced for sourced in sentences if any(term in sourced.sentence.lower() for term in terms)), None
            )
            if hit is not None:
                found.append(hit)
        if found:
            matches.append(CandidateMatch(application_id=application_id, sentences=found, hits=len(found)))
    return sorted(matches, key=lambda match: -match.hits)


def default_toolkit() -> RootToolkit:
    return RootToolkit(search=keyword_search)


def _sentences(context: ChatContext, application_id: UUID) -> list[SourcedSentence]:
    sentences = []
    for document in context.documents.get(application_id, []):
        for line in _SENTENCE.split(document.text):
            text = line.strip().lstrip("-• ").strip()
            if len(text) >= 4:
                sentences.append(SourcedSentence(sentence=text, source=document.type.label))
    return sentences
