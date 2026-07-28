"""Pydantic models for the HTTP API surface.

Kept separate from app/schemas.py, which models the internal pipeline. These are
the shapes the frontend consumes, so they are allowed to differ from the domain
models and are versioned alongside the UI.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas import LabelCategory, LabelSeverity, ScoreBand


# ============================================================================
# LABELS
# ============================================================================


class SourceView(BaseModel):
    """A citation source for a label."""

    title: str
    url: str


class LabelInstance(BaseModel):
    """One firing of a label.

    Most labels fire at most once, giving a single instance. Per-account labels
    such as `maxed_out_account` are expanded by the rule engine into one firing
    per account, so each gets its own instance with its own rendered copy.
    """

    account_id: Optional[str] = None
    account_name: Optional[str] = None
    message: str = ""
    mitigation_steps: list[str] = Field(default_factory=list)


class LabelView(BaseModel):
    """A single label, whether or not it fired for this customer.

    Unfired labels are returned so the UI can show the full diagnostic surface
    with the inactive checks dimmed. They carry their static KB copy but no
    instances and no rendered message.
    """

    label_id: str
    display_name: str
    category: LabelCategory
    severity: LabelSeverity
    priority_rank: int

    fired: bool

    # Static knowledge base copy.
    condition_human: str
    what_it_means_cibil: str
    why_it_matters: str

    # Per-firing rendered copy. Empty when the label did not fire.
    instances: list[LabelInstance] = Field(default_factory=list)

    # The precomputed facts this label is grounded in, already resolved to values.
    facts_to_cite: dict[str, Any] = Field(default_factory=dict)

    cibil_reason_codes: list[str] = Field(default_factory=list)
    sources: list[SourceView] = Field(default_factory=list)


class LabelsResponse(BaseModel):
    """The complete label diagnostic for one customer.

    Deterministic: no LLM is involved in producing this.
    """

    pan_masked: str
    customer_id: str
    score: int
    score_band: ScoreBand
    as_of_date: date

    total_labels: int
    n_fired: int

    # All labels, ordered by priority_rank (1 = most urgent) then label_id.
    labels: list[LabelView]

    # Fired label ids bucketed by severity, each bucket in priority order.
    # This is where overlapping utilisation tiers are made presentable without
    # touching the rule engine: the critical label leads its bucket and the
    # lower tiers read as supporting detail.
    fired_by_severity: dict[str, list[str]]


# ============================================================================
# CANVAS — the five must-have visualisations
# ============================================================================


class BandRange(BaseModel):
    """One CIBIL band and its inclusive score bounds.

    Sourced from kb_meta.cibil_bands so the API, the charts and the rule
    thresholds cannot disagree. Note frontend-charts-spec.md quotes FICO ranges
    (Fair 580-669, Good 670-739); those are not used.
    """

    name: str
    min_score: int
    max_score: int


class ScoreHero(BaseModel):
    """The big animated number, its band, and the deltas behind it."""

    score: int
    band: ScoreBand
    score_min: int = 300
    score_max: int = 900

    previous_score_1mo: Optional[int] = None
    previous_score_3mo: Optional[int] = None
    score_change_1mo: int = 0
    score_change_3mo: int = 0
    score_trend: str = "stable"

    # Where the score sits inside its own band, 0.0-1.0. Drives the gauge arc.
    band_progress: float = 0.0
    bands: list[BandRange] = Field(default_factory=list)


class ScoreTrendPoint(BaseModel):
    """One point on the 3-month score line."""

    label: str
    score: Optional[int] = None


class ScoreTrend(BaseModel):
    """The 3-month score trajectory."""

    points: list[ScoreTrendPoint]
    trend: str = "stable"
    change_3mo: int = 0
    # Present only when the trend is notable enough to annotate.
    annotation: Optional[str] = None


class CardUtilization(BaseModel):
    """Per-card utilisation, for the bars beneath the donut."""

    account_id: str
    display_name: str
    balance_paise: int
    credit_limit_paise: int
    utilization: float
    is_maxed: bool
    is_unused: bool
    # Amount to repay to reach the 30% target on this card. 0 when already under.
    paydown_to_target_paise: int = 0


class UtilizationView(BaseModel):
    """Overall utilisation plus the per-card breakdown."""

    overall_utilization: float
    total_balance_paise: int
    total_credit_limit_paise: int
    target_utilization: float = 0.30
    # Repayment needed to bring overall utilisation to the target.
    paydown_to_target_paise: int = 0

    cards: list[CardUtilization] = Field(default_factory=list)
    # Highest-utilisation card, for the "pay X on Y" callout.
    top_card_account_id: Optional[str] = None
    callout: Optional[str] = None


class HeatmapCell(BaseModel):
    """One month in the payment history heatmap."""

    period: str  # "YYYY-MM"
    label: str  # "June 2026"
    # Worst status across all accounts that month: 0 on time, 1/2/3 late tiers.
    status: int = 0
    has_data: bool = True


class PaymentHeatmap(BaseModel):
    """24 months of payment history, worst status per month."""

    cells: list[HeatmapCell]
    months_on_time: int
    months_total: int
    pct_on_time: float
    worst_status: int
    most_recent_late_period: Optional[str] = None
    summary: str = ""


class CanvasResponse(BaseModel):
    """Everything the canvas needs, computed without the LLM."""

    pan_masked: str
    customer_id: str
    as_of_date: date

    score_hero: ScoreHero
    score_trend: ScoreTrend
    utilization: UtilizationView
    payment_heatmap: PaymentHeatmap
    labels: LabelsResponse
