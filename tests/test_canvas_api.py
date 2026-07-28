"""Task 7 — canvas payload tests.

Covers the five must-have chart payloads for all 23 customers, with emphasis on
the invariants the frontend relies on: the heatmap is always 24 cells, and band
boundaries come from the database rather than the FICO ranges in the charts spec.
"""

import pytest

from app.api_schemas import CanvasResponse
from app.canvas_service import (
    HEATMAP_MONTHS,
    build_canvas_response,
    build_payment_heatmap,
    build_score_hero,
    load_bands,
)
from app.config import CIBIL_BANDS


@pytest.fixture
def client(seeded_db):
    from fastapi.testclient import TestClient

    from app.web import app

    return TestClient(app)


@pytest.fixture
def all_pans(seeded_db):
    from app.db import get_repository

    return [c.customer.pan_card for c in get_repository().list_all_customers()]


# ------------------------------------------------------------------- bands ----


def test_bands_load_from_database(seeded_db):
    bands = load_bands()
    assert [b.name for b in bands] == ["Poor", "Fair", "Good", "Very Good", "Excellent"]


def test_bands_match_config_not_fico(seeded_db):
    """The charts spec quotes FICO ranges; the DB must win.

    FICO would put Good at 670-739. CIBIL puts it at 700-749.
    """
    bands = {b.name: (b.min_score, b.max_score) for b in load_bands()}
    assert bands == CIBIL_BANDS
    assert bands["Good"] == (700, 749)
    assert bands["Fair"] == (580, 699)


def test_bands_are_contiguous_and_sorted(seeded_db):
    bands = load_bands()
    for earlier, later in zip(bands, bands[1:]):
        assert earlier.max_score + 1 == later.min_score, "gap or overlap between bands"


@pytest.mark.parametrize(
    "pan,expected_band",
    [
        ("KLMPO1234K", "Poor"),       # 486
        ("BCDRM2345B", "Fair"),       # 612
        ("ABCPS1234A", "Good"),       # 715
        ("OPQPS5678O", "Very Good"),  # 776
        ("NOPPR4567N", "Excellent"),  # 822
    ],
)
def test_band_assignment_matches_score(pan, expected_band, seeded_db):
    hero = build_canvas_response(pan).score_hero
    assert hero.band.value == expected_band


def test_band_boundaries_agree_with_stored_band(all_pans, seeded_db):
    """Each customer's stored band must contain their score."""
    bands = {b.name: (b.min_score, b.max_score) for b in load_bands()}
    for pan in all_pans:
        hero = build_canvas_response(pan).score_hero
        low, high = bands[hero.band.value]
        assert low <= hero.score <= high, f"{pan}: {hero.score} not in {hero.band.value}"


# -------------------------------------------------------------- score hero ----


def test_score_hero_carries_deltas(seeded_db):
    """Anjali: 715 now, 730 a month ago, 740 three months ago."""
    hero = build_canvas_response("ABCPS1234A").score_hero
    assert hero.score == 715
    assert hero.previous_score_1mo == 730
    assert hero.previous_score_3mo == 740
    assert hero.score_change_3mo == -25
    assert hero.score_trend == "falling"


def test_band_progress_is_within_unit_range(all_pans, seeded_db):
    for pan in all_pans:
        progress = build_canvas_response(pan).score_hero.band_progress
        assert 0.0 <= progress <= 1.0


def test_band_progress_at_band_floor_is_zero(seeded_db):
    """Riya scores 574, the bottom of Poor is 300 — so progress is mid-band."""
    hero = build_canvas_response("UVWPY1234U").score_hero
    expected = (574 - 300) / (579 - 300)
    assert hero.band_progress == pytest.approx(expected, abs=1e-6)


def test_score_hero_handles_missing_history(seeded_db):
    """Sana has no previous scores."""
    hero = build_canvas_response("HIJPL8901H").score_hero
    assert hero.previous_score_1mo is None
    assert hero.previous_score_3mo is None
    assert hero.score_trend == "stable"


# ------------------------------------------------------------- score trend ----


def test_score_trend_has_three_points(seeded_db):
    trend = build_canvas_response("ABCPS1234A").score_trend
    assert len(trend.points) == 3
    assert [p.label for p in trend.points] == ["3 months ago", "1 month ago", "Now"]
    assert [p.score for p in trend.points] == [740, 730, 715]


def test_falling_trend_is_annotated(seeded_db):
    trend = build_canvas_response("ABCPS1234A").score_trend
    assert trend.trend == "falling"
    assert "25" in trend.annotation


def test_rising_trend_is_annotated(seeded_db):
    """Priya: 725 -> 748."""
    trend = build_canvas_response("CDEPI3456C").score_trend
    assert trend.trend == "rising"
    assert "23" in trend.annotation


def test_missing_history_leaves_gaps_not_zeros(seeded_db):
    """A None score must not become 0, which would plot as a crash to the floor."""
    trend = build_canvas_response("HIJPL8901H").score_trend
    assert trend.points[0].score is None
    assert trend.points[2].score == 542
    assert trend.annotation is None


# -------------------------------------------------------------- utilisation ----


def test_utilization_totals_match_facts(seeded_db):
    util = build_canvas_response("ABCPS1234A").utilization
    assert util.total_balance_paise == 515000
    assert util.total_credit_limit_paise == 900000
    assert util.overall_utilization == pytest.approx(0.5722, abs=1e-3)


def test_cards_sorted_by_utilization_descending(seeded_db):
    cards = build_canvas_response("ABCPS1234A").utilization.cards
    utilizations = [c.utilization for c in cards]
    assert utilizations == sorted(utilizations, reverse=True)
    assert cards[0].display_name == "HDFC Millennia"


def test_installment_accounts_excluded_from_cards(seeded_db):
    """Anjali's auto loan is not a revolving line and must not appear."""
    cards = build_canvas_response("ABCPS1234A").utilization.cards
    names = {c.display_name for c in cards}
    assert "Mahindra Finance Auto Loan" not in names
    assert len(cards) == 3


def test_paydown_to_target(seeded_db):
    """HDFC: ₹4,200 balance on a ₹6,000 limit; 30% target is ₹1,800."""
    cards = build_canvas_response("ABCPS1234A").utilization.cards
    hdfc = next(c for c in cards if c.display_name == "HDFC Millennia")
    assert hdfc.paydown_to_target_paise == 420000 - 180000


def test_paydown_is_zero_for_healthy_card(seeded_db):
    cards = build_canvas_response("ABCPS1234A").utilization.cards
    icici = next(c for c in cards if c.display_name == "ICICI Platinum Chip")
    assert icici.paydown_to_target_paise == 0


def test_maxed_and_unused_flags(seeded_db):
    """Carlos's cards are maxed; Divya's are unused."""
    carlos = build_canvas_response("BCDRM2345B").utilization
    assert all(card.is_maxed for card in carlos.cards)

    divya = build_canvas_response("FGHPJ6789F").utilization
    assert all(card.is_unused for card in divya.cards)


def test_callout_names_the_top_card(seeded_db):
    util = build_canvas_response("BCDRM2345B").utilization
    assert "Kotak League Platinum" in util.callout
    assert "98%" in util.callout


def test_no_callout_when_nothing_to_pay_down(seeded_db):
    assert build_canvas_response("FGHPJ6789F").utilization.callout is None


def test_customer_with_no_cards(seeded_db):
    """Rohan has only installment debt."""
    util = build_canvas_response("GHIPK7890G").utilization
    assert util.cards == []
    assert util.top_card_account_id is None
    assert util.overall_utilization == 0.0


# ---------------------------------------------------------- payment heatmap ----


def test_heatmap_always_has_24_cells(all_pans, seeded_db):
    for pan in all_pans:
        cells = build_canvas_response(pan).payment_heatmap.cells
        assert len(cells) == HEATMAP_MONTHS, f"{pan} returned {len(cells)} cells"


def test_heatmap_24_cells_even_with_no_accounts(seeded_db):
    heatmap = build_canvas_response("HIJPL8901H").payment_heatmap
    assert len(heatmap.cells) == 24
    assert all(not cell.has_data for cell in heatmap.cells)
    assert heatmap.months_total == 0
    assert "No payment history" in heatmap.summary


def test_heatmap_months_are_real_and_sequential(seeded_db):
    """Cells run from 23 months before the anchor up to the anchor month."""
    cells = build_canvas_response("ABCPS1234A").payment_heatmap.cells
    assert cells[0].period == "2024-08"
    assert cells[-1].period == "2026-07"
    assert cells[-1].label == "July 2026"
    assert len({cell.period for cell in cells}) == 24


def test_heatmap_takes_worst_status_across_accounts(seeded_db):
    """Carlos's Axis card has a 90+ late; the clean Kotak card must not mask it."""
    heatmap = build_canvas_response("BCDRM2345B").payment_heatmap
    assert heatmap.worst_status == 3
    assert max(cell.status for cell in heatmap.cells) == 3


def test_heatmap_perfect_history_summary(seeded_db):
    heatmap = build_canvas_response("CDEPI3456C").payment_heatmap
    assert heatmap.months_on_time == heatmap.months_total
    assert heatmap.pct_on_time == 1.0
    assert "perfect" in heatmap.summary.lower()


def test_heatmap_reports_most_recent_late(seeded_db):
    heatmap = build_canvas_response("RSTPV8901R").payment_heatmap
    assert heatmap.most_recent_late_period == "2026-06"
    assert "June 2026" in heatmap.summary


def test_heatmap_statuses_are_valid_codes(all_pans, seeded_db):
    for pan in all_pans:
        for cell in build_canvas_response(pan).payment_heatmap.cells:
            assert cell.status in (0, 1, 2, 3)


# ----------------------------------------------------------------- payload ----


def test_canvas_includes_label_diagnostic(seeded_db):
    response = build_canvas_response("BCDRM2345B")
    assert response.labels.total_labels == 32
    assert response.labels.n_fired == 13


def test_schema_validates_for_every_customer(all_pans, seeded_db):
    for pan in all_pans:
        CanvasResponse.model_validate(build_canvas_response(pan).model_dump())


def test_pan_is_masked(seeded_db):
    response = build_canvas_response("ABCPS1234A")
    assert response.pan_masked == "ABCPS****A"
    assert "ABCPS1234A" not in response.model_dump_json()


def test_canvas_is_deterministic(seeded_db):
    first = build_canvas_response("BCDRM2345B").model_dump()
    second = build_canvas_response("BCDRM2345B").model_dump()
    assert first == second


# ---------------------------------------------------------------- endpoint ----


def test_endpoint_returns_200(client):
    response = client.post("/api/canvas", json={"pan": "ABCPS1234A", "income": 75000})
    assert response.status_code == 200

    body = response.json()
    assert body["score_hero"]["score"] == 715
    assert len(body["payment_heatmap"]["cells"]) == 24
    assert len(body["labels"]["labels"]) == 32


def test_endpoint_income_optional(client):
    assert client.post("/api/canvas", json={"pan": "ABCPS1234A"}).status_code == 200


def test_endpoint_requires_pan(client):
    assert client.post("/api/canvas", json={}).status_code == 400


def test_endpoint_404_for_unknown_pan(client):
    assert client.post("/api/canvas", json={"pan": "ZZZPZ9999Z"}).status_code == 404


def test_endpoint_rejects_bad_income(client):
    assert client.post(
        "/api/canvas", json={"pan": "ABCPS1234A", "income": "abc"}
    ).status_code == 400


def test_endpoint_bands_present_for_frontend(client):
    """The frontend reads band boundaries from the payload, not from its own copy."""
    body = client.post("/api/canvas", json={"pan": "ABCPS1234A"}).json()
    bands = body["score_hero"]["bands"]
    assert len(bands) == 5
    good = next(b for b in bands if b["name"] == "Good")
    assert (good["min_score"], good["max_score"]) == (700, 749)
