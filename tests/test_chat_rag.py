"""Tests for ``app/chat_rag`` — pure-Python retrieval over bundled chunks."""

from __future__ import annotations

import math

import pytest

from app.chat_kb_data import CHUNKS, EMBEDDING_DIM
from app.chat_rag import TOP_K, Retrieval, retrieve


def _fake_vec(seed: int) -> tuple[float, ...]:
    """Return an L2-normalised 1536-dim vector with a known orientation."""
    raw = [0.0] * EMBEDDING_DIM
    raw[seed % EMBEDDING_DIM] = 1.0
    # Add a couple of orthogonal components so different seeds are unrelated.
    raw[(seed + 7) % EMBEDDING_DIM] = 0.5
    raw[(seed + 13) % EMBEDDING_DIM] = -0.3
    norm = math.sqrt(sum(x * x for x in raw))
    return tuple(x / norm for x in raw)


def _all_zero_vec() -> tuple[float, ...]:
    return (0.0,) * EMBEDDING_DIM


def test_bundled_chunks_have_full_dimension():
    assert CHUNKS, "chat_kb_data module must ship at least one chunk"
    for chunk in CHUNKS:
        assert len(chunk.vector) == EMBEDDING_DIM


def test_retrieve_returns_top_k_retrievals():
    question = _fake_vec(0)
    results = retrieve(question, k=TOP_K)
    assert len(results) == TOP_K
    assert all(isinstance(r, Retrieval) for r in results)


def test_retrieve_scores_are_finite_in_unit_interval():
    question = _fake_vec(42)
    results = retrieve(question, k=TOP_K)
    scores = [r.score for r in results]
    assert all(math.isfinite(s) for s in scores)
    assert all(-1.0 - 1e-6 <= s <= 1.0 + 1e-6 for s in scores)
    # The function is monotonic by construction; verify the contract.
    assert scores == sorted(scores, reverse=True)


def test_retrieve_rejects_wrong_dim_question():
    with pytest.raises(ValueError):
        retrieve((0.1, 0.2, 0.3))


def test_retrieve_handles_unrelated_question():
    # A vector with every component tiny still produces well-defined scores.
    question = tuple(1.0 / math.sqrt(EMBEDDING_DIM) for _ in range(EMBEDDING_DIM))
    results = retrieve(question, k=TOP_K)
    assert len(results) == TOP_K


def test_retrieve_returns_tuple_with_no_k_mutation():
    question = _fake_vec(7)
    a = retrieve(question, k=TOP_K)
    b = retrieve(question, k=TOP_K)
    assert a == b
    assert isinstance(a, tuple)


def test_retrieve_clamps_k_to_available_chunks(monkeypatch):
    # If k > len(CHUNKS), the caller still gets every chunk in ranked order.
    over_top = retrieve(_fake_vec(5), k=9999)
    assert len(over_top) == len(CHUNKS)


def test_retrieve_zero_k_returns_empty():
    assert retrieve(_fake_vec(3), k=0) == ()


@pytest.mark.parametrize("label_id", [c.label_id for c in CHUNKS])
def test_each_chunk_is_self_retrievable(label_id):
    """Pointing at a chunk's stored vector returns that chunk at rank 0."""
    target = next(c for c in CHUNKS if c.label_id == label_id)
    results = retrieve(target.vector, k=1)
    assert results and results[0].label_id == label_id
