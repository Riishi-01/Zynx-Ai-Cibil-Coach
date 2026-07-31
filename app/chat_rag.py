"""In-memory retrieval over the bundled chat RAG chunks.

Pure-Python: takes an L2-normalized question vector and returns the top-K
chunks by cosine similarity (= dot product on normalized vectors). No I/O,
no allocations beyond the returned tuple.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from app.chat_kb_data import CHUNKS, EMBEDDING_DIM, EMBEDDING_MODEL

TOP_K = 5


@dataclass(frozen=True)
class Retrieval:
    """One retrieved knowledge-base chunk with its cosine score."""

    label_id: str
    text: str
    score: float


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _validate_question_vec(question_vec: Sequence[float]) -> None:
    if len(question_vec) != EMBEDDING_DIM:
        raise ValueError(
            f"question_vec has dimension {len(question_vec)}, expected {EMBEDDING_DIM}"
        )


def retrieve(question_vec: Sequence[float], k: int = TOP_K) -> tuple[Retrieval, ...]:
    """Return the ``k`` most similar chunks, ordered by descending score."""
    _validate_question_vec(question_vec)

    if k <= 0:
        return ()

    effective_k = min(k, len(CHUNKS))
    scored = (
        (_dot(question_vec, c.vector), c) for c in CHUNKS
    )
    top = sorted(scored, key=lambda pair: pair[0], reverse=True)[:effective_k]

    return tuple(
        Retrieval(label_id=c.label_id, text=c.text, score=score)
        for score, c in top
    )


__all__ = [
    "Retrieval",
    "TOP_K",
    "retrieve",
    "EMBEDDING_DIM",
    "EMBEDDING_MODEL",
]


def _module_metadata() -> tuple[str, int]:
    return EMBEDDING_MODEL, EMBEDDING_DIM


# Defensive: cosines of properly-normalized vectors stay in [-1, 1]. The bound
# below guards against unnormalized inputs creeping in via future refactors.
_SCORE_FLOOR = -1.0 - 1e-6
_SCORE_CEIL = 1.0 + 1e-6
assert math.isfinite(_SCORE_FLOOR) and math.isfinite(_SCORE_CEIL)
