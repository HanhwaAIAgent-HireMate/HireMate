"""Agent가 쓰는 NCS 참고 조회. 질의 임베딩은 서비스에 맡기고 검색은 ai DB에서 한다."""

from functools import cache
from typing import Annotated, Protocol

import httpx
from fastapi import Depends
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.config import settings
from hiremate_ai.db.session import session_factory
from hiremate_ai.ncs_search.search import search_tasks
from hiremate_ai.ncs_search.store import load_units
from hiremate_ai.ncs_search.types import NcsTask, NcsUnit, QueryVectors


class NcsUnavailable(Exception):
    """임베딩 서비스에 닿지 못했거나 서비스가 요청을 거절했다. 부르는 쪽은 NCS 없이 진행한다."""


class _Vectors(BaseModel):
    vectors: list[QueryVectors]


class EmbedClient:
    """질의 임베딩 서비스(hiremate_ai.ncs_search)의 클라이언트."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/embed"

    async def embed(self, texts: list[str]) -> list[QueryVectors]:
        try:
            response = await self._http.post(self._url, json={"texts": texts})
            response.raise_for_status()
            vectors = _Vectors.model_validate_json(response.content).vectors
        except (httpx.HTTPError, ValidationError) as error:
            raise NcsUnavailable(type(error).__name__) from error
        if len(vectors) != len(texts):
            raise NcsUnavailable("벡터 수가 글 수와 다릅니다.")
        return vectors


class NcsReference(Protocol):
    async def units(self) -> list[NcsUnit]:
        """모델이 고를 능력단위 목록. 표가 비어 있으면 빈 목록이다."""
        ...

    async def search(self, request: str, tasks: list[str], units: list[str]) -> list[NcsTask]:
        """원문 요청, NCS식 업무 문장, 고른 능력단위로 찾은 묶음. 임베딩 실패는 NcsUnavailable이다."""
        ...


class DbNcsReference:
    """ai DB의 NCS 표와 임베딩 서비스로 찾는다. 표는 적재할 때만 바뀌어 능력단위 목록을 기억해 둔다."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], embed: EmbedClient) -> None:
        self._sessions = sessions
        self._embed = embed
        self._units: list[NcsUnit] = []

    async def units(self) -> list[NcsUnit]:
        if not self._units:
            async with self._sessions() as session:
                self._units = await load_units(session)
        return self._units

    async def search(self, request: str, tasks: list[str], units: list[str]) -> list[NcsTask]:
        original, converted = await self._embed.embed([request, " ".join(tasks) or request])
        async with self._sessions() as session:
            return await search_tasks(session, original, converted, units)


@cache
def get_ncs() -> NcsReference:
    """FastAPI 의존성. 프로세스에 하나만 만든다. 테스트는 app.dependency_overrides[get_ncs]로 바꾼다."""
    http = httpx.AsyncClient(timeout=settings.ncs_embed_timeout_seconds)
    return DbNcsReference(session_factory(), EmbedClient(http, settings.ncs_embed_url))


NcsDep = Annotated[NcsReference, Depends(get_ncs)]
