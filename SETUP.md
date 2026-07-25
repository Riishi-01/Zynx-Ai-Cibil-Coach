# Setup Instructions — CIBIL Credit Coach

## Quick Start (5 minutes)

### Step 1: Get API Keys

1. **OpenAI API Key** (required)
   - Go to https://platform.openai.com/api-keys
   - Create a new API key
   - Copy it (starts with `sk-`)

2. **LangSmith API Key** (optional)
   - Go to https://smith.langchain.com
   - Create an account
   - Copy your API key (starts with `ls_`)

### Step 2: Configure Environment

In the project root (`/Users/rr/DEV/CIBIL Coach`):

```bash
# Create .env from template
cp .env.example .env

# Edit .env and paste your API keys
nano .env
```

Your `.env` should look like:
```
OPENAI_API_KEY=sk-proj-xxx...
LANGSMITH_API_KEY=ls_xxx...
LANGSMITH_PROJECT=cibil-coach
```

### Step 3: Install Dependencies

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 4: Run Real Test

```bash
# Test with customer ABCPS1234A, income ₹75,000/month
python3 scripts/real_llm_test.py ABCPS1234A 75000
```

You should see:
```
[1/6] Fetching customer record...
[2/6] Sanitising (PII removal)...
[3/6] Computing facts (74 features)...
[4/6] Firing labels...
[5/6] Building prompt...
[6/6] Calling LLM (OpenAI)...

========== LLM OUTPUT ==========
[Full credit analysis from OpenAI]
```

---

## What Happens

The pipeline:

1. **Fetches** customer record from `build_docs/cibil_data.json` by PAN
2. **Masks PII** (PAN → ABCPS****A, drops DOB, first name)
3. **Computes** 74 deterministic facts (utilization, DTI, payment history, age, etc.)
4. **Fires** 32 labels based on fact thresholds (e.g., "maxed_out" if utilization > 90%)
5. **Retrieves** knowledge base entries (mitigation steps, sources)
6. **Assembles** a prompt with facts + labels + KB entries
7. **Calls OpenAI** (gpt-4o-mini, temperature 0.3)
8. **Generates citations** (traces each number back to its source)
9. **Returns** analysis + reasoning + improvement plan

---

## Troubleshooting

### "OPENAI_API_KEY not set"

```bash
# Check if .env exists and has a valid key
cat .env | grep OPENAI_API_KEY

# If blank or missing, edit .env and add your key
nano .env
```

### "ModuleNotFoundError: No module named 'app'"

```bash
# Make sure you're in the project root
cd /Users/rr/DEV/CIBIL\ Coach

# Run with PYTHONPATH set
PYTHONPATH=/Users/rr/DEV/CIBIL\ Coach python3 scripts/real_llm_test.py ABCPS1234A 75000
```

### "LLM error: The model `gpt-4o-mini` does not exist"

Ensure your OpenAI account has access to gpt-4o-mini (newer models may require payment).

Or use a different model:
```bash
export OPENAI_MODEL="gpt-3.5-turbo"
python3 scripts/real_llm_test.py ABCPS1234A 75000
```

### Test completes but LLM output is empty

This could mean:
- The model responded but produced very little text (rare)
- The API call succeeded but returned an error response (check logs)

Try with a higher token limit:
```bash
export LLM_MAX_TOKENS=2000
python3 scripts/real_llm_test.py ABCPS1234A 75000
```

---

## Testing Without Real API Keys

### Mock Test (No LLM)

```bash
# Test the pipeline without calling OpenAI
python3 scripts/end_to_end_test.py
```

This verifies:
- All 23 customers load correctly
- Facts compute without errors
- All 32 labels fire (coverage contract)
- No errors in pipeline logic

### Mock with Prompt Preview

```bash
python3 -c "
from app.data_fetch import fetch_customer_by_pan
from app.pii_parser import sanitise_record
from app.precompute import precompute_facts
from app.rule_engine import fire_labels
from app.prompt_builder import build_prompt

rec = fetch_customer_by_pan('ABCPS1234A')
sanitised = sanitise_record(rec)
facts = precompute_facts(sanitised, monthly_income_inr=75000)
fired = fire_labels(facts)
sys_prompt, user_msg = build_prompt(sanitised, facts, fired)

print('=== SYSTEM PROMPT ===')
print(sys_prompt[:500])
print()
print('=== USER MESSAGE (first 1000 chars) ===')
print(user_msg[:1000])
"
```

---

## Other Test Customers

The seed data has 23 diverse profiles:

```
ABCPS1234A  Anjali   Score 715 (Good)        — mixed issues, falling trend
BCDRM2345B  Carlos   Score 612 (Fair)        — maxed out, delinquent
EFGKD5678E  Priya    Score 748 (Good)        — medical collection, rising
GHKKS7890G  Lin      Score 802 (Excellent)   — top-tier
IJKLK9012I  Marcus   Score 668 (Fair)        — thin file, rising
...
VWXYC2345V  Sandeep  Score 588 (Poor)        — DTI stress test (68% DTI!)
WXYZP3456W  Riya     Score 702 (Good)        — new credit, paid collection
```

Run any of them:
```bash
python3 scripts/real_llm_test.py BCDRM2345B 40000  # Carlos, ₹40k income
python3 scripts/real_llm_test.py IJKLK9012I 50000  # Marcus
```

---

## Next Steps

After confirming the real test works:

1. **Build a simple web interface** — FastAPI + HTML frontend to collect PAN + income and stream results
2. **Add database layer** — Replace in-memory JSON with SQLite / PostgreSQL
3. **Deploy** — Docker + Cloud Run / ECS / Heroku
4. **Add authentication** — Protect the /analyze endpoint
5. **Enable streaming** — Return tokens as they're generated (SSE)

See `build_docs/build.yaml` for all planned modules and their status.

---

## Support

For issues:
1. Check API key is valid: https://platform.openai.com/api-keys
2. Check rate limits: https://platform.openai.com/account/rate-limits
3. Check OpenAI status: https://status.openai.com
4. Run validation: `python3 scripts/validate_build_doc.py --summary`

---

**Created:** 2026-07-25  
**Build:** Mavis  
**Pipeline Status:** 22/22 modules complete, coverage contract satisfied
