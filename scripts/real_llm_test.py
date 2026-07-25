#!/usr/bin/env python3
"""Real end-to-end test with LLM invocation.

Usage:
  export OPENAI_API_KEY="sk-..."
  export LANGSMITH_API_KEY="ls_..."
  python scripts/real_llm_test.py ABCPS1234A 75000
"""

import sys
import os
from datetime import datetime

# Configure LangSmith (if API key is present)
if os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "cibil-coach")
    print("✓ LangSmith tracing enabled")
else:
    print("⚠ LANGSMITH_API_KEY not set — tracing disabled")

from app.data_fetch import fetch_customer_by_pan
from app.pii_parser import sanitise_record
from app.precompute import precompute_facts
from app.rule_engine import fire_labels
from app.kb_loader import get_knowledge_base
from app.prompt_builder import build_prompt
from app.llm_invoke import invoke_llm
from app.citations import generate_citations
from app.schemas import LLMError


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/real_llm_test.py <PAN> [monthly_income_inr]")
        print("Example: python scripts/real_llm_test.py ABCPS1234A 75000")
        sys.exit(1)
    
    pan = sys.argv[1]
    income_inr = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    print("=" * 80)
    print("CIBIL Credit Coach — Real LLM Test")
    print("=" * 80)
    print()
    print(f"Input: PAN={pan}, Income={income_inr or 'from profile'}")
    print()
    
    try:
        # ===== FETCH & SANITISE
        print("[1/6] Fetching customer record...")
        record = fetch_customer_by_pan(pan)
        print(f"✓ Found: {record.customer.first_name}, Score: {record.score.score}")
        
        if income_inr is None:
            income_inr = record.customer.income_monthly_paise // 100
        
        print("[2/6] Sanitising (PII removal)...")
        sanitised = sanitise_record(record)
        print(f"✓ PAN masked: {sanitised.pan_masked}")
        
        # ===== PRECOMPUTE
        print("[3/6] Computing facts (74 features)...")
        facts = precompute_facts(sanitised, monthly_income_inr=income_inr)
        print(f"✓ Facts computed:")
        print(f"    Score: {facts.score} ({facts.score_band.value})")
        print(f"    Utilization: {facts.overall_utilization:.1%}")
        print(f"    DTI: {facts.dti_ratio:.1%}")
        print(f"    Accounts: {facts.n_revolving_accounts} revolving + {facts.n_installment_accounts} installment")
        
        # ===== RULE ENGINE
        print("[4/6] Firing labels...")
        fired = fire_labels(facts)
        print(f"✓ {len(fired)} labels fired:")
        for i, label in enumerate(fired[:10], 1):
            print(f"    {i}. [{label.priority}] {label.label_id}")
        if len(fired) > 10:
            print(f"    ... and {len(fired) - 10} more")
        
        # ===== PROMPT BUILDER
        print("[5/6] Building prompt...")
        sys_prompt, user_msg = build_prompt(sanitised, facts, fired)
        print(f"✓ Prompt ready ({len(user_msg)} chars)")
        
        # ===== LLM INVOCATION
        print("[6/6] Calling LLM (OpenAI)...")
        print("     (This may take 10-30 seconds...)")
        llm_output = invoke_llm(sys_prompt, user_msg)
        print(f"✓ LLM responded ({len(llm_output)} chars)")
        
        # ===== CITATIONS
        print()
        print("[7/7] Generating citations...")
        annotated, citations = generate_citations(llm_output, facts, fired)
        print(f"✓ {len(citations)} citations extracted")
        
        # ===== OUTPUT
        print()
        print("=" * 80)
        print("LLM OUTPUT (Analysis + Reasoning + Improvement Plan)")
        print("=" * 80)
        print()
        print(llm_output)
        
        if citations:
            print()
            print("=" * 80)
            print("CITATIONS")
            print("=" * 80)
            for i, cit in enumerate(citations[:10], 1):
                print(f"\n[{i}] {cit.claim}")
                if cit.fact_ids:
                    print(f"    Facts: {', '.join(cit.fact_ids)}")
                if cit.sources:
                    print(f"    Sources: {', '.join(cit.sources)}")
            if len(citations) > 10:
                print(f"\n... and {len(citations) - 10} more citations")
        
        print()
        print("=" * 80)
        print("✓ Test completed successfully")
        print("=" * 80)
        
        return 0
    
    except LLMError as exc:
        print(f"\n✗ LLM Error: {exc}")
        print("\nMake sure OPENAI_API_KEY is set:")
        print("  export OPENAI_API_KEY='sk-...'")
        return 1
    except Exception as exc:
        print(f"\n✗ Error: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
