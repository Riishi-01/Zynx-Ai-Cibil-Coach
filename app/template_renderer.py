"""Render the KB's personalized_response_template into concrete sentences.

Each label in the knowledge base carries a template with {placeholders}, e.g.

    "Your overall utilization is {overall_utilization_pct}%
     (₹{total_balance_inr} of ₹{total_limit_inr})..."

This module fills those placeholders from the FactSet and the customer record.

Two things make it more than a str.format() call:

1. Placeholders are label-scoped. {balance_inr} means a card balance for
   `maxed_out_account` but a collection balance for `disputable_collection`.
   So each label that refers to a specific entity gets its own context builder,
   layered over a base context of profile-wide values.

2. A placeholder with no value must not leak a raw brace into user-facing copy.
   Instead the sentence containing it is dropped, which keeps the surrounding
   paragraph readable.

Money is formatted with Indian digit grouping (₹1,20,000 — not ₹120,000).
"""

import calendar
import re
from datetime import date
from typing import Any, Optional

from app.schemas import FactSet, FiredLabel, KBEntry, SanitisedRecord

# A placeholder token: {name}
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")

# Splits text into sentences while keeping the terminator attached, so a dropped
# sentence does not take its neighbour's full stop with it.
#
# A terminator only counts when followed by whitespace or end-of-string. That
# keeps intra-word periods intact — "cibil.com" and "0.30" must not be treated
# as sentence boundaries.
_SENTENCE_RE = re.compile(r".+?(?:[.!?]+(?=\s|$)|$)", re.DOTALL)

# CIBIL's optimal utilisation ceiling. Paydown targets are computed against it.
TARGET_UTILIZATION = 0.30


# ------------------------------------------------------------- formatting ----


def format_indian_digits(value: int) -> str:
    """Group digits in the Indian convention: 120000 -> '1,20,000'.

    The last three digits form one group, then digits are grouped in pairs.
    """
    negative = value < 0
    digits = str(abs(int(value)))

    if len(digits) <= 3:
        grouped = digits
    else:
        head, tail = digits[:-3], digits[-3:]
        parts: list[str] = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        grouped = ",".join(parts + [tail])

    return ("-" if negative else "") + grouped


def format_inr(paise: int) -> str:
    """Format a paise amount as grouped rupees, without the ₹ sign.

    Templates already include the ₹ glyph, so this returns digits only.
    """
    return format_indian_digits(int(paise) // 100)


def format_pct(ratio: float) -> str:
    """Format a 0-1 ratio as a whole-number percentage."""
    return str(int(round(ratio * 100)))


def format_period(period: Optional[str]) -> Optional[str]:
    """Turn a "YYYY-MM" period into "June 2026"."""
    if not period:
        return None
    try:
        year_str, month_str = period.split("-")
        return f"{calendar.month_name[int(month_str)]} {year_str}"
    except (ValueError, IndexError, KeyError):
        return period


def format_date(value: Optional[date]) -> Optional[str]:
    """Turn a date into "March 2024"."""
    if value is None:
        return None
    return f"{calendar.month_name[value.month]} {value.year}"


# --------------------------------------------------------- entity pickers ----


def _revolving(record: SanitisedRecord) -> list:
    return [acc for acc in record.accounts if acc.is_revolving]


def _account_util(account) -> float:
    if account.is_revolving and account.credit_limit_paise:
        return account.balance_paise / account.credit_limit_paise
    return 0.0


def _top_card(record: SanitisedRecord):
    """The revolving account carrying the highest utilisation."""
    cards = [acc for acc in _revolving(record) if acc.credit_limit_paise]
    if not cards:
        return None
    return max(cards, key=_account_util)


def _account_by_id(record: SanitisedRecord, account_id: Optional[str]):
    if not account_id:
        return None
    return next((acc for acc in record.accounts if acc.account_id == account_id), None)


def _worst_account_at_least(record: SanitisedRecord, threshold: int):
    """The account whose payment history contains the highest status >= threshold.

    Ties break toward the most recent occurrence, which is the one a customer
    will recognise.
    """
    best = None
    best_key = None
    for acc in record.accounts:
        history = acc.payment_history
        for idx, status in enumerate(history):
            if status >= threshold:
                key = (status, idx)
                if best_key is None or key > best_key:
                    best_key = key
                    best = acc
    return best


def _most_recent_late_account(record: SanitisedRecord):
    """The account with the latest-occurring late payment."""
    best = None
    best_months_back = None
    for acc in record.accounts:
        history = acc.payment_history
        for idx in range(len(history) - 1, -1, -1):
            if history[idx] > 0:
                months_back = (len(history) - 1) - idx
                if best_months_back is None or months_back < best_months_back:
                    best_months_back = months_back
                    best = acc
                break
    return best


def _oldest_unused_card(record: SanitisedRecord, facts: FactSet):
    """The longest-held revolving card with a zero balance."""
    unused = [
        acc for acc in _revolving(record)
        if acc.balance_paise == 0 and acc.credit_limit_paise
    ]
    if not unused:
        return None
    return min(unused, key=lambda acc: acc.opened_date)


def _pick_collection(record: SanitisedRecord, **flags):
    """First collection matching all given attribute values."""
    for col in record.collections:
        if all(getattr(col, key, None) == value for key, value in flags.items()):
            return col
    return None


# ---------------------------------------------------------------- context ----


def _base_context(facts: FactSet, record: SanitisedRecord) -> dict[str, Any]:
    """Placeholders that describe the profile as a whole."""
    top = _top_card(record)

    # What must be repaid to bring overall utilisation down to 30%.
    paydown_paise = max(
        0,
        int(facts.total_balance_paise - TARGET_UTILIZATION * facts.total_credit_limit_paise),
    )

    context: dict[str, Any] = {
        # Utilisation
        "overall_utilization_pct": format_pct(facts.overall_utilization),
        "total_balance_inr": format_inr(facts.total_balance_paise),
        "total_limit_inr": format_inr(facts.total_credit_limit_paise),
        "paydown_inr": format_inr(paydown_paise),
        "concentration_ratio": f"{facts.utilization_concentration:.2f}",
        "share_pct": format_pct(facts.single_card_limit_share),
        "n_cards": str(facts.n_revolving_accounts),
        "n_unused": str(facts.n_unused_revolving_cards),
        # Payment history
        "on_time_pct": format_pct(facts.pct_payments_on_time),
        # Score
        "score": str(facts.score),
        "current": str(facts.score),
        "band": facts.score_band.value,
        "prev_3mo": str(facts.previous_score_3mo) if facts.previous_score_3mo else None,
        "drop_points": str(abs(facts.score_change_3mo)) if facts.score_change_3mo < 0 else None,
        "rise_points": str(facts.score_change_3mo) if facts.score_change_3mo > 0 else None,
        "abs_change": str(abs(facts.score_change_3mo)),
        # Inquiries and new accounts
        "n_inquiries": str(facts.n_hard_inquiries_6mo),
        "n_new": str(facts.n_accounts_opened_6mo),
        # Age
        "oldest_months": str(facts.oldest_account_months),
        # DTI
        "dti_pct": format_pct(facts.dti_ratio),
        # Data quality
        "staleness_days": str(facts.freshness_days),
    }

    if top is not None:
        top_util = _account_util(top)
        context.update(
            {
                "top_card_name": top.display_name,
                "top_card_util_pct": format_pct(top_util),
                "target_inr": format_inr(int(TARGET_UTILIZATION * (top.credit_limit_paise or 0))),
                "target_balance_inr": format_inr(
                    int(TARGET_UTILIZATION * (top.credit_limit_paise or 0))
                ),
            }
        )

    return context


def _card_context(account) -> dict[str, Any]:
    """Placeholders describing one specific card."""
    if account is None:
        return {}
    limit = account.credit_limit_paise or 0
    return {
        "card_name": account.display_name,
        "account_name": account.display_name,
        "creditor": account.display_name,
        "util_pct": format_pct(_account_util(account)),
        "balance_inr": format_inr(account.balance_paise),
        "limit_inr": format_inr(limit),
        "target_inr": format_inr(int(TARGET_UTILIZATION * limit)),
        "target_balance_inr": format_inr(int(TARGET_UTILIZATION * limit)),
    }


def _delinquency_context(account, facts: FactSet) -> dict[str, Any]:
    """Placeholders describing a late payment on a specific account."""
    if account is None:
        return {}
    period = facts.account_last_late_period.get(account.account_id)
    formatted = format_period(period)
    return {
        "account_name": account.display_name,
        "creditor": account.display_name,
        "late_date": formatted,
        "late_month": formatted,
    }


def _collection_context(collection) -> dict[str, Any]:
    """Placeholders describing a specific collection."""
    if collection is None:
        return {}
    return {
        "original_creditor": collection.original_creditor,
        "balance_inr": format_inr(collection.balance_paise),
        "opened_date": format_date(collection.opened_date),
    }


def _label_context(
    label_id: str,
    facts: FactSet,
    record: SanitisedRecord,
    fired: Optional[FiredLabel],
) -> dict[str, Any]:
    """Context specific to the entity a label is talking about."""
    if label_id == "maxed_out_account":
        # This label is expanded per account, so the id comes from the rule engine.
        account = _account_by_id(record, fired.account_id if fired else None)
        return _card_context(account or _top_card(record))

    if label_id == "major_delinquency":
        return _delinquency_context(_worst_account_at_least(record, 3), facts)

    if label_id == "serious_delinquency":
        return _delinquency_context(_worst_account_at_least(record, 2), facts)

    if label_id == "recent_late_payment":
        return _delinquency_context(_most_recent_late_account(record), facts)

    if label_id == "oldest_card_at_risk":
        account = _oldest_unused_card(record, facts)
        if account is None:
            return {}
        months = facts.account_months_on_book.get(account.account_id, 0)
        return {
            "card_name": account.display_name,
            "age_years": str(int(months // 12)),
        }

    if label_id == "disputable_collection":
        return _collection_context(_pick_collection(record, is_disputable=True))

    if label_id == "collection_past_sol":
        return _collection_context(_pick_collection(record, is_past_sol=True))

    if label_id == "paid_collection_still_reporting":
        collection = _pick_collection(record, status="paid") or (
            record.collections[0] if record.collections else None
        )
        return _collection_context(collection)

    return {}


# ----------------------------------------------------------------- render ----


def render_template(
    entry: KBEntry,
    facts: FactSet,
    record: SanitisedRecord,
    fired: Optional[FiredLabel] = None,
) -> str:
    """Fill a label's template for this customer.

    Sentences whose placeholders cannot be resolved are omitted, so the result
    never contains a raw {placeholder}.
    """
    context = _base_context(facts, record)
    context.update(_label_context(entry.label_id, facts, record, fired))

    return _fill(entry.personalized_response_template, context)


def render_steps(
    entry: KBEntry,
    facts: FactSet,
    record: SanitisedRecord,
    fired: Optional[FiredLabel] = None,
) -> list[str]:
    """Fill placeholders in a label's mitigation steps.

    Only one step in the KB carries a placeholder, but steps are rendered
    through the same path so a future authored placeholder cannot leak.
    """
    context = _base_context(facts, record)
    context.update(_label_context(entry.label_id, facts, record, fired))

    return [_fill(step, context) for step in entry.mitigation_steps]


def _fill(text: str, context: dict[str, Any]) -> str:
    """Substitute placeholders, dropping sentences that cannot be completed."""
    if not text or "{" not in text:
        return text

    kept: list[str] = []
    for sentence in _SENTENCE_RE.findall(text):
        names = _PLACEHOLDER_RE.findall(sentence)
        if any(context.get(name) is None for name in names):
            # Unresolvable: drop the whole sentence rather than emit a brace.
            continue
        kept.append(
            _PLACEHOLDER_RE.sub(lambda m: str(context[m.group(1)]), sentence)
        )

    return " ".join(part.strip() for part in kept if part.strip())


def unresolved_placeholders(text: str) -> list[str]:
    """Any placeholder names left in a rendered string. Should always be empty."""
    return _PLACEHOLDER_RE.findall(text)
