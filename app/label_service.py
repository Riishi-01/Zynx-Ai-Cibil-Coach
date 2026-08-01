"""Label diagnostic service — join fired labels to knowledge base content.

The pipeline is entirely deterministic:

    fetch by PAN -> sanitise -> precompute facts -> fire_labels -> join KB

No LLM is involved, so this endpoint is fast (~25ms) and its output is stable
for a given (customer, as_of_date, income).

The rule engine is used as-is. Where RULE_TABLE fires overlapping utilisation
tiers (maxed_out, very_high_utilization and high_utilization all fire above
90%), that is resolved here in presentation only, by ordering on priority_rank
and bucketing by severity.
"""

from typing import Optional

from app.api_schemas import LabelInstance, LabelsResponse, LabelView, SourceView
from app.data_fetch import fetch_customer_by_pan
from app.fact_resolver import resolve_facts
from app.kb_loader import get_knowledge_base
from app.pii_parser import sanitise_record
from app.precompute import precompute_facts
from app.rule_engine import fire_labels
from app.schemas import CustomerRecord, FactSet, FiredLabel, SanitisedRecord
from app.template_renderer import render_steps, render_template

# Severity buckets, most to least urgent. Fixed order so the UI renders
# consistently rather than depending on dict insertion order.
SEVERITY_ORDER = ["critical", "warning", "info", "ok", "excellent"]


def run_pipeline(
    pan_card: str, monthly_income_inr: Optional[int] = None
) -> tuple[CustomerRecord, SanitisedRecord, FactSet, list[FiredLabel], str]:
    """Run fetch -> sanitise -> precompute -> fire_labels for one PAN.

    Shared by the labels, canvas and plan endpoints so they cannot drift apart.

    Returns ``(record, sanitised, facts, fired, first_name)`` where
    ``first_name`` is the customer-facing name from the canonical record.
    It is exposed here so the frontend dock can show the un-redacted name
    alongside the masked PAN — callers must never forward ``first_name``
    into a prompt or localStorage key.

    If monthly_income_inr is omitted, the customer's stored income is used.
    """
    record = fetch_customer_by_pan(pan_card)

    if monthly_income_inr is None:
        monthly_income_inr = record.customer.income_monthly_paise // 100

    sanitised = sanitise_record(record)
    facts = precompute_facts(sanitised, monthly_income_inr=monthly_income_inr)
    fired = fire_labels(facts)
    first_name = record.customer.first_name or ""

    return record, sanitised, facts, fired, first_name


def _account_name(record: SanitisedRecord, account_id: Optional[str]) -> Optional[str]:
    if not account_id:
        return None
    account = next((a for a in record.accounts if a.account_id == account_id), None)
    return account.display_name if account else None


def build_labels_response(
    pan_card: str, monthly_income_inr: Optional[int] = None
) -> LabelsResponse:
    """Build the full 32-label diagnostic for a customer."""
    _record, sanitised, facts, fired, _first_name = run_pipeline(pan_card, monthly_income_inr)
    return labels_response_from(sanitised, facts, fired)


def labels_response_from(
    sanitised: SanitisedRecord, facts: FactSet, fired: list[FiredLabel]
) -> LabelsResponse:
    """Build the label diagnostic from an already-run pipeline.

    Exposed so callers that need several views of the same customer (the canvas
    payload, the streaming plan) can run the pipeline once and reuse it.
    """
    kb = get_knowledge_base()

    # Group firings by label so per-account expansions stay together.
    firings: dict[str, list[FiredLabel]] = {}
    for label in fired:
        firings.setdefault(label.label_id, []).append(label)

    views: list[LabelView] = []

    # all_entries() is ordered by priority_rank, so the response is too.
    for entry in kb.all_entries():
        label_firings = firings.get(entry.label_id, [])

        instances = [
            LabelInstance(
                account_id=firing.account_id,
                account_name=_account_name(sanitised, firing.account_id),
                message=render_template(entry, facts, sanitised, firing),
                mitigation_steps=render_steps(entry, facts, sanitised, firing),
            )
            for firing in label_firings
        ]

        views.append(
            LabelView(
                label_id=entry.label_id,
                display_name=entry.display_name,
                category=entry.category,
                severity=entry.severity,
                priority_rank=entry.priority_rank,
                fired=bool(label_firings),
                condition_human=entry.condition_human,
                what_it_means_cibil=entry.what_it_means_cibil,
                why_it_matters=entry.why_it_matters,
                instances=instances,
                # Resolved for every label, fired or not, so the UI can explain
                # why an inactive check did not trigger.
                facts_to_cite=resolve_facts(facts, entry.facts_to_cite),
                cibil_reason_codes=list(entry.cibil_reason_codes),
                sources=[SourceView(title=s.title, url=s.url) for s in entry.sources],
            )
        )

    fired_by_severity: dict[str, list[str]] = {sev: [] for sev in SEVERITY_ORDER}
    for view in views:
        if view.fired:
            fired_by_severity.setdefault(view.severity.value, []).append(view.label_id)

    return LabelsResponse(
        pan_masked=sanitised.pan_masked,
        customer_id=sanitised.customer_id,
        score=facts.score,
        score_band=facts.score_band,
        as_of_date=facts.as_of_date,
        total_labels=len(views),
        n_fired=sum(1 for v in views if v.fired),
        labels=views,
        fired_by_severity=fired_by_severity,
    )
