"""End-to-end Maya test: Anjali (PAN ABCPS1234A) at ₹1,00,000/month.

Exercises the full pipeline → real LLM (gpt-4o-mini) → JSON plan → markdown
render. Validates the output against Maya's role expectations and reports
issues + suggested fixes.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.label_service import run_pipeline
from app.llm_stream import build_model
from app.prompt_builder import (
    CHAT_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    CoachPlan,
    build_chat_prompt,
    build_prompt,
)
from app.web import astream_plan  # noqa: F401  — proves the import path works
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser


def render_markdown(plan: dict) -> str:
    """Render the plan as a Markdown document — mirrors what the frontend
    MarkdownRenderer would produce. LaTeX is normalised like `lib/latex.ts`.
    """
    def normalize_latex(s: str) -> str:
        return s.replace("\\(", "$").replace("\\)", "$").replace("\\[", "$$").replace("\\]", "$$")

    out: list[str] = []
    situation = plan.get("current_situation", "")
    out.append(normalize_latex(situation))
    out.append("")
    out.append("**Top actions (in priority order):**")
    out.append("")
    for i, action in enumerate(plan.get("top_actions", []), 1):
        out.append(f"{i}. **{action.get('title', '?')}**")
        out.append(f"   - Why: {normalize_latex(action.get('why', '?'))}")
        out.append("   - Steps:")
        for step in action.get("steps", []):
            out.append(f"     - {normalize_latex(step)}")
        out.append(f"   - When you'll see results: {action.get('when_youll_see_results', '?')}")
        out.append("")
    out.append("**What to avoid:**")
    for item in plan.get("what_to_avoid", []):
        out.append(f"- {normalize_latex(item)}")
    out.append("")
    out.append(f"**Follow-up:** {normalize_latex(plan.get('follow_up_question', '?'))}")
    return "\n".join(out)


def validate_maya(plan: dict, facts, sanitised) -> list[str]:
    """Apply Maya's role + scope + framework rules to the model's output.
    Returns a list of issues (empty = pass)."""
    issues: list[str] = []

    # 1. Scope redirect: must not advise on investments / career / housing / tax / discretionary.
    forbidden_topics = ["invest", "mutual fund", "sip", "stock", "career", "salary hike",
                        "rent vs buy", "housing loan alternative", "tax saving"]
    flat = json.dumps(plan, ensure_ascii=False).lower()
    for topic in forbidden_topics:
        if topic in flat:
            issues.append(f"OUT-OF-SCOPE: mentions '{topic}'")

    # 2. Banned actions: must not recommend any of the 7 forbidden moves.
    banned_phrases = [
        ("cash withdrawal from credit card", "Cash withdrawal from credit card"),
        ("cash advance", "Cash withdrawal from credit card"),
        ("close your oldest card", "Closing the oldest credit card"),
        ("closing your oldest card", "Closing the oldest credit card"),
        ("pay the collection past", "Paying collection past 7y FCRA window"),
        ("consolidation loan", "New debt to pay old debt"),
        ("payday loan", "New debt to pay old debt"),
        ("balance transfer card", "Balance transfer card"),
        ("balance-transfer card", "Balance transfer card"),
    ]
    for needle, label in banned_phrases:
        if needle in flat:
            issues.append(f"BANNED ACTION: model recommended '{label}'")

    # 3. Disputable collection: if `disputable_collection` label fires AND
    # the action sequence is correct, the plan should mention dispute-in-writing.
    fired_ids = {label.label_id for label in _last_fired}
    if "disputable_collection" in fired_ids:
        if "dispute" not in flat or "written" not in flat:
            issues.append("MISSING LABEL ADAPTATION: Disputable Collection fired but no written-dispute guidance")

    # 4. Score falling: if `score_falling` label fires, plan should reference trend reversal.
    if "score_falling" in fired_ids:
        # Accept any of: "trend", "falling", "revers", "drop", "fell", "recover"
        trend_words = ["trend", "falling", "revers", "drop", "fell", "recover"]
        if not any(word in flat for word in trend_words):
            issues.append("MISSING LABEL ADAPTATION: Score Falling fired but trend reversal not mentioned")

    # 5. Citation discipline: every rupee amount in the plan should match a
    # fact or a precomputed slot value. Build the citable set from the
    # same logic the prompt builder uses.
    import re

    TARGET_UTILIZATION = 0.30
    citable_rupees: set[int] = set()
    citable_rupees.add(facts.income_monthly_paise // 100)
    citable_rupees.add(facts.total_balance_paise // 100)
    citable_rupees.add(facts.total_credit_limit_paise // 100)
    citable_rupees.add(int(TARGET_UTILIZATION * facts.total_credit_limit_paise) // 100)
    for a in sanitised.accounts:
        citable_rupees.add(a.balance_paise // 100)
        if a.credit_limit_paise is not None:
            citable_rupees.add(a.credit_limit_paise // 100)
        if a.is_revolving and a.credit_limit_paise:
            target = int(TARGET_UTILIZATION * a.credit_limit_paise)
            paydown = max(0, a.balance_paise - target)
            citable_rupees.add(target // 100)
            citable_rupees.add(paydown // 100)
    for c in sanitised.collections:
        citable_rupees.add(c.balance_paise // 100)
    # Disposable + cap slot values.
    essentials = int(0.50 * facts.income_monthly_paise)
    min_payments = sum(a.monthly_payment_paise for a in sanitised.accounts)
    disposable = facts.income_monthly_paise - essentials - min_payments
    seventy_pct_cap = int(0.70 * facts.income_monthly_paise) - essentials - min_payments
    if disposable > 0:
        citable_rupees.add(disposable // 100)
    if seventy_pct_cap > 0:
        citable_rupees.add(seventy_pct_cap // 100)
    citable_rupees.add(essentials // 100)
    citable_rupees.add(min_payments // 100)

    amount_re = re.compile(r"₹\s?([\d,]+)")
    for match in amount_re.finditer(flat):
        amount = int(match.group(1).replace(",", ""))
        if amount >= 100 and amount not in citable_rupees:
            issues.append(f"UNCITED AMOUNT: ₹{amount:,} appears in the plan but is not in the supplied facts")

    # 6. Persona: should not say "I am an AI" or "as a language model".
    for phrase in ("as an ai", "as a language model", "i'm just an ai"):
        if phrase in flat:
            issues.append(f"PERSONA LEAK: '{phrase}' breaks Maya's voice")

    # 6b. First-name usage: Maya should open current_situation with the
    # customer's first name when one was supplied. The 'Hi Anjali.' opening is
    # the canonical Maya format from her prompt's output spec.
    first_name = getattr(sanitised, "first_name_opt", None)
    if first_name:
        opening = plan.get("current_situation", "")
        if first_name.lower() not in opening.lower():
            issues.append(f"FIRST NAME: supplied '{first_name}' but current_situation does not use it")

    # 7. Word count: target 300–400. Allow ±100 for JSON overhead.
    word_count = len(flat.split())
    if word_count < 200:
        issues.append(f"WORD COUNT: only {word_count} words (target 300-400)")
    elif word_count > 600:
        issues.append(f"WORD COUNT: {word_count} words (target 300-400, too long)")

    return issues


async def call_llm(system_prompt: str, user_message: str) -> dict:
    """Invoke gpt-4o-mini with JSON mode. Returns the parsed plan dict."""
    model = build_model(json_mode=True)
    parser = JsonOutputParser()
    chain = model | parser

    final = None
    async for partial in chain.astream(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    ):
        if isinstance(partial, dict):
            final = partial
    return final


_last_fired: list = []


async def main() -> int:
    pan, income = "ABCPS1234A", 100000
    record, sanitised, facts, fired = run_pipeline(pan, income)
    global _last_fired
    _last_fired = fired

    print("=" * 72)
    print(f"END-TO-END MAYA TEST — Anjali (PAN {pan}), ₹{income:,}/month")
    print("=" * 72)
    print()
    print(f"Score: {facts.score} ({facts.score_band.value})")
    print(f"Overall utilization: {facts.overall_utilization:.0%}")
    print(f"DTI: {facts.dti_ratio:.0%} ({facts.dti_category})")
    print(f"Fired labels: {[label.label_id for label in fired]}")
    print()
    print("Calling gpt-4o-mini …")
    sys_prompt, user_msg = build_prompt(sanitised, facts, fired)
    plan = await call_llm(sys_prompt, user_msg)

    print()
    print("=" * 72)
    print("RAW LLM OUTPUT (parsed JSON)")
    print("=" * 72)
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    # Schema check
    print()
    print("=" * 72)
    print("SCHEMA VALIDATION")
    print("=" * 72)
    try:
        CoachPlan.model_validate(plan)
        print("PASS: Plan matches CoachPlan schema")
    except Exception as exc:
        print(f"FAIL: {exc}")

    # Role check
    print()
    print("=" * 72)
    print("MAYA ROLE VALIDATION")
    print("=" * 72)
    issues = validate_maya(plan, facts, sanitised)
    if not issues:
        print("PASS: All Maya rules satisfied")
    else:
        for issue in issues:
            print(f"  - {issue}")

    # Markdown render
    print()
    print("=" * 72)
    print("RENDERED MARKDOWN")
    print("=" * 72)
    md = render_markdown(plan)
    print(md)

    print()
    print("=" * 72)
    print("WORD COUNT")
    print("=" * 72)
    print(f"  Plan text: {len(json.dumps(plan, ensure_ascii=False).split())} words")
    print(f"  Markdown render: {len(md.split())} words")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
