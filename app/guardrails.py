"""Guardrail layer for the chat endpoint.

Two complementary checks:

* ``is_in_scope`` — embedding similarity to a curated in-scope /
  out-of-scope example bank. Cheap (no LLM call), runs before the chat
  model is invoked. Returns a verdict plus a label so the SSE stream can
  carry enough information for the UI to render the right copy.
* ``contains_out_of_scope_terms`` — regex scan over each prospective
  completion chunk. Catches the model drifting out of scope after the LLM
  call is already in flight.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from app.chat_guardrail_data import IN_VECTORS, OUT_VECTORS
from app.embeddings import Embedder

MARGIN = 0.05


# Patterns intentionally match editorial phrasing, not isolated credit-domain
# vocabulary. "rate" or "card" are too broad; the goal is to catch advice
# phrased as investment / career / housing / tax recommendations.
OUT_OF_SCOPE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(invest|investment|investing|stocks?|mutual funds?|etf|index fund|portfolio rebalance)\b", re.IGNORECASE),
    re.compile(r"\b(career change|career switch|salary negotiation|which job|job offer|promotion)\b", re.IGNORECASE),
    re.compile(r"\b(rent vs buy|rent or buy|home loan emi|property purchase)\b", re.IGNORECASE),
    re.compile(r"\b(tax planning|tax savings?|section 80[cd]|hra exemption)\b", re.IGNORECASE),
    re.compile(r"\b(start (?:a|your own) business|business idea|entrepreneurship side hustle)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class ScopeVerdict:
    in_scope: bool
    reason: str  # 'in' | 'out' | 'ambiguous' | 'embed_error'


def _avg_cosine(query: Sequence[float], bank: Sequence[tuple[float, ...]]) -> float:
    """Average cosine similarity of ``query`` against a bank of vectors."""
    if not bank:
        return 0.0
    return sum(_dot(query, v) for v in bank) / len(bank)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


async def is_in_scope(
    question_vec: Sequence[float],
    *,
    embedder: Embedder | None = None,
) -> ScopeVerdict:
    """Return whether ``question_vec`` is closer to the in- or out-of-scope bank.

    The verdict defaults to ``in_scope=True`` when the score margin is below
    ``MARGIN`` so the model gets the benefit of the doubt on ambiguous
    phrasing.
    """
    try:
        in_avg = _avg_cosine(question_vec, IN_VECTORS)
        out_avg = _avg_cosine(question_vec, OUT_VECTORS)
    except Exception:  # noqa: BLE001
        return ScopeVerdict(in_scope=True, reason="embed_error")

    diff = in_avg - out_avg
    if diff > MARGIN:
        return ScopeVerdict(in_scope=True, reason="in")
    if -diff > MARGIN:
        return ScopeVerdict(in_scope=False, reason="out")
    return ScopeVerdict(in_scope=True, reason="ambiguous")


def contains_out_of_scope_terms(answer: str) -> bool:
    """True if the supplied text contains out-of-scope advice markers."""
    if not answer:
        return False
    text = answer.lower()
    return any(pattern.search(text) for pattern in OUT_OF_SCOPE_PATTERNS)


__all__ = [
    "MARGIN",
    "OUT_OF_SCOPE_PATTERNS",
    "ScopeVerdict",
    "is_in_scope",
    "contains_out_of_scope_terms",
]
