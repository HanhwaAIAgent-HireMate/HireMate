"""지원자 프로필 검색 (FR-13, 14). Root Agent의 A 지원자 찾기가 쓰는 검색 함수.

tools.candidates.CandidateSearch 모양을 따른다. (조회 범위, 조건들, 후보 id) → 조건에 걸린 지원자.
- 프로필 항목(내용, 근거 문장)에서 조건 낱말을 찾는다. 원문 전체를 다시 읽지 않는다.
- 확인 필요(CHECK) 항목은 근거로 쓰지 않는다. "결제 도메인은 처음"이 금융 경험으로 잡히지 않게 하기 위해서다.
- 현재 기업 · 채용 · 전형 범위 안의 후보만 본다 (아키텍처 규칙 4).
- 같은 입력에는 늘 같은 순서로 돌려준다: 맞은 조건 수가 많은 순, 같으면 후보 id를 받은 순서.
- 넓게 모으고, 조건을 정말 충족하는지는 Root Agent가 재확인한다.

서류 점수 · 평가 점수 같은 숫자 조건은 Root가 backend 값(ChatContext)으로 거른 뒤 후보 id로 넘긴다.

Root에 연결하는 예
    search = profile_search(session_factory(), terms=concept_terms)
    toolkit = RootToolkit(search=search, ...)
"""

import re
from collections.abc import Callable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.contract import DocumentType
from hiremate_ai.db.profile import CandidateProfile, ItemCategory, ProfileItem
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch, SourcedSentence
from hiremate_ai.tools.scope import ToolScope

# 조건 하나에 모으는 근거 문장 수. Root의 재확인이 이 가운데 근거를 고른다
SENTENCES_PER_CONCEPT = 3

type TermsOf = Callable[[str], list[str]]
"""조건 하나("금융 도메인 경험")를 찾을 낱말들(["금융"])로 바꾸는 함수."""

_DOCUMENT_LABELS = {document.label for document in DocumentType}
_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z+#.]+")
_PARTICLE = re.compile(r"(이|가|을|를|은|는|도|만|의|과|와|에서|에|로|으로|이랑|랑)$")
# 조건을 말할 때 흔히 붙지만 지원자를 가르지 못하는 말
_STOP_WORDS = {
    "찾아줘",
    "찾아",
    "보여줘",
    "지원자",
    "사람",
    "경험",
    "경험자",
    "있는",
    "관련",
    "도메인",
    "처리",
    "능력",
    "역량",
    "프로젝트",
}


def simple_terms(concept: str) -> list[str]:
    """기본 낱말 나누기. 조사와 흔한 말을 뺀다. Root는 동의어까지 넓히는 자기 함수(concept_terms)를 넘길 수 있다."""
    terms: list[str] = []
    for match in _WORD.finditer(concept):
        word = _PARTICLE.sub("", match.group()).lower()
        if len(word) >= 2 and word not in _STOP_WORDS and word not in terms:
            terms.append(word)
    return terms


async def search_profiles(
    session: AsyncSession,
    scope: ToolScope,
    concepts: Sequence[str],
    pool: Sequence[UUID],
    *,
    terms: TermsOf = simple_terms,
) -> list[CandidateMatch]:
    """프로필에서 조건에 걸린 후보를 찾는다. pool 밖이나 조회 범위 밖의 지원자는 돌려주지 않는다."""
    # 차별 조건은 검색 낱말로 쓰지 않는다 (규칙 6). 요청 차단은 Root가 먼저 한다
    term_sets = [found for found in (terms(concept) for concept in concepts if not blocked_attribute(concept)) if found]
    order = [application_id for application_id in dict.fromkeys(pool) if application_id in scope.application_ids]
    if not term_sets or not order:
        return []

    profiles = await session.scalars(
        select(CandidateProfile).where(
            CandidateProfile.company_id == scope.company_id,
            CandidateProfile.recruitment_id == scope.recruitment_id,
            CandidateProfile.application_id.in_(order),
        )
    )
    by_id = {profile.application_id: profile for profile in profiles}

    matches = []
    for application_id in order:
        profile = by_id.get(application_id)
        if profile is None:
            continue  # 아직 분석 전이라 프로필이 없다
        # 한 번에 저장한 항목은 저장 시각이 같으므로 id로 순서를 고정해 늘 같은 문장 순서가 나오게 한다
        items = sorted((item for item in profile.items if _usable(item)), key=lambda item: (item.created_at, item.id))
        sentences: list[SourcedSentence] = []
        hits = 0
        for term_set in term_sets:
            found = _best(items, term_set)
            hits += bool(found)
            sentences += [sentence for sentence in found if sentence not in sentences]
        if hits:
            matches.append(CandidateMatch(application_id=application_id, sentences=sentences, hits=hits))
    # sorted는 같은 값의 순서를 지키므로 맞은 조건 수가 같으면 후보 순서 그대로다
    return sorted(matches, key=lambda match: -match.hits)


def profile_search(sessions: async_sessionmaker[AsyncSession], *, terms: TermsOf = simple_terms) -> CandidateSearch:
    """Root의 RootToolkit.search에 넣을 검색 함수를 만든다. 부를 때마다 세션을 열고 닫는다."""

    async def search(scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        async with sessions() as session:
            return await search_profiles(session, scope, concepts, pool, terms=terms)

    return search


def _usable(item: ProfileItem) -> bool:
    """검색 근거로 쓸 수 있는 항목. 확인 필요 항목과, 문서 출처인데 근거 문장이 없는 항목은 뺀다.

    Root의 재확인은 문서 출처 문장이 원문에 있는지 다시 보므로, 문서 출처 항목은 원문 근거 문장을 돌려줘야 한다.
    """
    if item.category == ItemCategory.CHECK:
        return False
    return item.evidence is not None or item.source not in _DOCUMENT_LABELS


def _best(items: list[ProfileItem], term_set: list[str]) -> list[SourcedSentence]:
    """조건 낱말이 많이 든 항목 순으로 근거 문장 몇 개. 같으면 저장된 순서."""
    scored = []
    for index, item in enumerate(items):
        text = f"{item.content} {item.evidence or ''}".lower()
        count = sum(term in text for term in term_set)
        if count:
            scored.append((-count, index, item))
    return [
        SourcedSentence(sentence=item.evidence or item.content, source=item.source)
        for _, _, item in sorted(scored, key=lambda scored_item: scored_item[:2])[:SENTENCES_PER_CONCEPT]
    ]
