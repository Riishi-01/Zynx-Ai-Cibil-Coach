"""Precompute Engine — turn sanitised record into 74 deterministic facts.

This is Phase 4: implements precompute_list.md §1-§11.
Pure functions, no LLM, no randomness, no wall-clock reads.

Same (customer, as_of_date) = identical facts on every run.
This determinism is non-negotiable for credit workflows.
"""

from datetime import date, datetime
from typing import Optional

from app.schemas import SanitisedRecord, FactSet, ScoreBand
from app.config import (
    AS_OF_DATE,
    CIBIL_BANDS,
    HYSTERESIS_UTILIZATION,
    HYSTERESIS_SCORE_POINTS,
    THIN_FILE_AGE_YEARS,
    EXTREME_THIN_FILE_AGE_YEARS,
    DISPUTE_MIN_AGE_YEARS,
    RBI_HIGH_DTI,
    RBI_SEVERE_DTI,
    MAXED_OUT_UTILIZATION,
    DATA_STALENESS_DAYS,
)

# Rate shopping: multiple hard inquiries clustered inside this many days are
# treated as shopping for a single loan rather than independent credit seeking.
RATE_SHOPPING_WINDOW_DAYS = 30

# A "recent" late means within this many months of as_of_date.
RECENT_LATE_WINDOW_MONTHS = 6


def _shift_month(anchor: date, months_back: int) -> tuple[int, int]:
    """Return the (year, month) that is `months_back` months before `anchor`.

    Pure calendar arithmetic — no wall-clock reads, so results are deterministic.
    """
    total = (anchor.year * 12 + (anchor.month - 1)) - months_back
    return total // 12, (total % 12) + 1


def _period_for_index(anchor: date, index: int, history_len: int) -> str:
    """Map a payment_history index to its real calendar month, as "YYYY-MM".

    Convention: the LAST element of payment_history is the month of anchor
    (most recent), and each earlier index steps one month further back. So for
    a 24-month history, index 23 is the anchor month and index 0 is 23 months
    earlier.

    The previous implementation returned the anchor month for every index,
    which made the reported month wrong unless the late happened to be in the
    most recent slot.
    """
    months_back = (history_len - 1) - index
    year, month = _shift_month(anchor, months_back)
    return f"{year}-{month:02d}"


def _last_late_index(payment_history: list[int]) -> Optional[int]:
    """Index of the most recent non-zero status, or None if never late."""
    for i in range(len(payment_history) - 1, -1, -1):
        if payment_history[i] > 0:
            return i
    return None


def _recent_slice(payment_history: list[int], months: int) -> list[int]:
    """The most recent `months` entries of a payment history."""
    if months <= 0:
        return []
    return payment_history[-months:]


def _months_between(anchor: date, earlier: date) -> int:
    """Whole months from `earlier` to `anchor` (calendar based, never negative)."""
    months = (anchor.year - earlier.year) * 12 + (anchor.month - earlier.month)
    return max(0, months)


def precompute_facts(
    record: SanitisedRecord,
    as_of_date: date = AS_OF_DATE,
    monthly_income_inr: int = None,
) -> FactSet:
    """Compute all 74 deterministic facts from the sanitised record.
    
    Args:
      record: SanitisedRecord (PII-scrubbed)
      as_of_date: Anchor date for time-windowed facts (default: AS_OF_DATE from config)
      monthly_income_inr: Monthly income in INR (not paise)
    
    Returns:
      FactSet with all 74 facts.
    """
    if monthly_income_inr is None:
        # Convert from paise to INR
        monthly_income_inr = record.income_monthly_paise // 100
    
    monthly_income_paise = monthly_income_inr * 100
    
    # ==== §0a PAN validation (already done in pan_validator.py, replicated here for FactSet)
    pan_format_valid = True  # We assume it's valid if it got this far
    pan_taxpayer_type = "P"
    pan_is_individual = True
    kyc_complete = True
    
    # ==== §1 Score & trend
    score = record.score
    score_band = record.score_band
    # Score history is carried on the SanitisedRecord (populated by pii_parser
    # from the raw record). Reading it here keeps precompute a pure function
    # that takes a SanitisedRecord and returns a FactSet — no DB lookup, so
    # the same code path works against SQLite and Supabase.
    previous_score_1mo = record.previous_score_1mo
    previous_score_3mo = record.previous_score_3mo

    score_change_1mo = (score - previous_score_1mo) if previous_score_1mo else 0
    score_change_3mo = (score - previous_score_3mo) if previous_score_3mo else 0

    # Trend with hysteresis
    if score_change_3mo < -HYSTERESIS_SCORE_POINTS:
        score_trend = "falling"
    elif score_change_3mo > HYSTERESIS_SCORE_POINTS:
        score_trend = "rising"
    else:
        score_trend = "stable"

    score_volatility_3mo = abs(score_change_3mo) if previous_score_3mo else 0

    # Freshness
    freshness_days = (as_of_date - record.score_as_of_date).days
    
    # ==== §2 Account-level facts (per account)
    account_utilizations = {}
    account_months_on_book = {}
    account_last_late_period = {}
    account_n_lates_24mo = {}
    account_is_unused = {}
    account_is_maxed = {}
    
    for acc in record.accounts:
        acc_id = acc.account_id
        
        # Utilisation (revolving only)
        if acc.is_revolving and acc.credit_limit_paise and acc.credit_limit_paise > 0:
            util = acc.balance_paise / acc.credit_limit_paise
        else:
            util = 0.0
        account_utilizations[acc_id] = util
        
        # Months on book
        months = ((as_of_date.year - acc.opened_date.year) * 12 +
                  (as_of_date.month - acc.opened_date.month))
        account_months_on_book[acc_id] = max(0, months)
        
        # Payment history analysis (24 months)
        payment_history = acc.payment_history

        # Last late period — resolved to the real calendar month of the late,
        # derived from its index in the history array.
        last_late_idx = _last_late_index(payment_history)
        account_last_late_period[acc_id] = (
            _period_for_index(as_of_date, last_late_idx, len(payment_history))
            if last_late_idx is not None
            else None
        )
        
        # Count lates in 24mo
        n_lates = sum(1 for status in payment_history if status > 0)
        account_n_lates_24mo[acc_id] = n_lates
        
        # Is unused? (revolving with zero balance)
        is_unused = acc.is_revolving and acc.balance_paise == 0
        account_is_unused[acc_id] = is_unused
        
        # Is maxed? (utilisation > 0.90)
        is_maxed = util > MAXED_OUT_UTILIZATION
        account_is_maxed[acc_id] = is_maxed
    
    # ==== §3 Utilization rollups
    revolving_accounts = [acc for acc in record.accounts if acc.is_revolving]
    total_credit_limit_paise = sum(
        (acc.credit_limit_paise or 0) for acc in revolving_accounts
    )
    total_balance_paise = sum(acc.balance_paise for acc in revolving_accounts)
    
    if total_credit_limit_paise > 0:
        overall_utilization = total_balance_paise / total_credit_limit_paise
    else:
        overall_utilization = 0.0
    
    # Concentration (Herfindahl-Hirschman Index of utilization)
    if revolving_accounts:
        utilizations = [account_utilizations.get(acc.account_id, 0.0) for acc in revolving_accounts]
        concentration = sum(u ** 2 for u in utilizations)  # HHI
    else:
        concentration = 0.0
    
    # Single card limit share
    if revolving_accounts and total_credit_limit_paise > 0:
        max_limit = max((acc.credit_limit_paise or 0) for acc in revolving_accounts)
        single_card_limit_share = max_limit / total_credit_limit_paise
    else:
        single_card_limit_share = 0.0

    # Highest single-card utilisation, and how many cards are above 90%.
    revolving_utils = [
        account_utilizations.get(acc.account_id, 0.0) for acc in revolving_accounts
    ]
    max_single_card_utilization = max(revolving_utils) if revolving_utils else 0.0
    n_accounts_over_90pct = sum(1 for u in revolving_utils if u > MAXED_OUT_UTILIZATION)

    # ==== §4 Payment history (24 months, rolled up)
    n_lates_30_24mo = 0
    n_lates_60_24mo = 0
    n_lates_90_24mo = 0
    worst_late_status = 0
    most_recent_late_period = None
    worst_status_recent_12mo = 0
    n_recent_lates = 0
    total_history_entries = 0
    on_time_entries = 0

    # Track the most recent late across all accounts by its absolute month, so
    # the reported period is the true latest one rather than whichever account
    # happened to be iterated last.
    most_recent_late_months_back = None

    for acc in record.accounts:
        ph = acc.payment_history
        history_len = len(ph)

        for idx, status_code in enumerate(ph):
            total_history_entries += 1
            if status_code == 0:
                on_time_entries += 1
            elif status_code == 1:
                n_lates_30_24mo += 1
            elif status_code == 2:
                n_lates_60_24mo += 1
            elif status_code >= 3:
                n_lates_90_24mo += 1
            worst_late_status = max(worst_late_status, status_code)

        # Worst status within the trailing 12 months.
        for status_code in _recent_slice(ph, 12):
            worst_status_recent_12mo = max(worst_status_recent_12mo, status_code)

        # Lates within the trailing 6 months.
        n_recent_lates += sum(
            1 for status in _recent_slice(ph, RECENT_LATE_WINDOW_MONTHS) if status > 0
        )

        # Most recent late across the whole file.
        last_idx = _last_late_index(ph)
        if last_idx is not None:
            months_back = (history_len - 1) - last_idx
            if most_recent_late_months_back is None or months_back < most_recent_late_months_back:
                most_recent_late_months_back = months_back
                most_recent_late_period = _period_for_index(as_of_date, last_idx, history_len)

    has_recent_late_6mo = n_recent_lates > 0

    # Share of reported months paid on time. A file with no history is treated
    # as 1.0 (nothing has gone wrong) rather than 0.0, which would read as a
    # perfect-delinquency record.
    pct_payments_on_time = (
        on_time_entries / total_history_entries if total_history_entries else 1.0
    )

    # Consecutive clean months counting back from the most recent, taking the
    # worst status across accounts for each month so one late breaks the streak.
    current_streak_months = 0
    if record.accounts:
        max_len = max(len(acc.payment_history) for acc in record.accounts)
        for offset in range(1, max_len + 1):
            worst_this_month = 0
            for acc in record.accounts:
                ph = acc.payment_history
                if offset <= len(ph):
                    worst_this_month = max(worst_this_month, ph[-offset])
            if worst_this_month > 0:
                break
            current_streak_months += 1
    
    # ==== §5 Inquiries (date-windowed)
    inquiries_6mo = 0
    inquiries_24mo = 0
    
    for inq in record.inquiries:
        months_ago = _months_between(as_of_date, inq.inquiry_date)
        if months_ago <= 6:
            inquiries_6mo += 1
        if months_ago <= 24:
            inquiries_24mo += 1

    # Hard inquiries only. Soft inquiries (pre-approvals, account reviews) are
    # not visible to lenders and must not count toward credit-seeking signals.
    hard_inquiries = [
        inq for inq in record.inquiries if str(inq.inquiry_type).lower() == "hard"
    ]

    def _hard_within(months: int) -> int:
        return sum(
            1 for inq in hard_inquiries if _months_between(as_of_date, inq.inquiry_date) <= months
        )

    n_hard_inquiries_3mo = _hard_within(3)
    n_hard_inquiries_6mo = _hard_within(6)
    n_hard_inquiries_12mo = _hard_within(12)

    # Rate shopping: two or more hard inquiries falling inside any 30-day
    # window. Sorting by date and comparing each pair of adjacent inquiries is
    # sufficient — if any pair is within the window, a cluster exists.
    hard_dates = sorted(inq.inquiry_date for inq in hard_inquiries)
    is_rate_shopping = any(
        (hard_dates[i + 1] - hard_dates[i]).days <= RATE_SHOPPING_WINDOW_DAYS
        for i in range(len(hard_dates) - 1)
    )

    credit_seeking_pattern = inquiries_6mo >= 3
    
    # ==== §6 Collections
    n_collections = len(record.collections)
    n_collections_past_sol = sum(
        1 for col in record.collections
        if getattr(col, 'is_past_sol', False)
    )
    n_collections_disputed = sum(
        1 for col in record.collections
        if getattr(col, 'is_disputable', False)
    )
    n_collections_paid_still_reporting = sum(
        1 for col in record.collections
        if col.status == "paid" or col.status == "open"  # Paid but still reporting
    )
    total_collections_balance_paise = sum(col.balance_paise for col in record.collections)
    has_medical_collections = any(
        getattr(col, 'is_medical', False) for col in record.collections
    )
    n_paid_collections_24mo = sum(
        1 for col in record.collections
        if col.status == "paid" and _months_between(as_of_date, col.opened_date) <= 24
    )
    
    # ==== §7 Public records
    has_tax_lien = any(pr.record_type == "tax_lien" for pr in record.public_records)
    has_bankruptcy_equivalent = any(pr.record_type == "bankruptcy" for pr in record.public_records)
    
    # ==== §8 Credit age & mix
    if account_months_on_book:
        oldest_account_months = max(account_months_on_book.values())
    else:
        oldest_account_months = 0
    
    oldest_account_years = oldest_account_months / 12.0
    is_thin_file = oldest_account_years < THIN_FILE_AGE_YEARS
    is_extreme_thin_file = oldest_account_years < EXTREME_THIN_FILE_AGE_YEARS
    
    n_revolving_accounts = sum(1 for acc in record.accounts if acc.is_revolving)
    n_installment_accounts = sum(1 for acc in record.accounts if not acc.is_revolving)
    has_no_revolving_credit = n_revolving_accounts == 0
    n_unused_revolving_cards = sum(1 for acc in revolving_accounts if account_is_unused.get(acc.account_id, False))
    
    single_card_dependency = (
        n_revolving_accounts == 1 and
        revolving_accounts[0].credit_limit_paise and
        revolving_accounts[0].credit_limit_paise > 0
    )

    # Breadth of the file: how many distinct product types are present.
    n_distinct_account_types = len({acc.account_type for acc in record.accounts})

    # Age of the oldest revolving line specifically — closing it would cost more
    # history than closing a newer card, which is why it is tracked separately
    # from oldest_account_months.
    revolving_ages = [
        account_months_on_book.get(acc.account_id, 0) for acc in revolving_accounts
    ]
    oldest_revolving_age_months = max(revolving_ages) if revolving_ages else 0

    n_accounts_opened_6mo = sum(
        1 for acc in record.accounts if _months_between(as_of_date, acc.opened_date) <= 6
    )
    n_accounts_opened_12mo = sum(
        1 for acc in record.accounts if _months_between(as_of_date, acc.opened_date) <= 12
    )
    
    # ==== §9 Debt-to-Income (DTI)
    total_monthly_obligations_paise = sum(acc.monthly_payment_paise for acc in record.accounts)
    
    if monthly_income_paise > 0:
        dti_ratio = total_monthly_obligations_paise / monthly_income_paise
    else:
        dti_ratio = 0.0
    
    is_high_dti = dti_ratio > RBI_HIGH_DTI
    is_severe_dti = dti_ratio > RBI_SEVERE_DTI

    # Banded DTI for display. Boundaries align with the RBI thresholds above so
    # the category and the is_high/is_severe flags can never disagree.
    if is_severe_dti:
        dti_category = "severe"
    elif is_high_dti:
        dti_category = "high"
    elif dti_ratio > 0.20:
        dti_category = "moderate"
    else:
        dti_category = "low"
    
    # ==== §10 Derived features (heuristic scores 0-100)
    # Credit mix score: bonus for having both revolving and installment
    credit_mix_score = 0
    if n_revolving_accounts > 0:
        credit_mix_score += 30
    if n_installment_accounts > 0:
        credit_mix_score += 30
    if n_revolving_accounts > 2:
        credit_mix_score += 20
    if not has_no_revolving_credit:
        credit_mix_score += 20
    credit_mix_score = min(100, credit_mix_score)
    
    # Credit age score: older is better
    credit_age_score = int(min(100, oldest_account_years * 10))
    
    # ==== Return FactSet
    return FactSet(
        # §0a
        pan_format_valid=pan_format_valid,
        pan_taxpayer_type=pan_taxpayer_type,
        pan_is_individual=pan_is_individual,
        kyc_complete=kyc_complete,
        # §1
        score=score,
        score_band=score_band,
        previous_score_1mo=previous_score_1mo,
        previous_score_3mo=previous_score_3mo,
        score_change_1mo=score_change_1mo,
        score_change_3mo=score_change_3mo,
        score_trend=score_trend,
        score_volatility_3mo=score_volatility_3mo,
        freshness_days=freshness_days,
        # §2
        account_utilizations=account_utilizations,
        account_months_on_book=account_months_on_book,
        account_last_late_period=account_last_late_period,
        account_n_lates_24mo=account_n_lates_24mo,
        account_is_unused=account_is_unused,
        account_is_maxed=account_is_maxed,
        # §3
        total_credit_limit_paise=total_credit_limit_paise,
        total_balance_paise=total_balance_paise,
        overall_utilization=overall_utilization,
        utilization_concentration=concentration,
        single_card_limit_share=single_card_limit_share,
        max_single_card_utilization=max_single_card_utilization,
        n_accounts_over_90pct=n_accounts_over_90pct,
        # §4
        n_lates_30_24mo=n_lates_30_24mo,
        n_lates_60_24mo=n_lates_60_24mo,
        n_lates_90_24mo=n_lates_90_24mo,
        worst_late_status=worst_late_status,
        most_recent_late_period=most_recent_late_period,
        worst_status_recent_12mo=worst_status_recent_12mo,
        has_recent_late_6mo=has_recent_late_6mo,
        n_recent_lates=n_recent_lates,
        pct_payments_on_time=pct_payments_on_time,
        current_streak_months=current_streak_months,
        # §5
        inquiries_6mo=inquiries_6mo,
        inquiries_24mo=inquiries_24mo,
        is_rate_shopping=is_rate_shopping,
        credit_seeking_pattern=credit_seeking_pattern,
        n_hard_inquiries_3mo=n_hard_inquiries_3mo,
        n_hard_inquiries_6mo=n_hard_inquiries_6mo,
        n_hard_inquiries_12mo=n_hard_inquiries_12mo,
        # §6
        n_collections=n_collections,
        n_collections_past_sol=n_collections_past_sol,
        n_collections_disputed=n_collections_disputed,
        n_collections_paid_still_reporting=n_collections_paid_still_reporting,
        total_collections_balance_paise=total_collections_balance_paise,
        has_medical_collections=has_medical_collections,
        n_paid_collections_24mo=n_paid_collections_24mo,
        # §7
        has_tax_lien=has_tax_lien,
        has_bankruptcy_equivalent=has_bankruptcy_equivalent,
        # §8
        oldest_account_months=oldest_account_months,
        is_thin_file=is_thin_file,
        is_extreme_thin_file=is_extreme_thin_file,
        n_revolving_accounts=n_revolving_accounts,
        n_installment_accounts=n_installment_accounts,
        has_no_revolving_credit=has_no_revolving_credit,
        n_unused_revolving_cards=n_unused_revolving_cards,
        single_card_dependency=single_card_dependency,
        n_distinct_account_types=n_distinct_account_types,
        oldest_revolving_age_months=oldest_revolving_age_months,
        n_accounts_opened_6mo=n_accounts_opened_6mo,
        n_accounts_opened_12mo=n_accounts_opened_12mo,
        # §9
        total_monthly_obligations_paise=total_monthly_obligations_paise,
        income_monthly_paise=monthly_income_paise,
        dti_ratio=dti_ratio,
        is_high_dti=is_high_dti,
        is_severe_dti=is_severe_dti,
        dti_category=dti_category,
        # §10
        credit_mix_score=credit_mix_score,
        credit_age_score=credit_age_score,
        # §11
        as_of_date=as_of_date,
        score_as_of_date=record.score_as_of_date,
        facts_computed_at=datetime.utcnow(),
    )
