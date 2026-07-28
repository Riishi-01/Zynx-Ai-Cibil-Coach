"""Citation generation — trace figures in the plan back to precomputed facts.

Rebuilt on app.fact_resolver so a citation always names a fact that actually
exists. The previous implementation compared against a small hardcoded dict of
formatted strings, which meant most numbers went uncited and the fact ids it did
emit were not guaranteed to resolve.

Approach: build an index of every citable fact's rendered forms (raw integer,
Indian-grouped rupees, percentage), then look up the numeric tokens appearing in
the model's output. Only exact matches are cited, so a citation is evidence
rather than a guess.
"""

import re
from typing import Any, Iterable, Optional

from app.fact_resolver import UnknownFact, resolve_fact
from app.kb_loader import get_knowledge_base
from app.schemas import Citation, FactSet, FiredLabel
from app.template_renderer import format_indian_digits

# Numbers as they appear in prose: 96, 96.5, 1,20,000, ₹38,500.
_NUMBER_RE = re.compile(r"₹?\s?(\d+(?:,\d{2,3})*(?:\.\d+)?)")

# Small integers are almost always prose ("2-3 steps", "1-2 billing cycles")
# rather than profile figures, and they collide with many facts. Requiring a
# minimum magnitude keeps citations meaningful.
MIN_CITABLE_VALUE = 10

# A token matching more than this many facts is ambiguous and tells the reader
# nothing, so it is not cited.
MAX_AMBIGUITY = 2

# Facts worth citing. Internal bookkeeping fields are excluded.
_CITABLE_FACTS = [
    "score",
    "previous_score_1mo",
    "previous_score_3mo",
    "score_change_3mo",
    "overall_utilization",
    "max_single_card_utilization",
    "total_balance_paise",
    "total_credit_limit_paise",
    "dti_ratio",
    "income_monthly_paise",
    "total_monthly_obligations_paise",
    "n_hard_inquiries_6mo",
    "n_hard_inquiries_12mo",
    "n_collections",
    "total_collections_balance_paise",
    "oldest_account_months",
    "n_revolving_accounts",
    "n_installment_accounts",
    "n_lates_30_24mo",
    "n_lates_60_24mo",
    "n_lates_90_24mo",
    "worst_late_status",
    "pct_payments_on_time",
    "n_accounts_over_90pct",
    "n_unused_revolving_cards",
]


def _rendered_forms(value: Any) -> set[str]:
    """Every string form a fact value might plausibly appear as."""
    forms: set[str] = set()

    if isinstance(value, bool) or value is None:
        return forms

    if isinstance(value, int):
        forms.add(str(value))
        forms.add(format_indian_digits(value))
        # Paise amounts are quoted in rupees.
        if value >= 100:
            forms.add(str(value // 100))
            forms.add(format_indian_digits(value // 100))
    elif isinstance(value, float):
        # Ratios are quoted as percentages.
        forms.add(str(int(round(value * 100))))
        forms.add(f"{value * 100:.1f}")

    return forms


def _build_index(facts: FactSet) -> dict[str, list[str]]:
    """Map each rendered form to the fact ids that produce it."""
    index: dict[str, list[str]] = {}

    for name in _CITABLE_FACTS:
        try:
            value = resolve_fact(facts, name)
        except UnknownFact:
            continue

        for form in _rendered_forms(value):
            index.setdefault(form, []).append(name)

    return index


def _reason_codes(fired_labels: Iterable[FiredLabel]) -> list[str]:
    """CIBIL reason codes across the fired labels, de-duplicated in order."""
    kb = get_knowledge_base()
    codes: list[str] = []
    for label in fired_labels:
        entry = kb.get(label.label_id)
        if entry is None:
            continue
        for code in entry.cibil_reason_codes:
            if code not in codes:
                codes.append(code)
    return codes


def generate_citations(
    text: str,
    facts: FactSet,
    fired_labels: list[FiredLabel],
) -> list[Citation]:
    """Cite the numeric claims in a block of generated text.

    Returns one Citation per distinct grounded figure found.
    """
    index = _build_index(facts)
    codes = _reason_codes(fired_labels)

    citations: list[Citation] = []
    seen: set[str] = set()

    for match in _NUMBER_RE.finditer(text):
        token = match.group(1)
        if token in seen:
            continue

        # Discard prose numerals before looking anything up.
        try:
            magnitude = float(token.replace(",", ""))
        except ValueError:
            continue
        if magnitude < MIN_CITABLE_VALUE:
            continue

        fact_ids = index.get(token)
        if not fact_ids or len(fact_ids) > MAX_AMBIGUITY:
            continue

        seen.add(token)
        citations.append(
            Citation(
                claim=match.group(0).strip(),
                sources=codes,
                fact_ids=fact_ids,
            )
        )

    return citations


def cite_plan(
    plan: dict,
    facts: FactSet,
    fired_labels: list[FiredLabel],
) -> list[Citation]:
    """Cite the figures across every text field of a CoachPlan."""
    fragments: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            fragments.append(value)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)

    collect(plan)
    return generate_citations("\n".join(fragments), facts, fired_labels)
