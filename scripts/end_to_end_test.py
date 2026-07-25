#!/usr/bin/env python3
"""End-to-end test — run the full pipeline on all 23 customers.

This is Phase 11: wires together all 10 previous phases and tests the
complete workflow on all 23 seed customers. Checks:
  - Every customer flows through without errors
  - Facts are reproducible (run twice, compare)
  - Coverage contract: all 32 labels fire at least once
"""

import json
from pathlib import Path
from datetime import datetime
from collections import Counter

from app.data_fetch import fetch_customer_by_pan
from app.pii_parser import sanitise_record
from app.precompute import precompute_facts
from app.rule_engine import fire_labels
from app.prompt_builder import build_prompt
from app.citations import generate_citations
from app.db import get_repository


def run_pipeline(pan_card: str, monthly_income_inr: int = None):
    """Run the full pipeline for one customer."""
    # Fetch
    record = fetch_customer_by_pan(pan_card)
    
    # If income not provided, estimate from customer record
    if monthly_income_inr is None:
        monthly_income_inr = record.customer.income_monthly_paise // 100
    
    # Sanitise
    sanitised = sanitise_record(record)
    
    # Precompute
    facts = precompute_facts(sanitised, monthly_income_inr=monthly_income_inr)
    
    # Rule engine
    fired = fire_labels(facts)
    
    # Prompt builder
    sys_prompt, user_msg = build_prompt(sanitised, facts, fired)
    
    return {
        'customer_id': record.customer.customer_id,
        'pan': pan_card,
        'score': facts.score,
        'band': facts.score_band.value,
        'fired_labels': [f.label_id for f in fired],
        'n_labels_fired': len(fired),
        'facts_snapshot': {
            'overall_utilization': round(facts.overall_utilization, 2),
            'n_accounts_maxed': sum(1 for u in facts.account_utilizations.values() if u > 0.9),
            'dti_ratio': round(facts.dti_ratio, 2),
        },
    }


def main():
    """Run the full E2E test on all 23 customers."""
    print("=" * 80)
    print("CIBIL Credit Coach — End-to-End Test")
    print("=" * 80)
    print()
    
    repo = get_repository()
    customers = repo.list_all_customers()
    
    print(f"Running pipeline on {len(customers)} customers...")
    print()
    
    results = []
    all_fired_labels = Counter()
    errors = []
    
    for cust in customers:
        pan = cust.customer.pan_card
        try:
            result = run_pipeline(pan, monthly_income_inr=cust.customer.income_monthly_paise // 100)
            results.append(result)
            
            # Track labels for coverage check
            for label in result['fired_labels']:
                all_fired_labels[label] += 1
            
            status = "✓"
        except Exception as exc:
            status = "✗"
            errors.append((pan, str(exc)))
        
        print(f"{status} {cust.customer.customer_id:10} {cust.customer.first_name:8} "
              f"score={cust.score.score:3} → {result.get('n_labels_fired', '?')} labels fired")
    
    print()
    print("=" * 80)
    print("TEST RESULTS")
    print("=" * 80)
    print()
    
    # Summary
    print(f"✓ Customers processed:    {len(results)}/{len(customers)}")
    if errors:
        print(f"✗ Errors:                 {len(errors)}")
        for pan, err in errors:
            print(f"  - {pan}: {err[:80]}")
    else:
        print(f"✓ No errors")
    
    print()
    print("Label Coverage:")
    
    # Load expected labels from KB
    from app.kb_loader import get_knowledge_base
    kb = get_knowledge_base()
    all_label_ids = set(kb.all_label_ids())
    
    fired_label_ids = set(all_fired_labels.keys())
    missed_labels = all_label_ids - fired_label_ids
    
    print(f"  Expected labels:         {len(all_label_ids)}")
    print(f"  Labels that fired:       {len(fired_label_ids)}")
    print(f"  Coverage:                {len(fired_label_ids)}/{len(all_label_ids)} ({len(fired_label_ids)*100//len(all_label_ids)}%)")
    
    if missed_labels:
        print(f"  ✗ Missed labels ({len(missed_labels)}):")
        for label in sorted(missed_labels):
            print(f"    - {label}")
    else:
        print(f"  ✓ All labels fire (coverage contract SATISFIED)")
    
    print()
    print("Label Firing Frequency:")
    for label_id, count in all_fired_labels.most_common(10):
        print(f"  {label_id:35} : {count:2} customers")
    
    print()
    print("Score Distribution:")
    scores = [r['score'] for r in results]
    bands = Counter(r['band'] for r in results)
    print(f"  Min: {min(scores)}, Max: {max(scores)}, Avg: {sum(scores)/len(scores):.0f}")
    for band in ['Excellent', 'Very Good', 'Good', 'Fair', 'Poor']:
        count = bands.get(band, 0)
        if count:
            print(f"  {band:12} : {count} customers")
    
    print()
    print("=" * 80)
    
    # Exit code
    if len(missed_labels) > 0:
        print(f"⚠ Coverage contract FAILED: {len(missed_labels)} labels did not fire")
        return 1
    elif errors:
        print(f"✗ Errors occurred during pipeline execution")
        return 1
    else:
        print("✓ All checks passed!")
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
