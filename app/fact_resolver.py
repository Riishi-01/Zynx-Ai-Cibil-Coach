"""Fact resolution — bridge the KB's fact vocabulary to FactSet field names.

Frontend_docs/label_kb.json was authored against a fact namespace that does not
match FactSet field-for-field. Its `facts_to_cite` arrays reference names like
`n_late_30d` and `oldest_account_years`, where FactSet exposes
`n_lates_30_24mo` and `oldest_account_months`.

Rather than rewrite either side, this module maps between them:

  ALIASES  — a KB name that is simply a different spelling of a FactSet field.
  DERIVED  — a KB name that is a pure function of one or more FactSet fields
             (unit conversions and boolean projections).

Everything else is expected to exist on FactSet directly. resolve_fact() is the
single entry point, so the citation layer, template renderer, and labels API all
resolve names the same way.
"""

from typing import Any, Callable

from app.schemas import FactSet


class UnknownFact(KeyError):
    """A fact name could not be resolved against FactSet."""


# KB name -> FactSet field name. Pure renames only.
ALIASES: dict[str, str] = {
    "n_late_30d": "n_lates_30_24mo",
    "n_late_60d": "n_lates_60_24mo",
    "n_late_90d_plus": "n_lates_90_24mo",
    "monthly_income_paise": "income_monthly_paise",
    "total_monthly_debt_paise": "total_monthly_obligations_paise",
    "max_single_card_limit_share": "single_card_limit_share",
    "n_open_collections": "n_collections",
}

# KB name -> function of the FactSet. Unit conversions and projections.
DERIVED: dict[str, Callable[[FactSet], Any]] = {
    # The KB talks in years; FactSet stores months.
    "oldest_account_years": lambda f: f.oldest_account_months / 12.0,
    # The KB asks a yes/no question; FactSet holds the count.
    "has_collections_past_sol": lambda f: f.n_collections_past_sol > 0,
}


def resolve_fact(facts: FactSet, name: str) -> Any:
    """Resolve a KB fact name to its value on this FactSet.

    Raises UnknownFact if the name maps to nothing, so a typo in the KB surfaces
    as a test failure rather than a silently missing citation.
    """
    if name in DERIVED:
        return DERIVED[name](facts)

    field = ALIASES.get(name, name)
    if hasattr(facts, field):
        return getattr(facts, field)

    raise UnknownFact(
        f"Fact '{name}' does not resolve to a FactSet field "
        f"(tried '{field}', no alias or derivation registered)"
    )


def resolve_facts(facts: FactSet, names: list[str]) -> dict[str, Any]:
    """Resolve a list of fact names, preserving order. Skips unknown names.

    Used by the API layer, where one bad name should not fail the whole request.
    Use resolve_fact() directly when a missing fact should be an error.
    """
    out: dict[str, Any] = {}
    for name in names:
        try:
            out[name] = resolve_fact(facts, name)
        except UnknownFact:
            continue
    return out


def known_fact_names(facts: FactSet) -> set[str]:
    """Every name resolve_fact() accepts, for diagnostics and tests."""
    return set(FactSet.model_fields) | set(ALIASES) | set(DERIVED)
