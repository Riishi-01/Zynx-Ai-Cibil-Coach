"""Task 3 — FactSet v2 and fact resolution tests.

Covers the namespace reconciliation, the corrected payment-history month
derivation, hard-only inquiry filtering, and rate-shopping clustering.
"""

from datetime import date

import pytest

from app.fact_resolver import ALIASES, DERIVED, UnknownFact, resolve_fact, resolve_facts
from app.precompute import (
    RATE_SHOPPING_WINDOW_DAYS,
    _last_late_index,
    _shift_month,
    period_for_index,
    precompute_facts,
)
from app.schemas import FactSet

AS_OF = date(2026, 7, 25)


# ---------------------------------------------------------------- helpers ----


def _facts_for(pan: str, seeded_db):
    """Run the real pipeline for one PAN."""
    from app.data_fetch import fetch_customer_by_pan
    from app.pii_parser import sanitise_record

    record = fetch_customer_by_pan(pan)
    sanitised = sanitise_record(record)
    return precompute_facts(
        sanitised, monthly_income_inr=record.customer.income_monthly_paise // 100
    )


# ------------------------------------------------- month index derivation ----


def test_shift_month_crosses_year_boundary():
    assert _shift_month(date(2026, 7, 25), 0) == (2026, 7)
    assert _shift_month(date(2026, 7, 25), 7) == (2025, 12)
    assert _shift_month(date(2026, 7, 25), 23) == (2024, 8)


def test_period_for_index_maps_last_slot_to_anchor_month():
    """The final history slot is the anchor month, not an earlier one."""
    assert period_for_index(AS_OF, 23, 24) == "2026-07"


def test_period_for_index_maps_first_slot_23_months_back():
    assert period_for_index(AS_OF, 0, 24) == "2024-08"


def test_period_for_index_is_not_constant():
    """Regression guard.

    The original implementation returned the anchor month for every index, so
    every late looked like it happened this month.
    """
    periods = {period_for_index(AS_OF, i, 24) for i in range(24)}
    assert len(periods) == 24, "each index must map to a distinct month"


def test_last_late_index_finds_most_recent():
    history = [0] * 24
    history[10] = 1
    history[20] = 2
    assert _last_late_index(history) == 20


def test_last_late_index_none_when_clean():
    assert _last_late_index([0] * 24) is None


def test_most_recent_late_period_reports_real_month(seeded_db):
    """Ishita's most recent late sits at index 22 -> June 2026.

    History is [.., 1(19), 1(20), 0(21), 1(22), 0(23)], so the latest late is
    one month before the anchor month.
    """
    facts = _facts_for("RSTPV8901R", seeded_db)
    assert facts.most_recent_late_period == "2026-06"


def test_account_last_late_period_is_per_account(seeded_db):
    """Carlos has one delinquent card and one clean card."""
    facts = _facts_for("BCDRM2345B", seeded_db)
    assert facts.account_last_late_period["acc_002_1"] is not None
    assert facts.account_last_late_period["acc_002_2"] is None


# ------------------------------------------------------------- inquiries ----


def test_hard_inquiries_exclude_soft(seeded_db):
    """Nisha has 3 hard inquiries plus 1 soft; the soft one must not count."""
    facts = _facts_for("PQRPT6789P", seeded_db)
    assert facts.n_hard_inquiries_6mo == 3
    assert facts.inquiries_6mo == 4, "unfiltered count still includes the soft inquiry"


def test_hard_inquiry_windows_are_nested(seeded_db):
    facts = _facts_for("PQRPT6789P", seeded_db)
    assert facts.n_hard_inquiries_3mo <= facts.n_hard_inquiries_6mo
    assert facts.n_hard_inquiries_6mo <= facts.n_hard_inquiries_12mo


def test_rate_shopping_detected_for_clustered_inquiries(seeded_db):
    """Nisha's hard inquiries are 2026-06-10/18/21 — inside a 30-day window."""
    facts = _facts_for("PQRPT6789P", seeded_db)
    assert facts.is_rate_shopping is True


def test_rate_shopping_false_when_inquiries_are_spread(seeded_db):
    """Anjali's inquiries are ~3-7 weeks apart across April to June.

    2026-04-12 to 2026-05-03 is 21 days, which is inside the window, so this
    customer does cluster. Marcus has a single inquiry and cannot cluster.
    """
    facts = _facts_for("EFGKD5678E", seeded_db)
    assert facts.is_rate_shopping is False


def test_rate_shopping_false_with_no_inquiries(seeded_db):
    facts = _facts_for("CDEPI3456C", seeded_db)
    assert facts.is_rate_shopping is False


def test_rate_shopping_window_constant_is_30_days():
    assert RATE_SHOPPING_WINDOW_DAYS == 30


# ------------------------------------------------- new payment-history facts ----


def test_pct_payments_on_time_perfect_file(seeded_db):
    facts = _facts_for("CDEPI3456C", seeded_db)
    assert facts.pct_payments_on_time == 1.0


def test_pct_payments_on_time_no_history_defaults_to_one(seeded_db):
    """Sana has no accounts at all; nothing has gone wrong."""
    facts = _facts_for("HIJPL8901H", seeded_db)
    assert facts.pct_payments_on_time == 1.0
    assert facts.current_streak_months == 0


def test_pct_payments_on_time_with_lates(seeded_db):
    facts = _facts_for("KLMPO1234K", seeded_db)
    assert 0.0 < facts.pct_payments_on_time < 1.0


def test_current_streak_counts_clean_months_from_most_recent(seeded_db):
    """Arjun's lates are old (indices 8-12), so the recent streak is long."""
    facts = _facts_for("KLMPO1234K", seeded_db)
    assert facts.current_streak_months == 11


def test_current_streak_breaks_on_recent_late(seeded_db):
    """Ishita's most recent late is at index 22, so only index 23 is clean."""
    facts = _facts_for("RSTPV8901R", seeded_db)
    assert facts.current_streak_months == 1


def test_worst_status_recent_12mo_excludes_old_delinquency(seeded_db):
    """Arjun's 90+ lates are old; only the trailing 30-day late is recent.

    History is [0]*8 + [3,3,3,2,1] + [0]*11, so indices 8-11 hold the severe
    delinquency and index 12 holds a 30-day late. The trailing 12 months are
    indices 12-23, which capture the 1 but none of the 2s or 3s.
    """
    facts = _facts_for("KLMPO1234K", seeded_db)
    assert facts.worst_late_status == 3
    assert facts.worst_status_recent_12mo == 1


def test_has_recent_late_6mo(seeded_db):
    assert _facts_for("RSTPV8901R", seeded_db).has_recent_late_6mo is True
    assert _facts_for("CDEPI3456C", seeded_db).has_recent_late_6mo is False


# --------------------------------------------------------- utilisation ----


def test_max_single_card_utilization(seeded_db):
    """Anjali's cards are at 70%, 45% and 5%."""
    facts = _facts_for("ABCPS1234A", seeded_db)
    assert facts.max_single_card_utilization == pytest.approx(0.70)


def test_n_accounts_over_90pct(seeded_db):
    """Carlos has two cards above 90%."""
    facts = _facts_for("BCDRM2345B", seeded_db)
    assert facts.n_accounts_over_90pct == 2


def test_n_accounts_over_90pct_zero_when_healthy(seeded_db):
    assert _facts_for("CDEPI3456C", seeded_db).n_accounts_over_90pct == 0


# --------------------------------------------------------- collections ----


def test_collection_aggregates(seeded_db):
    """Farah has a medical collection and a paid one."""
    facts = _facts_for("LMNPP2345L", seeded_db)
    assert facts.n_collections == 2
    assert facts.has_medical_collections is True
    assert facts.total_collections_balance_paise == 675000 + 42000
    assert facts.n_paid_collections_24mo == 1


def test_no_collections_is_zeroed(seeded_db):
    facts = _facts_for("CDEPI3456C", seeded_db)
    assert facts.n_collections == 0
    assert facts.total_collections_balance_paise == 0
    assert facts.has_medical_collections is False


# ------------------------------------------------------------ age & mix ----


def test_account_type_breadth(seeded_db):
    """Aman holds a credit card, a secured card, a mortgage and an installment loan."""
    facts = _facts_for("QRSPU7890Q", seeded_db)
    assert facts.n_distinct_account_types == 4


def test_oldest_revolving_age_excludes_installment(seeded_db):
    """Rohan has only installment debt, so there is no revolving age."""
    facts = _facts_for("GHIPK7890G", seeded_db)
    assert facts.oldest_revolving_age_months == 0
    assert facts.oldest_account_months > 0


def test_accounts_opened_windows(seeded_db):
    """Marcus opened his only card in Feb 2026 — 5 months before the anchor.

    That places it inside both the 6-month and 12-month windows.
    """
    facts = _facts_for("EFGKD5678E", seeded_db)
    assert facts.n_accounts_opened_6mo == 1
    assert facts.n_accounts_opened_12mo == 1


def test_accounts_opened_windows_exclude_older_accounts(seeded_db):
    """Anjali's newest account is Jan 2024, well outside both windows."""
    facts = _facts_for("ABCPS1234A", seeded_db)
    assert facts.n_accounts_opened_6mo == 0
    assert facts.n_accounts_opened_12mo == 0


# ------------------------------------------------------------------ DTI ----


@pytest.mark.parametrize(
    "pan,expected",
    [
        ("BCDRM2345B", "severe"),   # 54%
        ("MNOPQ3456M", "high"),     # 38%
        ("GHIPK7890G", "moderate"), # 23%
        ("CDEPI3456C", "low"),      # 0%
    ],
)
def test_dti_category_bands(pan, expected, seeded_db):
    assert _facts_for(pan, seeded_db).dti_category == expected


def test_dti_category_never_contradicts_flags(seeded_db):
    """The banded category and the boolean flags must agree."""
    from app.db import get_repository

    for cust in get_repository().list_all_customers():
        facts = _facts_for(cust.customer.pan_card, seeded_db)
        if facts.is_severe_dti:
            assert facts.dti_category == "severe"
        elif facts.is_high_dti:
            assert facts.dti_category == "high"
        else:
            assert facts.dti_category in ("low", "moderate")


# ------------------------------------------------------- fact resolution ----


def test_every_kb_fact_name_resolves(seeded_db, kb_json):
    """The contract for this task: no facts_to_cite name may be unresolvable."""
    facts = _facts_for("ABCPS1234A", seeded_db)

    names = sorted({n for label in kb_json["labels"] for n in label.get("facts_to_cite", [])})
    unresolved = []
    for name in names:
        try:
            resolve_fact(facts, name)
        except UnknownFact:
            unresolved.append(name)

    assert not unresolved, f"unresolvable KB fact names: {unresolved}"


def test_aliases_point_at_real_fields():
    for kb_name, field in ALIASES.items():
        assert field in FactSet.model_fields, f"alias {kb_name} -> missing field {field}"


def test_alias_returns_same_value_as_field(seeded_db):
    facts = _facts_for("BCDRM2345B", seeded_db)
    assert resolve_fact(facts, "n_late_30d") == facts.n_lates_30_24mo
    assert resolve_fact(facts, "monthly_income_paise") == facts.income_monthly_paise
    assert resolve_fact(facts, "n_open_collections") == facts.n_collections


def test_derived_unit_conversion(seeded_db):
    facts = _facts_for("ABCPS1234A", seeded_db)
    assert resolve_fact(facts, "oldest_account_years") == pytest.approx(
        facts.oldest_account_months / 12.0
    )


def test_derived_boolean_projection(seeded_db):
    """Lin has a past-SOL collection; Priya has none."""
    assert resolve_fact(_facts_for("DEFPC4567D", seeded_db), "has_collections_past_sol") is True
    assert resolve_fact(_facts_for("CDEPI3456C", seeded_db), "has_collections_past_sol") is False


def test_unknown_fact_raises(seeded_db):
    facts = _facts_for("ABCPS1234A", seeded_db)
    with pytest.raises(UnknownFact):
        resolve_fact(facts, "not_a_real_fact")


def test_resolve_facts_skips_unknown(seeded_db):
    facts = _facts_for("ABCPS1234A", seeded_db)
    out = resolve_facts(facts, ["overall_utilization", "not_a_real_fact", "n_late_30d"])
    assert set(out) == {"overall_utilization", "n_late_30d"}


def test_alias_and_derived_names_do_not_shadow_fields():
    """A KB name must not be both a real field and an alias/derivation."""
    for name in list(ALIASES) + list(DERIVED):
        assert name not in FactSet.model_fields, f"{name} shadows a real FactSet field"


# ----------------------------------------------------------- determinism ----


def test_precompute_is_deterministic(seeded_db):
    """Same customer and as_of_date must yield identical facts every run."""
    a = _facts_for("ABCPS1234A", seeded_db).model_dump()
    b = _facts_for("ABCPS1234A", seeded_db).model_dump()
    # facts_computed_at is a wall-clock stamp and is excluded by design.
    a.pop("facts_computed_at")
    b.pop("facts_computed_at")
    assert a == b


def test_all_customers_precompute_without_error(seeded_db):
    from app.db import get_repository

    for cust in get_repository().list_all_customers():
        facts = _facts_for(cust.customer.pan_card, seeded_db)
        assert isinstance(facts, FactSet)
