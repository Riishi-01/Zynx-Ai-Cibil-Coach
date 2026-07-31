"""Lazily-instantiated OpenAI embeddings client.

The module imports ``openai`` on first call so test suites can monkeypatch
``app.embeddings._get_client`` without paying the SDK cost. All vectors are
returned L2-normalized and rounded to four decimal places — matching the
build-time quantization in ``app/chat_kb_data``.

The class only exposes ``embed`` (single string) and ``embed_batch`` (list of
strings). The runtime path uses ``embed``; ``embed_batch`` is only consumed
by ``scripts/build_chat_kb.py`` at build time.
"""

from __future__ import annotations

import math
import os
from typing import Optional

from app.chat_kb_data import EMBEDDING_DIM
from app.schemas import LLMError


def _get_client():
    """Lazily construct the AsyncOpenAI client.

    Mirrors the pattern in ``app.llm_stream._get_client`` so importing this
    module never requires ``OPENAI_API_KEY`` to be set.
    """
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("OPENAI_API_KEY not set in environment")
    return AsyncOpenAI(api_key=api_key)


def _normalize(vec: list[float]) -> tuple[float, ...]:
    """L2-normalize a list of floats, rounding to 4 decimals.

    Empty / zero vectors are returned as ``None`` rather than NaN — callers
    surface those explicitly.
    """
    if not vec:
        raise ValueError("vector is empty")
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0 or not math.isfinite(norm):
        raise ValueError("vector has zero or non-finite norm; cannot normalize")
    rounded = [round(x / norm, 4) for x in vec]
    # Round-trip through tuple; re-validate length.
    if len(rounded) != EMBEDDING_DIM:
        raise ValueError(
            f"embedding dimension mismatch: got {len(rounded)}, expected {EMBEDDING_DIM}"
        )
    # Re-normalize after rounding so quantization drift is corrected.
    post_norm = math.sqrt(sum(x * x for x in rounded))
    if post_norm == 0.0:
        raise ValueError("vector collapsed to zero after rounding")
    scale = 1.0 / post_norm
    return tuple(round(x * scale, 4) for x in rounded)


class Embedder:
    """Thin wrapper around the OpenAI embeddings endpoint.

    The ``model`` argument is fixed to ``text-embedding-3-small`` at runtime
    so the bundled ``chat_kb_data`` vectors stay dimensionally compatible
    with query embeddings produced by this class.
    """

    MODEL = "text-embedding-3-small"

    def __init__(self, model: str = MODEL, *, client=None) -> None:
        if model != self.MODEL:
            raise ValueError(
                f"only {self.MODEL} is supported (asked for {model!r}); the chat "
                "RAG index is pre-built for this model's 1536-dim output."
            )
        self._model = model
        self._client = client  # injection point for tests

    @property
    def model(self) -> str:
        return self._model

    async def embed(self, text: str) -> tuple[float, ...]:
        """Embed a single string. Returns an L2-normalized 1536-dim tuple."""
        if not text or not text.strip():
            raise ValueError("cannot embed empty text")
        response = await self._call([text])
        return _normalize(response[0])

    async def embed_batch(self, texts: list[str]) -> list[tuple[float, ...]]:
        """Embed a list of strings. Caps at OpenAI's 2048-input batch limit."""
        if not texts:
            return []
        if any(not t or not t.strip() for t in texts):
            raise ValueError("embed_batch refuses empty strings")

        results: list[tuple[float, ...]] = []
        for start in range(0, len(texts), 2048):
            chunk = texts[start : start + 2048]
            response = await self._call(chunk)
            results.extend(_normalize(v) for v in response)
        return results

    async def _call(self, inputs: list[str]) -> list[list[float]]:
        client = self._client or _get_client()
        try:
            response = await client.embeddings.create(
                model=self._model,
                input=inputs,
            )
        except Exception as exc:  # noqa: BLE001 — turn SDK errors into LLMError
            raise LLMError(f"embedding call failed: {exc}") from exc
        return [record.embedding for record in response.data]


__all__ = ["Embedder", "EMBEDDING_DIM"]


# Re-export so callers can ``from app.embeddings import EMBEDDING_DIM`` if
# they don't already import it from chat_kb_data.
_EMBEDDING_DIM: int = EMBEDDING_DIM


def expected_dim() -> int:
    return _EMBEDDING_DIM


def _check_env() -> Optional[str]:
    """Helper for the build script — returns the env var or a short error."""
    return os.getenv("OPENAI_API_KEY")
