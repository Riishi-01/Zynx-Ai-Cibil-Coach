"""Guardrail layer for the chat endpoint.

Two complementary checks:

* ``is_in_scope`` — embedding similarity to a curated in-scope /
  out-of-scope example bank. Cheap (no LLM call), runs before the chat
  model is invoked. Returns a verdict plus a label so the SSE stream can
  carry enough information for the UI to render the right copy.
* ``contains_out_of_scope_terms`` — regex scan over each prospective
  completion chunk. Catches the model drifting out of scope after the LLM
  call is already in flight.

The class-based API (``ScopeGuard``, ``HardRulesChecker``, ``NumberVerifier``,
``check_response``) wraps the same primitives and adds post-LLM checks for
hard rule violations and untraced numbers. The module-level functions stay
for backwards compatibility — eval scripts and existing tests still import
them directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

from app.chat_guardrail_data import IN_VECTORS, OUT_VECTORS
from app.embeddings import Embedder
from app.schemas import FactSet, SanitisedRecord

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


# Heuristic OOS patterns — a small subset that lets ScopeGuard fast-reject
# obvious hits without paying for an embedding call. Anything that doesn't
# match here falls through to the embedding layer.
_OOS_HEURISTIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\binvest\b", re.IGNORECASE),
    re.compile(r"\bcareer (?:change|switch)\b", re.IGNORECASE),
    re.compile(r"\brent vs buy\b", re.IGNORECASE),
    re.compile(r"\bsection 80[cd]\b", re.IGNORECASE),
    re.compile(r"\bstart (?:a|your own) business\b", re.IGNORECASE),
)


# Hard rule patterns — banned recommendations that the prompt asks the model
# to avoid. Each key is a stable identifier used by HardRulesChecker.check().
HARD_RULE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "cash_advance": (
        re.compile(r"\bcash advance\b", re.IGNORECASE),
        re.compile(r"\bcash withdrawal from (?:a )?(?:credit )?card\b", re.IGNORECASE),
    ),
    "close_oldest_card": (
        re.compile(r"\bclose (?:your|the) oldest (?:credit )?card\b", re.IGNORECASE),
        re.compile(r"\bclosing (?:your|the) oldest (?:credit )?card\b", re.IGNORECASE),
    ),
    "pay_past_sol_collection": (
        re.compile(r"\bpay (?:the )?collection past\b", re.IGNORECASE),
    ),
    "pay_overdue_first": (
        re.compile(r"\bpay(?:ing)? down a card that is 30\+ days overdue\b", re.IGNORECASE),
    ),
    "consolidation_loan": (
        re.compile(r"\b(?:consolidation loan|payday loan)\b", re.IGNORECASE),
    ),
    "balance_transfer": (
        re.compile(r"\bbalance[- ]transfer card\b", re.IGNORECASE),
    ),
}


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


# ============================================================================
# Class-based guardrail API
# ============================================================================


class ScopeGuard:
    """Pre-LLM scope check — heuristic fast-reject then embedding similarity.

    The embedding cache lives on the embedder (passed in via ``__init__`` or
    built lazily on first use). When a ``question_vec`` is supplied to
    ``check()`` the embedder is bypassed entirely so the chat endpoint can
    reuse the vector it already produced for retrieval.
    """

    def __init__(self, embedder: Optional[Embedder] = None) -> None:
        self._embedder = embedder

    async def check(
        self,
        text: str,
        *,
        question_vec: Optional[Sequence[float]] = None,
    ) -> tuple[bool, str, float]:
        """Return (in_scope, reason, confidence).

        Reasons: 'heuristic' | 'in' | 'out' | 'ambiguous' | 'embed_error' |
        'no_embedder'. Confidence is ``|in_avg - out_avg|`` on the embedding
        layer, ``1.0`` on heuristic fast-reject, ``0.0`` on embed failure.
        """
        for pattern in _OOS_HEURISTIC_PATTERNS:
            if pattern.search(text or ""):
                return (False, "heuristic", 1.0)

        if question_vec is None:
            if self._embedder is None:
                return (True, "no_embedder", 0.0)
            try:
                question_vec = await self._embedder.embed(text)
            except Exception:  # noqa: BLE001
                return (True, "embed_error", 0.0)

        try:
            in_avg = _avg_cosine(question_vec, IN_VECTORS)
            out_avg = _avg_cosine(question_vec, OUT_VECTORS)
        except Exception:  # noqa: BLE001
            return (True, "embed_error", 0.0)

        diff = in_avg - out_avg
        conf = abs(diff)
        if diff > MARGIN:
            return (True, "in", conf)
        if -diff > MARGIN:
            return (False, "out", conf)
        return (True, "ambiguous", conf)


@dataclass(frozen=True)
class GuardrailReport:
    """Result of running the post-LLM checks on a plan or text answer."""

    in_scope: bool
    hard_rule_violations: list[str]
    untraced_numbers: list[str]

    @property
    def overall_pass(self) -> bool:
        return self.in_scope and not self.hard_rule_violations and not self.untraced_numbers


class HardRulesChecker:
    """Post-LLM regex scan against ``HARD_RULE_PATTERNS``.

    Returns the list of rule names whose pattern matched anywhere in the
    text. An empty list means the response avoided every banned recommendation.
    """

    def check(self, text: str) -> list[str]:
        if not text:
            return []
        lower = text.lower()
        fired: list[str] = []
        for rule, patterns in HARD_RULE_PATTERNS.items():
            if any(p.search(lower) for p in patterns):
                fired.append(rule)
        return fired


class NumberVerifier:
    """Post-LLM extraction + traceability check.

    Scans only ``current_situation`` and ``top_actions[*].why`` of a plan
    dict, or the full string for chat text. ``steps`` and ``what_to_avoid``
    are skipped on purpose — prose numerals like "1-2 steps" or "2-3
    mistakes" would otherwise trigger false positives.

    A figure is "untraced" when its magnitude passes ``MIN_CITABLE_VALUE``
    but the citation index built from ``facts`` does not name it.
    """

    def __init__(self, facts: FactSet, record: SanitisedRecord) -> None:
        from app.citations import _build_index  # local import — keeps citations private
        self._index = _build_index(facts)

    def check(self, plan_or_text: dict | str) -> list[str]:
        from app.citations import (
            _NUMBER_RE,
            MIN_CITABLE_VALUE,
            MAX_AMBIGUITY,
        )
        text = self._scoped_text(plan_or_text)
        if not text:
            return []
        untraced: list[str] = []
        for match in _NUMBER_RE.finditer(text):
            token = match.group(1)
            try:
                magnitude = float(token.replace(",", ""))
            except ValueError:
                continue
            if magnitude < MIN_CITABLE_VALUE:
                continue
            fact_ids = self._index.get(token)
            if not fact_ids or len(fact_ids) > MAX_AMBIGUITY:
                untraced.append(match.group(0).strip())
        return untraced

    @staticmethod
    def _scoped_text(plan_or_text: dict | str) -> str:
        if isinstance(plan_or_text, str):
            return plan_or_text
        if not isinstance(plan_or_text, dict):
            return ""
        parts: list[str] = []
        situation = plan_or_text.get("current_situation")
        if isinstance(situation, str):
            parts.append(situation)
        for action in plan_or_text.get("top_actions", []) or []:
            if isinstance(action, dict):
                why = action.get("why")
                if isinstance(why, str):
                    parts.append(why)
        return "\n".join(parts)


def check_response(
    plan_or_text: dict | str,
    facts: FactSet,
    record: SanitisedRecord,
) -> GuardrailReport:
    """Run every post-LLM check. Sync; CPU-only.

    Hard-rule violations are scanned against the full plan text (every
    string field) — a banned recommendation in a title is just as much a
    violation as one in the why field. Number verification is scoped to
    ``current_situation`` and ``top_actions[*].why`` so prose numerals in
    steps / what_to_avoid don't trip false positives.

    ``in_scope`` is always ``True`` here — the upstream pre-LLM scope check
    already ran in the SSE pipeline before the LLM call. The field is on
    the report for shape symmetry with future pre+post orchestrators, not
    because this function makes a scope decision.
    """
    full_text = (
        plan_or_text
        if isinstance(plan_or_text, str)
        else _flatten_all_text(plan_or_text)
    )
    hard = HardRulesChecker().check(full_text or "")
    untraced = NumberVerifier(facts, record).check(plan_or_text)
    return GuardrailReport(
        in_scope=True,
        hard_rule_violations=hard,
        untraced_numbers=untraced,
    )


def _flatten_all_text(plan: Any) -> str:
    """Walk every string value in a plan dict and join them with newlines.

    Mirrors the walk used by ``app.citations.cite_plan`` so hard-rule
    coverage matches the breadth of what the model can output.
    """
    parts: list[str] = []

    def _walk(value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            for item in value:
                _walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                _walk(item)

    _walk(plan)
    return "\n".join(parts)


__all__ = [
    "MARGIN",
    "OUT_OF_SCOPE_PATTERNS",
    "ScopeVerdict",
    "is_in_scope",
    "contains_out_of_scope_terms",
    "HARD_RULE_PATTERNS",
    "ScopeGuard",
    "HardRulesChecker",
    "NumberVerifier",
    "GuardrailReport",
    "check_response",
]
