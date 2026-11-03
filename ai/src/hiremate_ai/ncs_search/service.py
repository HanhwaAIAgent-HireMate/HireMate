"""질의 임베딩 서비스. ai 서버가 NCS를 찾기 전에 요청 문장의 벡터를 받는다. 내부망에만 연다."""

from typing import Annotated

from fastapi import FastAPI
from pydantic import BaseModel, Field, StringConstraints

from hiremate_ai.ncs_search.embedder import Embedder
from hiremate_ai.ncs_search.types import QueryVectors

MAX_CHARS = 2000
"""글 하나의 최대 글자 수. 공고 수정 요청과 바꾼 업무 문장을 넉넉히 담는다."""


class EmbedRequest(BaseModel):
    texts: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CHARS)]] = Field(
        min_length=1, max_length=4
    )


class EmbedResponse(BaseModel):
    vectors: list[QueryVectors]


def create_app(embedder: Embedder) -> FastAPI:
    app = FastAPI(title="HireMate NCS 임베딩")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # 모델 계산이 이벤트 루프를 막지 않게 스레드 풀에서 돈다(def 엔드포인트)
    @app.post("/embed")
    def embed(body: EmbedRequest) -> EmbedResponse:
        return EmbedResponse(vectors=embedder.encode(body.texts))

    return app
