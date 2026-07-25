"""Pydantic schemas for the CIBIL Credit Coach pipeline.

Invariant: All monetary amounts are stored as paise (integer, no floats).
1 INR = 100 paise. Example: ₹50,000 = 5_000_000 paise.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# ENUMS
# ============================================================================


class ScoreBand(str, Enum):
    POOR = "Poor"
    FAIR = "Fair"
    GOOD = "Good"
    VERY_GOOD = "Very Good"
    EXCELLENT = "Excellent"


class AccountType(str, Enum):
    CREDIT_CARD = "credit_card"
    INSTALLMENT_LOAN = "installment_loan"
    PERSONAL_LOAN = "personal_loan"
    MORTGAGE = "mortgage"
    AUTO_LOAN = "auto_loan"
    STUDENT_LOAN = "student_loan"
    SECURED_CARD = "secured_card"


class AccountStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    DELINQUENT = "delinquent"
    PAID = "paid"


class LabelCategory(str, Enum):
    UTILIZATION = "utilization"
    PAYMENT = "payment"
    INQUIRIES = "inquiries"
    COLLECTIONS = "collections"
    CREDIT_AGE = "credit_age"
    MIX = "mix"
    SCORE_TREND = "score_trend"
    DTI = "dti"
    DATA_QUALITY = "data_quality"


class LabelSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    OK = "ok"
    EXCELLENT = "excellent"
    INFO = "info"


# ============================================================================
# RAW DATA (from cibil_data.json)
# ============================================================================


class Customer(BaseModel):
    customer_id: str
    first_name: str
    dob_year: int
    income_bracket: str
    income_monthly_paise: int  # Integer paise (100 paise = ₹1)
    region: str
    pan_card: str


class Score(BaseModel):
    score: int  # 300-900
    previous_score_1mo: Optional[int] = None
    previous_score_3mo: Optional[int] = None
    band: ScoreBand
    score_as_of_date: date


class Account(BaseModel):
    account_id: str
    display_name: str
    account_type: AccountType
    balance_paise: int
    credit_limit_paise: Optional[int] = None  # NULL for non-revolving accounts
    monthly_payment_paise: int
    opened_date: date
    status: AccountStatus
    is_revolving: bool
    payment_history: list[int]  # 24 months of status codes: 0, 1 (30d), 2 (60d), 3 (90d+)


class Inquiry(BaseModel):
    inquiry_id: str
    creditor_name: str  # Name of the lending institution
    inquiry_date: date
    inquiry_type: str  # "hard", "soft", etc.


class Collection(BaseModel):
    collection_id: str
    original_creditor: str
    collection_agency: Optional[str] = None
    balance_paise: int  # Current balance of the collection
    opened_date: date  # When the collection was opened
    status: str  # "open", "paid", "settled", etc.
    is_past_sol: bool  # Past Statute of Limitations (7 years in India)
    is_disputable: bool  # Is it disputable/medical/etc.
    is_medical: Optional[bool] = False


class PublicRecord(BaseModel):
    record_id: str
    record_type: str  # "tax_lien", "bankruptcy", "judgment"
    filed_date: date  # When filed
    amount_paise: Optional[int] = None
    status: str  # "filed", "discharged", "active", etc.
    jurisdiction: Optional[str] = None  # e.g., "NCLT Mumbai"


class CustomerRecord(BaseModel):
    """The raw customer credit profile fetched from the database."""

    customer: Customer
    score: Score
    accounts: list[Account]
    inquiries: list[Inquiry]
    collections: list[Collection]
    public_records: list[PublicRecord]


# ============================================================================
# SANITISED DATA (after PII masking)
# ============================================================================


class SanitisedAccount(BaseModel):
    """Account after PII scrubbing (account number masked, etc.)."""

    account_id: str  # Stable token for this request
    display_name: str
    account_type: AccountType
    balance_paise: int
    credit_limit_paise: Optional[int] = None  # NULL for non-revolving
    monthly_payment_paise: int
    opened_date: date
    status: AccountStatus
    is_revolving: bool
    payment_history: list[int]


class SanitisedRecord(BaseModel):
    """Customer record after PII removal — safe for LLM exposure."""

    customer_id: str
    pan_masked: str  # e.g., "ABCDE****F"
    first_name_opt: Optional[str]  # Optional; may be None for privacy
    dob_year_opt: Optional[int]  # Optional; may be None or coarsened
    income_monthly_paise: int
    region: str  # OK to keep; not directly identifying
    score: int
    score_band: ScoreBand
    score_as_of_date: date
    accounts: list[SanitisedAccount]
    inquiries: list[Inquiry]  # Already low-PII
    collections: list[Collection]  # Already low-PII
    public_records: list[PublicRecord]  # Already low-PII


# ============================================================================
# PRECOMPUTE OUTPUT (74 FEATURES)
# ============================================================================


class FactSet(BaseModel):
    """All 74 deterministic facts computed from the sanitised record.
    
    These are the ONLY quantitative inputs the LLM receives.
    Sections map to precompute_list.md §1-§11.
    """

    # §0a PAN validation
    pan_format_valid: bool
    pan_taxpayer_type: str
    pan_is_individual: bool
    kyc_complete: bool

    # §1 Score & trend
    score: int
    score_band: ScoreBand
    previous_score_1mo: Optional[int] = None
    previous_score_3mo: Optional[int] = None
    score_change_1mo: int = 0
    score_change_3mo: int = 0
    score_trend: Literal["falling", "rising", "stable"] = "stable"
    score_volatility_3mo: int = 0
    freshness_days: int = 0

    # §2 Account-level facts (per account)
    account_utilizations: dict[str, float]  # {account_id -> util}
    account_months_on_book: dict[str, int]  # {account_id -> months}
    account_last_late_period: dict[str, Optional[str]]  # {account_id -> "YYYY-MM" or None}
    account_n_lates_24mo: dict[str, int]  # {account_id -> count}
    account_is_unused: dict[str, bool]  # {account_id -> bool}
    account_is_maxed: dict[str, bool]  # {account_id -> bool}

    # §3 Utilization rollups
    total_credit_limit_paise: int
    total_balance_paise: int
    overall_utilization: float
    utilization_concentration: float  # Herfindahl-Hirschman Index
    single_card_limit_share: float  # Largest card / total limit

    # §4 Payment history (24 months)
    n_lates_30_24mo: int
    n_lates_60_24mo: int
    n_lates_90_24mo: int
    worst_late_status: int  # 0, 1, 2, or 3
    most_recent_late_period: Optional[str] = None

    # §5 Inquiries
    inquiries_6mo: int
    inquiries_24mo: int
    is_rate_shopping: bool  # Clustered inquiries in 14-30d window
    credit_seeking_pattern: bool  # 3+ inquiries in 6 months

    # §6 Collections
    n_collections: int
    n_collections_past_sol: int  # Past 7-year reporting window
    n_collections_disputed: int
    n_collections_paid_still_reporting: int

    # §7 Public records (India-specific)
    has_tax_lien: bool
    has_bankruptcy_equivalent: bool

    # §8 Credit age & mix
    oldest_account_months: int
    is_thin_file: bool  # < 2 years
    is_extreme_thin_file: bool  # < 1 year
    n_revolving_accounts: int
    n_installment_accounts: int
    has_no_revolving_credit: bool
    n_unused_revolving_cards: int
    single_card_dependency: bool  # All revolving on one card

    # §9 Debt-to-Income (DTI)
    total_monthly_obligations_paise: int
    income_monthly_paise: int
    dti_ratio: float
    is_high_dti: bool  # DTI > 0.36
    is_severe_dti: bool  # DTI > 0.50

    # §10 Derived features
    credit_mix_score: int  # 0-100 heuristic
    credit_age_score: int  # 0-100 heuristic

    # §11 Metadata
    as_of_date: date
    facts_computed_at: datetime


# ============================================================================
# RULE ENGINE OUTPUT
# ============================================================================


class FiredLabel(BaseModel):
    """A label that fired based on one or more facts."""

    label_id: str
    priority: int  # 1 (most urgent) to 5 (contextual)
    evidence_fact_ids: list[str]  # fact_id values that triggered this label
    account_id: Optional[str] = None  # For per-account rules like maxed_out_account


# ============================================================================
# KNOWLEDGE BASE ENTRY
# ============================================================================


class KBSource(BaseModel):
    title: str
    url: str


class KBEntry(BaseModel):
    """A single label's coaching content from label_kb.json."""

    label_id: str
    display_name: str
    category: LabelCategory
    severity: LabelSeverity
    priority_rank: int
    fact_id: str  # The fact that triggers this label
    condition: str  # Programmatic condition (e.g., "overall_utilization > 0.90")
    condition_human: str
    what_it_means_cibil: str
    why_it_matters: str
    mitigation_steps: list[str]
    facts_to_cite: list[str]  # Which FactSet fields to surface
    cibil_reason_codes: list[str]
    personalized_response_template: str
    sources: list[KBSource]


# ============================================================================
# LLM REQUEST & RESPONSE
# ============================================================================


class Citation(BaseModel):
    """A source citation for a claim in the LLM output."""

    claim: str  # The text being cited
    sources: list[str]  # CIBIL reason codes or KB source titles
    fact_ids: list[str]  # Which precomputed facts ground this claim


class LLMResponse(BaseModel):
    """The analysed output from the LLM with citations."""

    score: int
    score_band: ScoreBand
    what_to_fix_first: str
    how_to_fix_it: str
    what_to_avoid: str
    citations: list[Citation]
    raw_response: str  # The full model output


# ============================================================================
# REQUEST/RESPONSE
# ============================================================================


class AnalyzeRequest(BaseModel):
    """End-user request to analyse a customer."""

    pan_card: str
    monthly_income_inr: int  # INR rupees, not paise


# ============================================================================
# EXCEPTIONS (DOMAIN ERRORS)
# ============================================================================


class CIBILCoachException(Exception):
    """Base exception for the credit coach."""

    pass


class InvalidPAN(CIBILCoachException):
    """PAN failed format validation."""

    pass


class CustomerNotFound(CIBILCoachException):
    """No credit file for this PAN."""

    pass


class DataFetchError(CIBILCoachException):
    """Error retrieving customer data."""

    pass


class PIILeakDetected(CIBILCoachException):
    """PII scrubbing failed — a raw identifier reached an unsafe boundary."""

    pass


class KBUnavailable(CIBILCoachException):
    """Knowledge base could not be loaded."""

    pass


class LLMError(CIBILCoachException):
    """LLM invocation failed."""

    pass
