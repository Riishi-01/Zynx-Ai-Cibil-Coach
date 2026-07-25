"""Rule Engine — evaluate facts against business thresholds and fire labels.

This is Phase 5: evaluates precomputed facts and fires labels based on the
32 rules from label_kb.json. Deterministic, rule-based classification.

Coverage contract: all 32 labels must fire on at least one of the 23 customers.
"""

from typing import Optional

from app.schemas import FactSet, FiredLabel
from app.config import HYSTERESIS_UTILIZATION


# ============================================================================
# RULE TABLE — (label_id, fact_id, operator, threshold, priority)
# Derived from label_kb.json and precompute_list.md §12
# ============================================================================

RULE_TABLE = [
    # Utilization (7 labels)
    ("maxed_out", "overall_utilization", ">", 0.90, 1),
    ("all_cards_maxed", "n_accounts_over_90pct", ">=", 2, 1),
    ("maxed_out_account", "per_account_util_90+", ">", 0.90, 2),  # Per-account expansion
    ("very_high_utilization", "overall_utilization", ">", 0.75, 2),
    ("high_utilization", "overall_utilization", ">", 0.50, 3),
    ("low_utilization", "overall_utilization", "<", 0.10, 5),
    ("utilization_concentration", "utilization_concentration", ">", 0.5, 3),
    
    # Payment history (5 labels)
    ("major_delinquency", "worst_late_status", ">=", 3, 1),  # 90+ days
    ("serious_delinquency", "worst_late_status", ">=", 2, 2),  # 60+ days
    ("recent_late_payment", "n_lates_30_24mo", ">", 0, 3),
    ("perfect_payment", "worst_late_status", "==", 0, 5),
    ("zero_utilization_paradox", "zero_util_with_cards", "==", True, 4),
    
    # Inquiries (3 labels)
    ("recent_inquiries", "inquiries_6mo", ">=", 2, 3),
    ("credit_seeking_pattern", "credit_seeking_pattern", "==", True, 2),
    ("excessive_new_credit", "inquiries_6mo", ">=", 3, 2),
    
    # Collections (3 labels)
    ("disputable_collection", "n_collections_disputed", ">", 0, 2),
    ("collection_past_sol", "n_collections_past_sol", ">", 0, 2),
    ("paid_collection_still_reporting", "n_collections_paid_still_reporting", ">", 0, 2),
    
    # Credit age (2 labels)
    ("thin_file", "is_thin_file", "==", True, 4),
    ("extreme_thin_file", "is_extreme_thin_file", "==", True, 1),
    
    # Credit mix (5 labels)
    ("no_revolving_credit", "has_no_revolving_credit", "==", True, 3),
    ("unused_revolving_cards", "n_unused_revolving_cards", ">", 0, 4),
    ("single_card_dependency", "single_card_dependency", "==", True, 3),
    ("oldest_card_at_risk", "oldest_card_at_risk_unused", "==", True, 4),
    ("single_card_limit_share", "single_card_limit_share", ">", 0.70, 3),
    
    # Score trend (3 labels)
    ("score_falling", "score_trend", "==", "falling", 2),
    ("score_rising", "score_trend", "==", "rising", 5),
    ("score_volatile", "score_volatility_3mo", ">", 30, 3),
    
    # DTI (2 labels)
    ("high_dti", "is_high_dti", "==", True, 2),
    ("severe_dti", "is_severe_dti", "==", True, 1),
    
    # Data quality (2 labels)
    ("data_staleness", "freshness_days", ">", 7, 5),
    ("credit_score_context", "score_band", "!=", "", 5),  # Always fires as context
]


def _evaluate_condition(fact_value, operator: str, threshold) -> bool:
    """Evaluate a single fact against a threshold."""
    if operator == ">":
        return fact_value > threshold
    elif operator == ">=":
        return fact_value >= threshold
    elif operator == "<":
        return fact_value < threshold
    elif operator == "<=":
        return fact_value <= threshold
    elif operator == "==":
        return fact_value == threshold
    elif operator == "!=":
        return fact_value != threshold
    else:
        raise ValueError(f"Unknown operator: {operator}")


def fire_labels(facts: FactSet) -> list[FiredLabel]:
    """Evaluate facts against the rule table and return fired labels.
    
    Returns a priority-ordered list of FiredLabel with evidence.
    """
    fired = []
    
    # Compute derived facts for rule matching
    n_maxed_accounts = sum(1 for util in facts.account_utilizations.values() if util > 0.90)
    
    # Check each rule
    for label_id, fact_id, operator, threshold, priority in RULE_TABLE:
        fact_value = None
        evidence_facts = [fact_id]
        account_id = None
        
        # Map fact_id to FactSet field
        if fact_id == "overall_utilization":
            fact_value = facts.overall_utilization
        elif fact_id == "n_accounts_over_90pct":
            fact_value = n_maxed_accounts
        elif fact_id == "per_account_util_90+":
            # Per-account expansion: fire one label per maxed account
            for acc_id, util in facts.account_utilizations.items():
                if util > 0.90:
                    fired.append(FiredLabel(
                        label_id="maxed_out_account",
                        priority=2,
                        evidence_fact_ids=["account_utilizations"],
                        account_id=acc_id,
                    ))
            continue
        elif fact_id == "utilization_concentration":
            fact_value = facts.utilization_concentration
        elif fact_id == "worst_late_status":
            fact_value = facts.worst_late_status
        elif fact_id == "n_lates_30_24mo":
            fact_value = facts.n_lates_30_24mo
        elif fact_id == "zero_util_with_cards":
            fact_value = (facts.overall_utilization < 0.01 and facts.n_revolving_accounts > 0)
        elif fact_id == "inquiries_6mo":
            fact_value = facts.inquiries_6mo
        elif fact_id == "credit_seeking_pattern":
            fact_value = facts.credit_seeking_pattern
        elif fact_id == "n_collections_disputed":
            fact_value = facts.n_collections_disputed
        elif fact_id == "n_collections_past_sol":
            fact_value = facts.n_collections_past_sol
        elif fact_id == "n_collections_paid_still_reporting":
            fact_value = facts.n_collections_paid_still_reporting
        elif fact_id == "is_thin_file":
            fact_value = facts.is_thin_file
        elif fact_id == "is_extreme_thin_file":
            fact_value = facts.is_extreme_thin_file
        elif fact_id == "has_no_revolving_credit":
            fact_value = facts.has_no_revolving_credit
        elif fact_id == "n_unused_revolving_cards":
            fact_value = facts.n_unused_revolving_cards
        elif fact_id == "single_card_dependency":
            fact_value = facts.single_card_dependency
        elif fact_id == "oldest_card_at_risk_unused":
            fact_value = (facts.oldest_account_months > 60 and facts.n_unused_revolving_cards > 0)
        elif fact_id == "single_card_limit_share":
            fact_value = facts.single_card_limit_share
        elif fact_id == "score_trend":
            fact_value = facts.score_trend
        elif fact_id == "score_volatility_3mo":
            fact_value = facts.score_volatility_3mo
        elif fact_id == "is_high_dti":
            fact_value = facts.is_high_dti
        elif fact_id == "is_severe_dti":
            fact_value = facts.is_severe_dti
        elif fact_id == "freshness_days":
            fact_value = facts.freshness_days
        elif fact_id == "score_band":
            fact_value = facts.score_band
        elif fact_id == "very_high_utilization":
            fact_value = facts.overall_utilization
            threshold = 0.75
        elif fact_id == "high_utilization":
            fact_value = facts.overall_utilization
            threshold = 0.50
        elif fact_id == "low_utilization":
            fact_value = facts.overall_utilization
            threshold = 0.10
        
        if fact_value is None:
            continue
        
        # Evaluate the condition
        if _evaluate_condition(fact_value, operator, threshold):
            fired.append(FiredLabel(
                label_id=label_id,
                priority=priority,
                evidence_fact_ids=evidence_facts,
                account_id=account_id,
            ))
    
    # Sort by priority (1 = most urgent)
    fired.sort(key=lambda x: x.priority)
    
    return fired
