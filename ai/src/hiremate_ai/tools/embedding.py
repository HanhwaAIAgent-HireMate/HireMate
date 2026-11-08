"""내부 임베딩 서비스의 밀집 벡터 클라이언트."""

import math
from functools import cache
from typing import Protocol

import httpx

from hiremate_ai.config import settings
from hiremate_ai.ncs_search.reference import EmbedClient


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class DenseEmbedder:
    def __init__(self, client: EmbedClient) -> None:
        self._client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.dense for vector in await self._client.embed(texts)]


@cache
def get_embedder() -> Embedder:
    http = httpx.AsyncClient(timeout=settings.ncs_embed_timeout_seconds)
    return DenseEmbedder(EmbedClient(http, settings.ncs_embed_url))


def valid_vector(vector: list[float]) -> bool:
    return len(vector) == 1024 and all(math.isfinite(value) for value in vector) and any(vector)
