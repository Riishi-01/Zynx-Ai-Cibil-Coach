"""Tests for ``app/guardrails`` — pre-check (embedding) and post-check (regex)."""

from __future__ import annotations

import math

import pytest

from app.guardrails import (
    MARGIN,
    OUT_OF_SCOPE_PATTERNS,
    contains_out_of_scope_terms,
    is_in_scope,
)


def _unit(direction: tuple[int, ...]) -> tuple[float, ...]:
    """Build an L2-normalised vector pointing along ``direction``."""
    raw = [0.0] * 1536
    for index in direction:
        raw[index] = 1.0
    norm = math.sqrt(sum(x * x for x in raw))
    return tuple(x / norm for x in raw)


@pytest.mark.asyncio
async def test_is_in_scope_pulls_towards_in_examples():
    """A vector aligned with IN_VECTORS scores at least as close to the in-bank
    as to the out-bank. With a threshold > 0 the verdict is in-scope; with the
    default 0.05 margin the verdict remains ambiguous, but never out-of-scope.
    """
    from app.chat_guardrail_data import IN_VECTORS, OUT_VECTORS

    if not IN_VECTORS or not OUT_VECTORS:
        pytest.skip("guardrail data not generated")

    avg = [0.0] * 1536
    for vec in IN_VECTORS:
        for i, x in enumerate(vec):
            avg[i] += x
    norm = math.sqrt(sum(x * x for x in avg))
    question = tuple(x / norm for x in avg)

    verdict = await is_in_scope(question)
    assert verdict.in_scope is True
    assert verdict.reason in {"in", "ambiguous"}


@pytest.mark.asyncio
async def test_is_in_scope_pulls_towards_out_examples():
    """The averaged out-of-scope direction must never be classified as
    "in-scope with a high-confidence in signal". The guardrail is allowed
    to fall through as ambiguous, which is the current default margin (0.05)
    reflects — but it must not emit the explicit "in" verdict.
    """
    from app.chat_guardrail_data import IN_VECTORS, OUT_VECTORS

    if not IN_VECTORS or not OUT_VECTORS:
        pytest.skip("guardrail data not generated")

    avg = [0.0] * 1536
    for vec in OUT_VECTORS:
        for i, x in enumerate(vec):
            avg[i] += x
    norm = math.sqrt(sum(x * x for x in avg))
    question = tuple(x / norm for x in avg)

    verdict = await is_in_scope(question)
    assert verdict.reason != "in"


@pytest.mark.asyncio
async def test_is_in_scope_falls_back_to_true_on_bad_input():
    """A wrong-dimension question must not raise — pass-through to the model."""
    verdict = await is_in_scope((0.1, 0.2, 0.3))
    assert verdict.in_scope is True


def test_post_check_catches_investment_advice():
    text = "You should invest in index funds and forget about credit scores."
    assert contains_out_of_scope_terms(text) is True


def test_post_check_catches_career_advice():
    text = "Consider a career change — your salary would increase significantly."
    assert contains_out_of_scope_terms(text) is True


def test_post_check_catches_tax_planning_advice():
    text = "Use section 80c deductions to save on taxes this year."
    assert contains_out_of_scope_terms(text) is True


def test_post_check_catches_start_business_advice():
    text = "Now is a great time to start your own business on the side."
    assert contains_out_of_scope_terms(text) is True


def test_post_check_safe_response_passes():
    text = (
        "Pay the HDFC card down to ₹18,000 (30% of its ₹60,000 limit). "
        "Set up autopay for the statement balance so utilization stays low."
    )
    assert contains_out_of_scope_terms(text) is False


def test_post_check_handles_empty_text():
    assert contains_out_of_scope_terms("") is False


def test_post_check_does_not_flag_generic_credit_terms():
    """Words like 'rate' or 'card' must not trip the post-check by themselves."""
    text = "Rate-shopping within 14 days counts as a single hard inquiry; keep cards active."
    assert contains_out_of_scope_terms(text) is False


def test_post_check_patterns_are_compiled():
    import re

    for pattern in OUT_OF_SCOPE_PATTERNS:
        assert isinstance(pattern, re.Pattern)


def test_margin_constant_is_positive():
    assert MARGIN > 0
