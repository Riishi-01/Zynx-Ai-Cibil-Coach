"""Canvas payload service — deterministic data for the five must-have charts.

Score hero, score trend, utilisation donut with per-card bars, payment heatmap,
and the label diagnostic. None of it needs the LLM, so this is returned to the
browser immediately and the canvas renders before the coaching plan starts
streaming.

Band boundaries come from kb_meta.cibil_bands in the database, which is the
authoritative copy. frontend-charts-spec.md quotes FICO ranges instead
(Fair 580-669, Good 670-739) — those would disagree with the rule engine and
are deliberately not used.
"""

from typing import Optional

from app.api_schemas import (
    BandRange,
    CanvasResponse,
    CardUtilization,
    HeatmapCell,
    PaymentHeatmap,
    ScoreHero,
    ScoreTrend,
    ScoreTrendPoint,
    UtilizationView,
)
from app.label_service import build_labels_response, labels_response_from, run_pipeline
from app.precompute import period_for_index
from app.schemas import FactSet, SanitisedRecord
from app.template_renderer import (
    TARGET_UTILIZATION,
    format_indian_digits,
    format_period,
)

HEATMAP_MONTHS = 24


# ------------------------------------------------------------------- bands ----


def load_bands() -> list[BandRange]:
    """Read the CIBIL bands from kb_meta, falling back to config.

    The KB stores them as {"Good": "700-749", ...}. On Supabase (whether
    reached via DATABASE_URL=postgresql://… or via SUPABASE_URL alone on
    Vercel) the kb_meta table is unreachable via SQLAlchemy — Supabase uses
    the supabase-py REST client — so we skip the SQLite attempt entirely
    and fall through to the config constant, which carries the same values.

    The bug this prevents: when only SUPABASE_URL is set on Vercel
    (DATABASE_URL is unset, so IS_POSTGRES=False and IS_SQLITE=True), the
    SQLite branch opened cibil_coach.db — a file excluded from the Vercel
    bundle by `*.db` in excludeFiles — and queried kb_meta, raising
    OperationalError and turning /api/canvas and /api/analyze into HTTP 500s.
    """
    import os

    from app.config import CIBIL_BANDS
    from app.database import IS_POSTGRES

    bands: list[BandRange] = []

    supabase_active = IS_POSTGRES or bool(os.environ.get("SUPABASE_URL"))

    if not supabase_active:
        # SQLite path: read from kb_meta via SQLAlchemy.
        from app.database import get_db_session
        from app.models import KBMetaModel

        session = get_db_session()
        try:
            row = session.query(KBMetaModel).filter_by(key="cibil_bands").first()
            raw = row.value if row else None
        finally:
            session.close()

        if isinstance(raw, dict):
            for name, span in raw.items():
                try:
                    low, high = str(span).split("-")
                    bands.append(BandRange(name=name, min_score=int(low), max_score=int(high)))
                except (ValueError, AttributeError):
                    continue

    if not bands:
        # kb_meta missing, malformed, or on Supabase — fall back to config.
        bands = [
            BandRange(name=name, min_score=low, max_score=high)
            for name, (low, high) in CIBIL_BANDS.items()
        ]

    bands.sort(key=lambda b: b.min_score)
    return bands


def _band_progress(score: int, bands: list[BandRange], band_name: str) -> float:
    """How far through its own band the score sits, 0.0-1.0."""
    band = next((b for b in bands if b.name == band_name), None)
    if band is None or band.max_score <= band.min_score:
        return 0.0
    progress = (score - band.min_score) / (band.max_score - band.min_score)
    return max(0.0, min(1.0, progress))


# -------------------------------------------------------------- components ----


def build_score_hero(facts: FactSet) -> ScoreHero:
    bands = load_bands()
    return ScoreHero(
        score=facts.score,
        band=facts.score_band,
        previous_score_1mo=facts.previous_score_1mo,
        previous_score_3mo=facts.previous_score_3mo,
        score_change_1mo=facts.score_change_1mo,
        score_change_3mo=facts.score_change_3mo,
        score_trend=facts.score_trend,
        band_progress=_band_progress(facts.score, bands, facts.score_band.value),
        bands=bands,
    )


def build_score_trend(facts: FactSet) -> ScoreTrend:
    """Three points: 3 months ago, 1 month ago, now.

    Points with no historical score are returned with score=None so the chart
    can render a gap rather than a misleading zero.
    """
    points = [
        ScoreTrendPoint(label="3 months ago", score=facts.previous_score_3mo),
        ScoreTrendPoint(label="1 month ago", score=facts.previous_score_1mo),
        ScoreTrendPoint(label="Now", score=facts.score),
    ]

    annotation = None
    if facts.previous_score_3mo:
        if facts.score_trend == "falling":
            annotation = (
                f"Score dropped {abs(facts.score_change_3mo)} points in 3 months"
            )
        elif facts.score_trend == "rising":
            annotation = f"Score rose {facts.score_change_3mo} points in 3 months"

    return ScoreTrend(
        points=points,
        trend=facts.score_trend,
        change_3mo=facts.score_change_3mo,
        annotation=annotation,
    )


def build_utilization(facts: FactSet, record: SanitisedRecord) -> UtilizationView:
    cards: list[CardUtilization] = []

    for account in record.accounts:
        if not account.is_revolving or not account.credit_limit_paise:
            continue

        limit = account.credit_limit_paise
        utilization = facts.account_utilizations.get(account.account_id, 0.0)
        target_balance = int(TARGET_UTILIZATION * limit)

        cards.append(
            CardUtilization(
                account_id=account.account_id,
                display_name=account.display_name,
                balance_paise=account.balance_paise,
                credit_limit_paise=limit,
                utilization=utilization,
                is_maxed=facts.account_is_maxed.get(account.account_id, False),
                is_unused=facts.account_is_unused.get(account.account_id, False),
                paydown_to_target_paise=max(0, account.balance_paise - target_balance),
            )
        )

    # Highest utilisation first — the actionable ordering.
    cards.sort(key=lambda c: c.utilization, reverse=True)

    overall_paydown = max(
        0,
        int(facts.total_balance_paise - TARGET_UTILIZATION * facts.total_credit_limit_paise),
    )

    top_card = cards[0] if cards else None
    callout = None
    if top_card and top_card.paydown_to_target_paise > 0:
        callout = (
            f"Highest card: {top_card.display_name} at "
            f"{int(round(top_card.utilization * 100))}%. "
            f"Pay ₹{format_indian_digits(top_card.paydown_to_target_paise // 100)} "
            f"to bring it to 30%."
        )

    return UtilizationView(
        overall_utilization=facts.overall_utilization,
        total_balance_paise=facts.total_balance_paise,
        total_credit_limit_paise=facts.total_credit_limit_paise,
        target_utilization=TARGET_UTILIZATION,
        paydown_to_target_paise=overall_paydown,
        cards=cards,
        top_card_account_id=top_card.account_id if top_card else None,
        callout=callout,
    )


def build_payment_heatmap(facts: FactSet, record: SanitisedRecord) -> PaymentHeatmap:
    """Exactly 24 cells, each the worst status across accounts for that month.

    Always returns 24 cells even for a customer with no accounts, so the grid
    never changes shape.
    """
    # Index 0 is the oldest month, index 23 the anchor month.
    worst_by_index: list[int] = [0] * HEATMAP_MONTHS
    has_data: list[bool] = [False] * HEATMAP_MONTHS

    for account in record.accounts:
        history = account.payment_history
        # Align the end of each history with the end of the window, so accounts
        # with shorter histories occupy the most recent cells.
        for offset in range(1, min(len(history), HEATMAP_MONTHS) + 1):
            cell_index = HEATMAP_MONTHS - offset
            status = history[-offset]
            worst_by_index[cell_index] = max(worst_by_index[cell_index], status)
            has_data[cell_index] = True

    cells: list[HeatmapCell] = []
    for index in range(HEATMAP_MONTHS):
        period = period_for_index(facts.as_of_date, index, HEATMAP_MONTHS)
        cells.append(
            HeatmapCell(
                period=period,
                label=format_period(period) or period,
                status=worst_by_index[index],
                has_data=has_data[index],
            )
        )

    reported = [cell for cell in cells if cell.has_data]
    on_time = sum(1 for cell in reported if cell.status == 0)
    total = len(reported)
    pct = (on_time / total) if total else 1.0

    if total == 0:
        summary = "No payment history reported yet."
    elif on_time == total:
        summary = f"{on_time}/{total} months on time — perfect history."
    else:
        summary = f"{on_time}/{total} months on time."
        if facts.most_recent_late_period:
            summary += f" Most recent late: {format_period(facts.most_recent_late_period)}."

    return PaymentHeatmap(
        cells=cells,
        months_on_time=on_time,
        months_total=total,
        pct_on_time=pct,
        worst_status=facts.worst_late_status,
        most_recent_late_period=facts.most_recent_late_period,
        summary=summary,
    )


# ----------------------------------------------------------------- payload ----


def build_canvas_response(
    pan_card: str, monthly_income_inr: Optional[int] = None
) -> CanvasResponse:
    """Assemble the full canvas payload for a customer."""
    record, sanitised, facts, fired, first_name = run_pipeline(pan_card, monthly_income_inr)

    return CanvasResponse(
        pan_masked=sanitised.pan_masked,
        customer_id=sanitised.customer_id,
        as_of_date=facts.as_of_date,
        score_hero=build_score_hero(facts),
        score_trend=build_score_trend(facts),
        utilization=build_utilization(facts, sanitised),
        payment_heatmap=build_payment_heatmap(facts, sanitised),
        # Reuses the single pipeline run above rather than recomputing.
        labels=labels_response_from(sanitised, facts, fired),
        first_name=first_name,
    )
