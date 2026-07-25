"""Build the LLM prompt from facts, fired labels, and KB entries.

This is Phase 8: assembles the exact message list sent to the LLM.
System prompt + user message containing facts, labels, and KB entries.
"""

from app.schemas import FactSet, FiredLabel, SanitisedRecord
from app.kb_loader import get_knowledge_base


SYSTEM_PROMPT = """\
You are a CIBIL Credit Coach for Indian credit profiles.

Your role:
1. Analyze the customer's credit profile using ONLY the provided facts and knowledge base entries.
2. Never invent numbers — all figures must come from the customer's actual data.
3. Use CIBIL terminology and Indian financial context (not FICO/US terms).
4. Format money in INR: Rs.50,000 or lakh notation (Rs.1L for Rs.1,00,000).
5. Provide specific, actionable advice grounded in the customer's actual numbers.

Output structure:
1. Credit score and band (e.g., 715 = Good)
2. What to fix first (most urgent issue)
3. How to fix it (specific actions with timelines)
4. What to avoid (mistakes that worsen the score)

Cite specific facts from the profile. For example:
- "Your utilization is 57% (Rs.4,20,000 of Rs.7,40,000)"
- "You have 3 inquiries in the last 6 months"
- "Your oldest card opened 64 months ago"

Never be generic. Always reference the customer's actual numbers.
"""


def build_prompt(
    sanitised_record: SanitisedRecord,
    facts: FactSet,
    fired_labels: list[FiredLabel],
) -> tuple[str, str]:
    """Build the system and user messages for the LLM.
    
    Returns:
      (system_prompt, user_message)
    """
    kb = get_knowledge_base()
    
    # Build the user message
    user_message_parts = []
    
    # Section 1: Customer summary
    user_message_parts.append("## Customer Profile")
    user_message_parts.append(f"Score: {facts.score} ({facts.score_band.value})")
    user_message_parts.append(f"Income: Rs.{facts.income_monthly_paise // 100:,} / month")
    user_message_parts.append(f"Credit age: {facts.oldest_account_months // 12} years")
    user_message_parts.append("")
    
    # Section 2: Key facts
    user_message_parts.append("## Key Financial Facts")
    user_message_parts.append(f"- Overall utilization: {facts.overall_utilization:.0%}")
    user_message_parts.append(f"- Total revolving balance: Rs.{facts.total_balance_paise // 100:,}")
    user_message_parts.append(f"- Total revolving limit: Rs.{facts.total_credit_limit_paise // 100:,}")
    user_message_parts.append(f"- Accounts: {facts.n_revolving_accounts} revolving + {facts.n_installment_accounts} installment")
    user_message_parts.append(f"- Payment status: {facts.worst_late_status} (0=perfect, 1=30d, 2=60d, 3=90d+)")
    user_message_parts.append(f"- Collections: {facts.n_collections}")
    user_message_parts.append(f"- Inquiries (6mo): {facts.inquiries_6mo}")
    user_message_parts.append(f"- DTI ratio: {facts.dti_ratio:.1%}")
    user_message_parts.append("")
    
    # Section 3: Fired labels with KB entries
    if fired_labels:
        user_message_parts.append("## Issues & Opportunities (by priority)")
        user_message_parts.append("")
        
        for fired_label in fired_labels:
            kb_entry = kb.get(fired_label.label_id)
            if not kb_entry:
                # Label not in KB — skip or use minimal info
                user_message_parts.append(f"**{fired_label.label_id}** (unrecorded label)")
                continue
            
            user_message_parts.append(f"### [{fired_label.priority}] {kb_entry.display_name}")
            user_message_parts.append(f"*{kb_entry.condition_human}*")
            user_message_parts.append("")
            user_message_parts.append(f"**Why it matters:**\n{kb_entry.why_it_matters}")
            user_message_parts.append("")
            user_message_parts.append("**Steps to fix:**")
            for step in kb_entry.mitigation_steps:
                user_message_parts.append(f"- {step}")
            user_message_parts.append("")
    else:
        user_message_parts.append("## No issues detected")
        user_message_parts.append("The profile is strong — maintain current habits.")
        user_message_parts.append("")
    
    # Section 4: Instruction
    user_message_parts.append("## Your task")
    user_message_parts.append("Using the above facts and issues, provide:")
    user_message_parts.append("1. The score and band")
    user_message_parts.append("2. The #1 priority issue and specific actions to fix it")
    user_message_parts.append("3. A timeline (e.g., 'can recover 40 points in 2 billing cycles')")
    user_message_parts.append("4. One thing to avoid")
    user_message_parts.append("")
    user_message_parts.append("Always cite specific numbers from the profile.")
    
    user_message = "\n".join(user_message_parts)
    
    return SYSTEM_PROMPT, user_message
