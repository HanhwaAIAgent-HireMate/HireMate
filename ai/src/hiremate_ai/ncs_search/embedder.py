"""요청 문장의 BGE-M3 임베딩. 표의 묶음 벡터를 만든 모델과 같아야 검색이 맞는다."""

import importlib
from typing import Any, Literal, Protocol

from hiremate_ai.ncs_search.types import QueryVectors

Device = Literal["cpu", "mps", "cuda"]

MAX_TOKENS = 512
"""질의 하나의 최대 토큰. 서비스가 받는 글은 2,000자 이하라 넘지 않는다."""


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> list[QueryVectors]: ...


class BgeM3Embedder:
    """FlagEmbedding의 BGE-M3. 의존성 그룹 ncs를 설치해야 쓸 수 있다(uv run --group ncs).

    FlagEmbedding은 ai 서버 기본 의존성이 아니라 import_module로 부른다.
    """

    def __init__(self, model: str, device: Device) -> None:
        flag: Any = importlib.import_module("FlagEmbedding")
        self._model = flag.BGEM3FlagModel(model, devices=device, use_fp16=device == "cuda")

    def encode(self, texts: list[str]) -> list[QueryVectors]:
        result = self._model.encode(
            texts,
            batch_size=len(texts),
            max_length=MAX_TOKENS,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        return [
            QueryVectors(
                dense=[float(x) for x in dense],
                sparse={int(token): float(weight) for token, weight in weights.items() if float(weight) > 0},
            )
            for dense, weights in zip(result["dense_vecs"], result["lexical_weights"], strict=True)
        ]
