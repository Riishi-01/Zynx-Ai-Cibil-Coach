"""Tests for ``app/embeddings`` — normalize + dimension + mock-friendly SDK."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Sequence

import pytest

from app.embeddings import EMBEDDING_DIM, Embedder
from app.schemas import LLMError


class _FakeRecord:
    def __init__(self, embedding):
        self.embedding = embedding


class _FakeEmbeddingsResponse:
    def __init__(self, data):
        self.data = data


class _FakeEmbeddingsAPI:
    def __init__(self, vectors):
        self._vectors = vectors
        self.calls = []

    async def create(self, *, model, input):
        self.calls.append((model, list(input)))
        return _FakeEmbeddingsResponse(
            [_FakeRecord(list(v)) for v in self._vectors]
        )


def _random_unit(seed: int) -> list[float]:
    raw = [0.0] * EMBEDDING_DIM
    for i in range(EMBEDDING_DIM):
        raw[i] = ((seed + i * 7) % 17) - 8
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def test_embed_normalizes_to_unit_length():
    fake = _FakeEmbeddingsAPI([_random_unit(11)])
    client = SimpleNamespace(embeddings=fake)
    embedder = Embedder(client=client)

    import asyncio

    vec = asyncio.run(embedder.embed("hello"))

    assert len(vec) == EMBEDDING_DIM
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-3


def test_embed_returns_tuple_with_4_decimals_precision():
    fake = _FakeEmbeddingsAPI([_random_unit(23)])
    embedder = Embedder(client=SimpleNamespace(embeddings=fake))

    import asyncio

    vec = asyncio.run(embedder.embed("hello"))

    for value in vec:
        # Round-trip through str with 4 decimals and back; values must agree.
        assert round(value, 4) == value


def test_embed_rejects_empty_text():
    fake = _FakeEmbeddingsAPI([])
    embedder = Embedder(client=SimpleNamespace(embeddings=fake))

    import asyncio

    with pytest.raises(ValueError):
        asyncio.run(embedder.embed("   "))


def test_embed_batch_returns_one_vector_per_input():
    fake = _FakeEmbeddingsAPI(
        [_random_unit(i) for i in range(5)]
    )
    embedder = Embedder(client=SimpleNamespace(embeddings=fake))

    import asyncio

    vectors = asyncio.run(
        embedder.embed_batch(["a", "b", "c", "d", "e"])
    )
    assert len(vectors) == 5
    assert all(len(v) == EMBEDDING_DIM for v in vectors)


def test_embed_batch_chunks_large_inputs():
    inputs = [f"q{i}" for i in range(4096)]
    responses: list[list[list[float]]] = []

    class _ChunkedAPI:
        def __init__(self):
            self.calls = []

        async def create(self, *, model, input):
            self.calls.append(list(input))
            vectors = [_random_unit(i) for i in range(len(input))]
            responses.append(vectors)
            return _FakeEmbeddingsResponse([_FakeRecord(v) for v in vectors])

    api = _ChunkedAPI()
    embedder = Embedder(client=SimpleNamespace(embeddings=api))

    import asyncio

    vectors = asyncio.run(embedder.embed_batch(inputs))

    assert len(api.calls) == 2  # 4096 -> 2048 + 2048
    assert len(vectors) == 4096


def test_embed_rejects_unsupported_model():
    with pytest.raises(ValueError):
        Embedder(model="text-embedding-3-large")


def test_embed_translates_sdk_errors_into_llmerror():
    class _BoomAPI:
        async def create(self, *, model, input):
            raise RuntimeError("network down")

    embedder = Embedder(client=SimpleNamespace(embeddings=_BoomAPI()))
    import asyncio

    with pytest.raises(LLMError):
        asyncio.run(embedder.embed("anything"))


def test_default_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app import embeddings as module

    with pytest.raises(LLMError):
        module._get_client()
