"""Citation Generation — attach sources to LLM claims.

This is Phase 10: scans the LLM output for numeric claims and attaches
sources (facts + KB entries). Ensures every number traces back to the
original data.
"""

import re
from typing import Optional

from app.schemas import FactSet, FiredLabel, Citation
from app.kb_loader import get_knowledge_base


def generate_citations(
    llm_output: str,
    facts: FactSet,
    fired_labels: list[FiredLabel],
) -> tuple[str, list[Citation]]:
    """Annotate the LLM output with citations.
    
    Scans for numeric claims and attaches sources.
    
    Args:
      llm_output: Raw text from the LLM
      facts: FactSet with source numbers
      fired_labels: List of fired labels (for KB sources)
    
    Returns:
      (annotated_output, citations_list)
    """
    kb = get_knowledge_base()
    citations_list: list[Citation] = []
    
    # Extract all numbers from the output (percentage, rupees, counts, etc.)
    # This is a heuristic — look for patterns like "50%", "Rs.50,000", "3 inquiries"
    number_pattern = r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*(%|Rs|paise|months?|years?|inquiries?|accounts?)?'
    
    matches = re.finditer(number_pattern, llm_output)
    
    # Build a mapping of facts to their values for matching
    fact_values = {
        'overall_utilization': f"{facts.overall_utilization:.0%}",
        'total_balance_paise': f"Rs.{facts.total_balance_paise // 100:,}",
        'total_credit_limit_paise': f"Rs.{facts.total_credit_limit_paise // 100:,}",
        'inquiries_6mo': str(facts.inquiries_6mo),
        'oldest_account_months': f"{facts.oldest_account_months // 12}",
        'dti_ratio': f"{facts.dti_ratio:.0%}",
    }
    
    for match in matches:
        number = match.group(1)
        unit = match.group(2) or ""
        claim = match.group(0)
        
        # Try to match to a fact
        matched_facts = []
        matched_sources = []
        
        for fact_id, fact_val_str in fact_values.items():
            if number in fact_val_str or number.replace(",", "") in fact_val_str:
                matched_facts.append(fact_id)
        
        # Get KB sources from fired labels
        for fired_label in fired_labels:
            entry = kb.get(fired_label.label_id)
            if entry:
                matched_sources.extend(entry.cibil_reason_codes)
        
        if matched_facts or matched_sources:
            citation = Citation(
                claim=claim,
                sources=list(set(matched_sources)),  # Deduplicate
                fact_ids=matched_facts,
            )
            citations_list.append(citation)
    
    # Annotate the output (simple: add footnotes)
    annotated = llm_output
    if citations_list:
        annotated += "\n\n## Sources\n"
        for i, cit in enumerate(citations_list, 1):
            annotated += f"\n[{i}] {cit.claim}"
            if cit.sources:
                annotated += f" (CIBIL codes: {', '.join(cit.sources)})"
            if cit.fact_ids:
                annotated += f" — from facts: {', '.join(cit.fact_ids)}"
    
    return annotated, citations_list
