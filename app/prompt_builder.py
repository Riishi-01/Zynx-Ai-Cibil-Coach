"""Build the LLM prompt and the structured coaching plan schema.

The model no longer returns prose. It returns a CoachPlan object, which the
frontend renders as discrete sections that fill in progressively as the JSON
streams. The structure follows frontend-charts-spec.md Part 4 (§15-19):
a situation summary, prioritised actions each with its own "when you'll see
results" horizon, what to avoid, and a follow-up question.

Grounding rules live in the system prompt. Every number the model is allowed to
use is supplied in the user message, precomputed and already formatted, so the
model never has to do arithmetic.
"""

from typing import Optional

from pydantic import BaseModel, Field

from app.kb_loader import get_knowledge_base
from app.schemas import FactSet, FiredLabel, SanitisedRecord
from app.template_renderer import (
    format_indian_digits,
    format_pct,
    render_steps,
    render_template,
)


# ============================================================================
# STRUCTURED OUTPUT SCHEMA
# ============================================================================


class CoachAction(BaseModel):
    """One prioritised action in the plan."""

    title: str = Field(description="Short imperative headline, under 60 characters")
    why: str = Field(description="Why this matters, citing the customer's own numbers")
    steps: list[str] = Field(description="2-4 concrete steps, in order")
    when_youll_see_results: str = Field(
        description="Realistic horizon, e.g. '1-2 billing cycles' or '30-60 days'"
    )


class CoachPlan(BaseModel):
    """The complete coaching plan for one customer."""

    current_situation: str = Field(
        description="2-3 sentences summarising where the customer stands today"
    )
    top_actions: list[CoachAction] = Field(
        description="Up to 3 actions, highest leverage first"
    )
    what_to_avoid: list[str] = Field(
        description="2-3 mistakes that would make things worse"
    )
    follow_up_question: str = Field(
        description="One question inviting the customer to go deeper"
    )


# ============================================================================
# PROMPTS
# ============================================================================

# Formatting rules follow Frontend_docs/SPEC.md §4.1. The frontend renders these
# fields through react-markdown with remark-math and rehype-katex.
_FORMATTING_RULES = """\
FORMATTING (these fields are rendered as markdown):
  - Use $..$ for inline math and $$..$$ on its own lines for block math.
  - NEVER wrap LaTeX in code fences.
  - Use - for unordered lists and 1. for ordered lists.
  - Use pipe tables only when comparing 2+ items across 2+ dimensions.
  - Use ``` for code only, never for math.
  - No headings inside these fields; the UI supplies its own section headers.\
"""

SYSTEM_PROMPT = f"""\
You are a senior credit analyst at an Indian fintech, coaching a customer on \
their CIBIL credit report. You explain clearly, cite the customer's own \
numbers, and never waffle.

GROUNDING (this is the hard constraint):
  - Use ONLY the figures supplied in the user message. Never invent, estimate, \
or recompute a number.
  - Every claim about the customer's profile must trace to a supplied fact.
  - If a figure you want is not supplied, describe the situation qualitatively \
instead of guessing.
  - If you are uncertain, say so rather than fabricating.

INDIAN CONTEXT:
  - CIBIL scores run 300-900. Never reference FICO or US bureaus.
  - Format money as ₹ with Indian digit grouping: ₹1,20,000 (not ₹120,000).
  - Refer to CIBIL, Experian, Equifax and CRIF High Mark as the four bureaus.
  - DTI is also called FOIR in Indian lending.

PRIORITISATION:
  - Lead with the single highest-leverage action, which is usually the one \
affecting utilisation or a delinquency.
  - Give each action a realistic horizon: paydowns show up in 1-2 billing \
cycles, disputes take 30-90 days, late payments fade over 6-12 months.
  - Be concrete. "Pay ₹13,500 on your Kotak card" beats "reduce your balances".

{_FORMATTING_RULES}

Return a JSON object matching the requested schema. No prose outside the JSON.\
"""

# Follow-up chat streams markdown text rather than JSON, so it gets its own
# system prompt with the same grounding and formatting rules.
CHAT_SYSTEM_PROMPT = f"""\
You are a senior credit analyst at an Indian fintech, answering follow-up \
questions about a customer's CIBIL credit report.

You have already given the customer their analysis. Answer their question \
directly and concisely, grounded in the profile facts supplied below.

GROUNDING:
  - Use ONLY the supplied figures. Never invent or recompute a number.
  - If the question needs a figure you do not have, say what you would need.

INDIAN CONTEXT:
  - CIBIL scores run 300-900. Never reference FICO or US bureaus.
  - Format money as ₹ with Indian digit grouping: ₹1,20,000.

{_FORMATTING_RULES}
  - Use ## for section headers when the answer has multiple parts.\
"""


# ============================================================================
# CONTEXT ASSEMBLY
# ============================================================================


def build_facts_block(facts: FactSet, record: SanitisedRecord) -> str:
    """The precomputed figures the model is permitted to cite.

    Values are pre-formatted so the model never performs arithmetic.
    """
    lines: list[str] = ["## Profile figures (the only numbers you may cite)"]

    lines.append(f"- CIBIL score: {facts.score} ({facts.score_band.value} band)")
    if facts.previous_score_3mo:
        direction = "down" if facts.score_change_3mo < 0 else "up"
        lines.append(
            f"- Score 3 months ago: {facts.previous_score_3mo} "
            f"({direction} {abs(facts.score_change_3mo)} points, trend {facts.score_trend})"
        )

    lines.append(
        f"- Overall card utilisation: {format_pct(facts.overall_utilization)}% "
        f"(₹{format_indian_digits(facts.total_balance_paise // 100)} of "
        f"₹{format_indian_digits(facts.total_credit_limit_paise // 100)})"
    )
    lines.append(
        f"- Monthly income: ₹{format_indian_digits(facts.income_monthly_paise // 100)}; "
        f"DTI/FOIR: {format_pct(facts.dti_ratio)}% ({facts.dti_category})"
    )
    lines.append(
        f"- Accounts: {facts.n_revolving_accounts} revolving, "
        f"{facts.n_installment_accounts} installment; "
        f"oldest is {facts.oldest_account_months} months old"
    )
    lines.append(
        f"- Payment history: {format_pct(facts.pct_payments_on_time)}% of months on time; "
        f"worst status {facts.worst_late_status} (0=clean, 1=30d, 2=60d, 3=90d+)"
    )
    if facts.most_recent_late_period:
        lines.append(f"- Most recent late payment: {facts.most_recent_late_period}")
    lines.append(
        f"- Hard inquiries: {facts.n_hard_inquiries_6mo} in 6 months, "
        f"{facts.n_hard_inquiries_12mo} in 12 months"
    )
    if facts.n_collections:
        lines.append(
            f"- Collections: {facts.n_collections} "
            f"(₹{format_indian_digits(facts.total_collections_balance_paise // 100)} total)"
        )

    if record.accounts:
        lines.append("")
        lines.append("### Per-card detail")
        for account in record.accounts:
            if not account.is_revolving or not account.credit_limit_paise:
                continue
            utilization = facts.account_utilizations.get(account.account_id, 0.0)
            lines.append(
                f"- {account.display_name}: "
                f"₹{format_indian_digits(account.balance_paise // 100)} of "
                f"₹{format_indian_digits(account.credit_limit_paise // 100)} "
                f"({format_pct(utilization)}%)"
            )

    return "\n".join(lines)


def build_findings_block(
    facts: FactSet, record: SanitisedRecord, fired: list[FiredLabel]
) -> str:
    """The fired labels with their knowledge base guidance.

    Each finding carries the KB's rendered message, why it matters, and its
    authored mitigation steps, so the model synthesises rather than invents.
    """
    if not fired:
        return "## Findings\nNo risk labels fired. The profile is healthy; reinforce current habits."

    kb = get_knowledge_base()
    lines: list[str] = ["## Findings (priority 1 = most urgent)"]

    for label in fired:
        entry = kb.get(label.label_id)
        if entry is None:
            continue

        lines.append("")
        lines.append(
            f"### [priority {entry.priority_rank}] {entry.display_name} "
            f"({entry.severity.value})"
        )
        lines.append(f"Finding: {render_template(entry, facts, record, label)}")
        lines.append(f"Why it matters: {entry.why_it_matters}")
        if entry.cibil_reason_codes:
            lines.append(f"CIBIL reason codes: {', '.join(entry.cibil_reason_codes)}")
        lines.append("Recommended steps from the knowledge base:")
        # Steps must be rendered, not passed through: one authored step carries a
        # {target_balance_inr} placeholder that would otherwise reach the model.
        for step in render_steps(entry, facts, record, label):
            lines.append(f"  - {step}")

    return "\n".join(lines)


def build_prompt(
    sanitised_record: SanitisedRecord,
    facts: FactSet,
    fired_labels: list[FiredLabel],
) -> tuple[str, str]:
    """Build (system_prompt, user_message) for the structured plan.

    Signature is unchanged from the previous prose-based implementation so
    existing callers keep working.
    """
    sections = [
        build_facts_block(facts, sanitised_record),
        "",
        build_findings_block(facts, sanitised_record, fired_labels),
        "",
        "## Your task",
        "Produce a coaching plan as JSON with these fields:",
        "- current_situation: 2-3 sentences on where this customer stands.",
        "- top_actions: up to 3 actions, highest leverage first. Each needs a "
        "title, a why citing their numbers, 2-4 steps, and when_youll_see_results.",
        "- what_to_avoid: 2-3 specific mistakes that would set them back.",
        "- follow_up_question: one question inviting them to go deeper.",
        "",
        "Base the actions on the findings above, ordered by priority. Cite the "
        "customer's actual figures throughout.",
    ]

    return SYSTEM_PROMPT, "\n".join(sections)


def build_chat_prompt(
    sanitised_record: SanitisedRecord,
    facts: FactSet,
    fired_labels: list[FiredLabel],
    question: str,
    history: Optional[list[dict]] = None,
) -> tuple[str, str]:
    """Build (system_prompt, user_message) for a follow-up question."""
    sections = [
        build_facts_block(facts, sanitised_record),
        "",
        build_findings_block(facts, sanitised_record, fired_labels),
    ]

    if history:
        sections.append("")
        sections.append("## Conversation so far")
        for turn in history[-6:]:  # Recent turns only, to bound the prompt.
            role = str(turn.get("role", "user")).lower()
            speaker = "Customer" if role == "user" else "You"
            sections.append(f"{speaker}: {turn.get('content', '')}")

    sections.append("")
    sections.append("## The customer's question")
    sections.append(question)

    return CHAT_SYSTEM_PROMPT, "\n".join(sections)
