"""지원자 검색의 결과 형식. Root Agent의 찾기가 쓰고, 프로필 · 검색 담당의 검색 함수가 이 형식으로 돌려준다."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

from hiremate_ai.tools.scope import ToolScope


@dataclass(frozen=True)
class SourcedSentence:
    """조건과 맞닿은 원문 문장과 출처(이력서, 자기소개서, 평가 결과 등)."""

    sentence: str
    source: str
    anchor: str | None = None


@dataclass(frozen=True)
class CandidateMatch:
    """조건에 걸린 지원자. hits는 맞은 조건 수다."""

    application_id: UUID
    sentences: list[SourcedSentence]
    hits: int


class SearchResults(list[CandidateMatch]):
    def __init__(self, matches: Sequence[CandidateMatch] = (), *, warnings: Sequence[str] = ()) -> None:
        super().__init__(matches)
        self.warnings = list(warnings)


type CandidateSearch = Callable[[ToolScope, Sequence[str], Sequence[UUID]], Awaitable[list[CandidateMatch]]]
"""(조회 범위, 조건들, 후보 id) → 조건에 걸린 지원자. 후보 밖은 돌려주지 않고, 같은 입력에는 늘 같은 순서로 돌려준다.

넓게 모아도 된다. 정밀한 판정은 Root Agent가 재확인한다.
"""
