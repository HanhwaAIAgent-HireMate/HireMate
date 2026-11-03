from fastapi.testclient import TestClient

from hiremate_ai.ncs_search.service import create_app
from hiremate_ai.ncs_search.types import DENSE_DIM, QueryVectors


class FakeEmbedder:
    """글자 수를 dense 첫 칸에 넣는 가짜. 받은 글을 기록한다."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts: list[str]) -> list[QueryVectors]:
        self.calls.append(texts)
        return [QueryVectors(dense=[float(len(t))] + [0.0] * (DENSE_DIM - 1), sparse={len(t): 1.0}) for t in texts]


def client(embedder: FakeEmbedder) -> TestClient:
    return TestClient(create_app(embedder))


def test_embed_returns_vector_per_text() -> None:
    embedder = FakeEmbedder()

    response = client(embedder).post("/embed", json={"texts": ["주문 API를 개발한다", "가"]})

    assert response.status_code == 200
    vectors = [QueryVectors.model_validate(v) for v in response.json()["vectors"]]
    assert [v.dense[0] for v in vectors] == [12.0, 1.0]
    assert vectors[1].sparse == {1: 1.0}
    assert embedder.calls == [["주문 API를 개발한다", "가"]]


def test_embed_rejects_empty_text() -> None:
    embedder = FakeEmbedder()

    assert client(embedder).post("/embed", json={"texts": [" "]}).status_code == 422
    assert embedder.calls == []


def test_embed_rejects_too_long_text() -> None:
    assert client(FakeEmbedder()).post("/embed", json={"texts": ["가" * 2001]}).status_code == 422


def test_embed_rejects_too_many_texts() -> None:
    assert client(FakeEmbedder()).post("/embed", json={"texts": ["가"] * 5}).status_code == 422


def test_health() -> None:
    assert client(FakeEmbedder()).get("/health").json() == {"status": "ok"}
