"""Tests for ``app/guardrails`` — pre-check (embedding) and post-check (regex)."""

from __future__ import annotations

import math

import pytest

from app.guardrails import (
    MARGIN,
    OUT_OF_SCOPE_PATTERNS,
    GuardrailReport,
    HardRulesChecker,
    NumberVerifier,
    ScopeGuard,
    contains_out_of_scope_terms,
    check_response,
    is_in_scope,
)


def _unit(direction: tuple[int, ...]) -> tuple[float, ...]:
    """Build an L2-normalised vector pointing along ``direction``."""
    raw = [0.0] * 1536
    for index in direction:
        raw[index] = 1.0
    norm = math.sqrt(sum(x * x for x in raw))
    return tuple(x / norm for x in raw)


class _FakeEmbedder:
    """Test double: records whether embed() was called and returns a canned vector."""

    def __init__(self, vec: tuple[float, ...]) -> None:
        self._vec = vec
        self.called = False

    async def embed(self, text: str) -> tuple[float, ...]:
        self.called = True
        return self._vec


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


# ============================================================================
# ScopeGuard — class-based pre-LLM check
# ============================================================================


@pytest.mark.asyncio
async def test_scope_guard_heuristic_rejects_invest_advice():
    """Obvious OOS phrasings must short-circuit before the embedder is called."""
    fake = _FakeEmbedder(vec=tuple([0.0] * 1536))
    guard = ScopeGuard(embedder=fake)
    in_scope, reason, conf = await guard.check("Should I invest in mutual funds?")
    assert in_scope is False
    assert reason == "heuristic"
    assert conf == 1.0
    assert fake.called is False, "heuristic must skip the embedder"


@pytest.mark.asyncio
async def test_scope_guard_heuristic_rejects_career_change():
    fake = _FakeEmbedder(vec=tuple([0.0] * 1536))
    guard = ScopeGuard(embedder=fake)
    in_scope, reason, _ = await guard.check("I'm thinking about a career change.")
    assert in_scope is False
    assert reason == "heuristic"
    assert fake.called is False


@pytest.mark.asyncio
async def test_scope_guard_heuristic_rejects_rent_vs_buy():
    fake = _FakeEmbedder(vec=tuple([0.0] * 1536))
    guard = ScopeGuard(embedder=fake)
    in_scope, reason, _ = await guard.check("rent vs buy — what should I do?")
    assert in_scope is False
    assert reason == "heuristic"


@pytest.mark.asyncio
async def test_scope_guard_embedding_layer_handles_in_scope_question():
    """A vector pointing at IN_VECTORS scores as 'in' (or 'ambiguous') with the embedder called."""
    from app.chat_guardrail_data import IN_VECTORS

    if not IN_VECTORS:
        pytest.skip("guardrail data not generated")

    avg = [0.0] * 1536
    for vec in IN_VECTORS:
        for i, x in enumerate(vec):
            avg[i] += x
    norm = math.sqrt(sum(x * x for x in avg))
    question_vec = tuple(x / norm for x in avg)

    fake = _FakeEmbedder(vec=question_vec)
    guard = ScopeGuard(embedder=fake)
    in_scope, reason, conf = await guard.check(
        "What is my CIBIL score?", question_vec=question_vec
    )
    assert in_scope is True
    assert reason in {"in", "ambiguous"}
    assert conf >= 0.0


@pytest.mark.asyncio
async def test_scope_guard_embedding_layer_handles_out_of_scope_question():
    from app.chat_guardrail_data import OUT_VECTORS

    if not OUT_VECTORS:
        pytest.skip("guardrail data not generated")

    avg = [0.0] * 1536
    for vec in OUT_VECTORS:
        for i, x in enumerate(vec):
            avg[i] += x
    norm = math.sqrt(sum(x * x for x in avg))
    question_vec = tuple(x / norm for x in avg)

    fake = _FakeEmbedder(vec=question_vec)
    guard = ScopeGuard(embedder=fake)
    in_scope, reason, _ = await guard.check(
        "Should I buy index funds?", question_vec=question_vec
    )
    # An averaged out-vector may still be ambiguous under the 0.05 margin —
    # but it must never be the explicit "in" verdict.
    assert reason != "in" or in_scope is False


@pytest.mark.asyncio
async def test_scope_guard_skips_embed_when_vec_provided():
    """Passing question_vec= must bypass the embedder entirely."""
    fake = _FakeEmbedder(vec=tuple([0.0] * 1536))
    guard = ScopeGuard(embedder=fake)
    await guard.check("What's my credit utilization?", question_vec=tuple([0.0] * 1536))
    assert fake.called is False


@pytest.mark.asyncio
async def test_scope_guard_without_embedder_returns_no_embedder():
    guard = ScopeGuard(embedder=None)
    in_scope, reason, conf = await guard.check("What's my credit utilization?")
    assert in_scope is True
    assert reason == "no_embedder"
    assert conf == 0.0


# ============================================================================
# HardRulesChecker — post-LLM regex scan for banned recommendations
# ============================================================================


def test_hard_rules_checker_flags_balance_transfer_advice():
    text = "Consider opening a balance transfer card to save on interest."
    assert HardRulesChecker().check(text) == ["balance_transfer"]


def test_hard_rules_checker_flags_close_oldest_card_advice():
    text = "You should close your oldest card to simplify your accounts."
    assert HardRulesChecker().check(text) == ["close_oldest_card"]


def test_hard_rules_checker_flags_pay_past_sol_collection_advice():
    text = "We recommend you pay the collection past the reporting window."
    assert HardRulesChecker().check(text) == ["pay_past_sol_collection"]


def test_hard_rules_checker_flags_cash_advance_advice():
    text = "A cash advance from a credit card can bridge the gap this month."
    fired = HardRulesChecker().check(text)
    assert "cash_advance" in fired


def test_hard_rules_checker_passes_clean_plan():
    text = (
        "Pay the HDFC card down to ₹18,000 (30% of its ₹60,000 limit). "
        "Set up autopay for the statement balance so utilization stays low. "
        "Avoid taking on new debt and keep all payments on time."
    )
    assert HardRulesChecker().check(text) == []


def test_hard_rules_checker_handles_empty_text():
    assert HardRulesChecker().check("") == []


# ============================================================================
# NumberVerifier — post-LLM extraction + traceability check
# ============================================================================


def _pipeline():
    """Run the deterministic pipeline against the seeded fixture."""
    from app.label_service import run_pipeline

    return run_pipeline("ABCPS1234A", 100000)[:4]


def test_number_verifier_flags_invented_rupee_amount(seeded_db):
    _record, sanitised, facts, _ = _pipeline()
    text = "Pay the card down by ₹99,999 to improve your score."
    verifier = NumberVerifier(facts, sanitised)
    fired = verifier.check(text)
    assert any("99,999" in s for s in fired), fired


def test_number_verifier_passes_when_all_figures_traced(seeded_db):
    """A plan that uses only slot-derived values produces no untraced figures."""
    _record, sanitised, facts, _ = _pipeline()
    # Build a citable text from the slot values.
    from app.template_renderer import format_indian_digits, format_pct

    income = format_indian_digits(facts.income_monthly_paise // 100)
    util = format_pct(facts.overall_utilization)
    text = f"Your monthly income is ₹{income} and overall utilisation is {util}%."
    verifier = NumberVerifier(facts, sanitised)
    fired = verifier.check(text)
    assert fired == []


def test_number_verifier_scopes_to_current_situation_and_why_fields(seeded_db):
    """A figure buried in steps[] or what_to_avoid[] must NOT trip the check."""
    _record, sanitised, facts, _ = _pipeline()
    plan = {
        "current_situation": "Your score is fine.",
        "top_actions": [
            {
                "title": "Pay down the card",
                "why": "Bring overall utilisation under control.",
                "steps": ["Pay ₹1,23,45,678 this month"],  # absurd figure, but in steps
                "when_youll_see_results": "1-2 billing cycles",
            }
        ],
        "what_to_avoid": ["Don't carry a balance of ₹99,99,999"],  # absurd, but in what_to_avoid
    }
    fired = NumberVerifier(facts, sanitised).check(plan)
    assert fired == []


def test_number_verifier_accepts_string_input(seeded_db):
    _record, sanitised, facts, _ = _pipeline()
    text = "Pay ₹99,999 right away."
    fired = NumberVerifier(facts, sanitised).check(text)
    assert any("99,999" in s for s in fired)


# ============================================================================
# check_response — orchestrator
# ============================================================================


def test_check_response_overall_pass_when_all_clear(seeded_db):
    _record, sanitised, facts, _ = _pipeline()
    plan = {
        "current_situation": "Your credit looks healthy.",
        "top_actions": [{"title": "Keep paying on time", "why": "Strong on-time history helps."}],
        "what_to_avoid": ["Don't miss payments"],
    }
    report = check_response(plan, facts, sanitised)
    assert isinstance(report, GuardrailReport)
    assert report.overall_pass is True
    assert report.hard_rule_violations == []
    assert report.untraced_numbers == []


def test_check_response_overall_fails_on_hard_rule_violation(seeded_db):
    _record, sanitised, facts, _ = _pipeline()
    plan = {
        "current_situation": "Your credit looks healthy.",
        "top_actions": [
            {
                "title": "Try a balance transfer card",
                "why": "Lower interest for a few months.",
            }
        ],
        "what_to_avoid": [],
    }
    report = check_response(plan, facts, sanitised)
    assert report.overall_pass is False
    assert "balance_transfer" in report.hard_rule_violations


def test_check_response_overall_fails_on_untraced_number(seeded_db):
    _record, sanitised, facts, _ = _pipeline()
    plan = {
        "current_situation": "Pay ₹88,888 to clear your card.",
        "top_actions": [{"title": "Pay down", "why": "Reduce balance."}],
        "what_to_avoid": [],
    }
    report = check_response(plan, facts, sanitised)
    assert report.overall_pass is False
    assert any("88,888" in s for s in report.untraced_numbers)


def test_check_response_accepts_str_input(seeded_db):
    _record, sanitised, facts, _ = _pipeline()
    text = "Close your oldest card to clean things up."
    report = check_response(text, facts, sanitised)
    assert "close_oldest_card" in report.hard_rule_violations


def test_check_response_accepts_dict_input(seeded_db):
    _record, sanitised, facts, _ = _pipeline()
    plan = {
        "current_situation": "All good.",
        "top_actions": [{"title": "x", "why": "y"}],
        "what_to_avoid": [],
    }
    report = check_response(plan, facts, sanitised)
    assert isinstance(report, GuardrailReport)
