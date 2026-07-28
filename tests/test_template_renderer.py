"""Task 5 — template rendering tests.

The headline contract: no fired label, for any of the 23 customers, may produce
a rendered string containing a raw {placeholder}.
"""

from datetime import date

import pytest

from app.template_renderer import (
    TARGET_UTILIZATION,
    format_date,
    format_indian_digits,
    format_inr,
    format_pct,
    format_period,
    render_steps,
    render_template,
    unresolved_placeholders,
)


# --------------------------------------------------------------- helpers ----


def _pipeline(pan: str):
    """Return (facts, sanitised_record, fired_labels) for a PAN."""
    from app.data_fetch import fetch_customer_by_pan
    from app.pii_parser import sanitise_record
    from app.precompute import precompute_facts
    from app.rule_engine import fire_labels

    record = fetch_customer_by_pan(pan)
    sanitised = sanitise_record(record)
    facts = precompute_facts(
        sanitised, monthly_income_inr=record.customer.income_monthly_paise // 100
    )
    return facts, sanitised, fire_labels(facts)


# ----------------------------------------------------- Indian digit grouping ----


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "0"),
        (5, "5"),
        (100, "100"),
        (999, "999"),
        (1000, "1,000"),
        (4200, "4,200"),
        (99999, "99,999"),
        (100000, "1,00,000"),
        (120000, "1,20,000"),
        (515000, "5,15,000"),
        (1000000, "10,00,000"),
        (10000000, "1,00,00,000"),
    ],
)
def test_indian_digit_grouping(value, expected):
    assert format_indian_digits(value) == expected


def test_indian_grouping_is_not_western():
    """The distinguishing case: western grouping would give '120,000'."""
    assert format_indian_digits(120000) == "1,20,000"


def test_negative_values_keep_sign():
    assert format_indian_digits(-120000) == "-1,20,000"


def test_format_inr_converts_paise_to_rupees():
    assert format_inr(12000000) == "1,20,000"


def test_format_pct_rounds_to_whole_number():
    assert format_pct(0.572) == "57"
    assert format_pct(0.9625) == "96"
    assert format_pct(0.0) == "0"


def test_format_period_humanises():
    assert format_period("2026-06") == "June 2026"
    assert format_period(None) is None


def test_format_date_humanises():
    assert format_date(date(2024, 3, 15)) == "March 2024"
    assert format_date(None) is None


# ------------------------------------------------------- the main contract ----


def test_no_unresolved_placeholders_for_any_fired_label(seeded_db):
    """Every fired label, every customer, must render cleanly."""
    from app.db import get_repository
    from app.kb_loader import get_knowledge_base

    kb = get_knowledge_base()
    failures = []

    for cust in get_repository().list_all_customers():
        pan = cust.customer.pan_card
        facts, record, fired = _pipeline(pan)
        for label in fired:
            entry = kb.get(label.label_id)
            if entry is None:
                continue
            rendered = render_template(entry, facts, record, label)
            leftover = unresolved_placeholders(rendered)
            if leftover:
                failures.append((pan, label.label_id, leftover))

    assert not failures, f"unresolved placeholders: {failures}"


def test_no_unresolved_placeholders_in_steps(seeded_db):
    from app.db import get_repository
    from app.kb_loader import get_knowledge_base

    kb = get_knowledge_base()
    failures = []

    for cust in get_repository().list_all_customers():
        facts, record, fired = _pipeline(cust.customer.pan_card)
        for label in fired:
            entry = kb.get(label.label_id)
            if entry is None:
                continue
            for step in render_steps(entry, facts, record, label):
                leftover = unresolved_placeholders(step)
                if leftover:
                    failures.append((cust.customer.pan_card, label.label_id, leftover))

    assert not failures, f"unresolved placeholders in steps: {failures}"


def test_rendered_output_is_never_empty_for_fired_labels(seeded_db):
    """Dropping sentences must not silently erase an entire message."""
    from app.db import get_repository
    from app.kb_loader import get_knowledge_base

    kb = get_knowledge_base()
    empties = []

    for cust in get_repository().list_all_customers():
        facts, record, fired = _pipeline(cust.customer.pan_card)
        for label in fired:
            entry = kb.get(label.label_id)
            if entry is None:
                continue
            if not render_template(entry, facts, record, label).strip():
                empties.append((cust.customer.pan_card, label.label_id))

    assert not empties, f"rendered to empty string: {empties}"


# ------------------------------------------------------- specific renderings ----


def test_utilization_numbers_match_facts(seeded_db):
    """Anjali: 57% overall, ₹5,15,000 of ₹9,00,000."""
    from app.kb_loader import get_knowledge_base

    facts, record, fired = _pipeline("ABCPS1234A")
    entry = get_knowledge_base().get("high_utilization")
    label = next(f for f in fired if f.label_id == "high_utilization")

    rendered = render_template(entry, facts, record, label)
    assert "57%" in rendered


def test_top_card_is_the_highest_utilisation_card(seeded_db):
    """Anjali's HDFC Millennia is at 70%, the highest of her three cards."""
    from app.kb_loader import get_knowledge_base

    facts, record, _ = _pipeline("ABCPS1234A")
    entry = get_knowledge_base().get("maxed_out")

    rendered = render_template(entry, facts, record, None)
    assert "HDFC Millennia" in rendered


def test_maxed_out_account_uses_the_fired_account(seeded_db):
    """Carlos has two maxed cards; each expansion must name its own card."""
    from app.kb_loader import get_knowledge_base

    facts, record, fired = _pipeline("BCDRM2345B")
    entry = get_knowledge_base().get("maxed_out_account")

    per_account = [f for f in fired if f.label_id == "maxed_out_account"]
    assert len(per_account) == 2, "expected one label per maxed card"

    names = set()
    for label in per_account:
        rendered = render_template(entry, facts, record, label)
        account = next(a for a in record.accounts if a.account_id == label.account_id)
        assert account.display_name in rendered
        names.add(account.display_name)

    assert names == {"Axis Bank Neo", "Kotak League Platinum"}


def test_target_is_30_percent_of_the_card_limit(seeded_db):
    """Carlos's Axis card has a ₹20,000 limit, so the target is ₹6,000."""
    from app.kb_loader import get_knowledge_base

    facts, record, fired = _pipeline("BCDRM2345B")
    entry = get_knowledge_base().get("maxed_out_account")
    label = next(
        f for f in fired if f.label_id == "maxed_out_account" and f.account_id == "acc_002_1"
    )

    rendered = render_template(entry, facts, record, label)
    # limit 2000000 paise = ₹20,000; 30% = ₹6,000
    assert "6,000" in rendered
    assert TARGET_UTILIZATION == 0.30


def test_delinquency_names_the_right_account_and_month(seeded_db):
    """Ishita's late is on the RBL card in June 2026."""
    from app.kb_loader import get_knowledge_base

    facts, record, fired = _pipeline("RSTPV8901R")
    entry = get_knowledge_base().get("recent_late_payment")
    label = next(f for f in fired if f.label_id == "recent_late_payment")

    rendered = render_template(entry, facts, record, label)
    assert "RBL Shoprite" in rendered
    assert "June 2026" in rendered


def test_collection_names_the_disputable_creditor(seeded_db):
    """Anjali's disputable collection is the Airtel Postpaid account."""
    from app.kb_loader import get_knowledge_base

    facts, record, fired = _pipeline("ABCPS1234A")
    entry = get_knowledge_base().get("disputable_collection")
    label = next(f for f in fired if f.label_id == "disputable_collection")

    rendered = render_template(entry, facts, record, label)
    assert "Airtel Postpaid" in rendered
    assert "March 2024" in rendered


def test_past_sol_collection_picks_the_past_sol_item(seeded_db):
    """Riya has two collections; only the BSNL one is past SOL."""
    from app.kb_loader import get_knowledge_base

    facts, record, fired = _pipeline("UVWPY1234U")
    entry = get_knowledge_base().get("collection_past_sol")
    label = next(f for f in fired if f.label_id == "collection_past_sol")

    rendered = render_template(entry, facts, record, label)
    assert "BSNL Broadband" in rendered
    assert "Bajaj Finance EMI Card" not in rendered


def test_score_context_renders_score_and_band(seeded_db):
    from app.kb_loader import get_knowledge_base

    facts, record, fired = _pipeline("ABCPS1234A")
    entry = get_knowledge_base().get("credit_score_context")
    label = next(f for f in fired if f.label_id == "credit_score_context")

    rendered = render_template(entry, facts, record, label)
    assert "715" in rendered
    assert "Good" in rendered


def test_oldest_card_at_risk_names_the_unused_card(seeded_db):
    """Priya's unused Citi Rewards card was opened in 2018."""
    from app.kb_loader import get_knowledge_base

    facts, record, fired = _pipeline("CDEPI3456C")
    entry = get_knowledge_base().get("oldest_card_at_risk")
    label = next((f for f in fired if f.label_id == "oldest_card_at_risk"), None)
    assert label is not None, "expected oldest_card_at_risk to fire for Priya"

    rendered = render_template(entry, facts, record, label)
    assert "Citi Rewards" in rendered


# --------------------------------------------------- sentence-dropping rule ----


def test_sentence_with_missing_placeholder_is_dropped(seeded_db):
    """A None value removes its sentence and leaves the rest intact."""
    from app.template_renderer import _fill

    text = "Kept sentence. Dropped {missing} sentence. Also kept."
    out = _fill(text, {"missing": None})
    assert "Kept sentence." in out
    assert "Also kept." in out
    assert "Dropped" not in out
    assert "{" not in out


def test_resolved_placeholder_is_substituted():
    from app.template_renderer import _fill

    assert _fill("Score is {score}.", {"score": "715"}) == "Score is 715."


def test_text_without_placeholders_is_untouched():
    from app.template_renderer import _fill

    text = "No placeholders here at all."
    assert _fill(text, {}) == text


def test_domain_names_are_not_split_as_sentences():
    """Regression: 'cibil.com' must not become 'cibil. com'."""
    from app.template_renderer import _fill

    text = "File a dispute with CIBIL (cibil.com dispute portal) and the bureaus."
    assert _fill(text, {}) == text


def test_decimals_are_not_split_as_sentences():
    from app.template_renderer import _fill

    text = "Keep utilization below 0.30 at all times."
    assert _fill(text, {}) == text


def test_sentence_splitting_preserves_all_sentences():
    from app.template_renderer import _fill

    text = "First one. Second one! Third one? Fourth."
    out = _fill(text, {})
    for fragment in ("First one.", "Second one!", "Third one?", "Fourth."):
        assert fragment in out


def test_score_rising_drops_the_falling_sentence(seeded_db):
    """Priya's score is rising, so drop_points is None and must not appear."""
    from app.kb_loader import get_knowledge_base

    facts, record, fired = _pipeline("CDEPI3456C")
    entry = get_knowledge_base().get("score_rising")
    label = next(f for f in fired if f.label_id == "score_rising")

    rendered = render_template(entry, facts, record, label)
    assert not unresolved_placeholders(rendered)
    assert "23" in rendered  # 748 - 725


# -------------------------------------------------------- no-history file ----


def test_customer_with_no_credit_history_renders(seeded_db):
    """Sana has no accounts at all; nothing may crash or leak a brace."""
    from app.kb_loader import get_knowledge_base

    kb = get_knowledge_base()
    facts, record, fired = _pipeline("HIJPL8901H")

    assert fired, "expected at least the contextual labels to fire"
    for label in fired:
        entry = kb.get(label.label_id)
        if entry is None:
            continue
        rendered = render_template(entry, facts, record, label)
        assert not unresolved_placeholders(rendered), label.label_id
