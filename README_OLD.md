# CIBIL Credit Coach — Quick Start Guide

The core pipeline is complete and tested. Here's how to run it with your own OpenAI API key.

## Setup

### 1. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate  # On macOS/Linux
# OR
# .venv\Scripts\activate  # On Windows

pip install -r requirements.txt
```

### 2. Configure API Keys

Create a `.env` file in the root directory (copy from `.env.example`):

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
# Required: OpenAI API Key
# Get from: https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-...

# Optional: LangSmith tracing (for observability)
# Get from: https://smith.langchain.com
LANGSMITH_API_KEY=ls_...
LANGSMITH_PROJECT=cibil-coach
```

**Note:** Never commit `.env` to version control. The `.env.example` file is a template.

## Running the Pipeline

### Option 1: Test with Mock LLM (no API calls)

```bash
cd /Users/rr/DEV/CIBIL\ Coach
python3 -c "
from app.data_fetch import fetch_customer_by_pan
from app.pii_parser import sanitise_record
from app.precompute import precompute_facts
from app.rule_engine import fire_labels
from app.prompt_builder import build_prompt

# Fetch & process
record = fetch_customer_by_pan('ABCPS1234A')
sanitised = sanitise_record(record)
facts = precompute_facts(sanitised, monthly_income_inr=75000)
fired = fire_labels(facts)
sys_prompt, user_msg = build_prompt(sanitised, facts, fired)

print(f'✓ Pipeline ready for customer {record.customer.first_name}')
print(f'  Score: {facts.score}, {len(fired)} labels fired')
"
```

### Option 2: Run with Real LLM (OpenAI)

```bash
export OPENAI_API_KEY="sk-..."
python3 scripts/real_llm_test.py ABCPS1234A 75000
```

Output will include:
1. Customer profile
2. 74 precomputed facts
3. 32 label rules evaluation
4. LLM-generated analysis (from OpenAI)
5. Citations extracted

### Option 3: End-to-End Test on All 23 Customers

```bash
python3 scripts/end_to_end_test.py
```

This verifies:
- All 23 customers process without errors
- Coverage contract: all 32 labels fire
- Score distribution and label frequency

## Architecture & Data Flow

```
User Input (PAN + Income)
         ↓
   [PAN Validation]
         ↓
[Data Fetch] → [SQLite Query] → CustomerRecord
         ↓
[PII Parser] (mask identifiers)
         ↓
[Precompute Engine] (74 facts, deterministic)
         ↓
[Rule Engine] (fire 32 labels based on thresholds)
         ↓
[Label KB Ingestion] (fetch mitigation, sources)
         ↓
[Prompt Builder] (assemble system + user message)
         ↓
[LLM Invocation] (OpenAI, temperature 0.3)
         ↓
[Citation Generation] (verify & annotate)
         ↓
[SSE Streaming] (Server-Sent Events to browser)
         ↓
Output: Score + Analysis + Recommendations (with citations)
```

**For detailed flow with error handling, see [ARCHITECTURE_FLOW.md](ARCHITECTURE_FLOW.md)** — includes:
- Complete Mermaid class diagram
- Stage-by-stage breakdown
- Concrete example: PAN=ABCPS1234A, Income=₹100,000
- Full error handling matrix
- Performance metrics

## Module Breakdown

| Module | File | Status | Purpose |
|--------|------|--------|---------|
| Schemas | `app/schemas.py` | ✓ Complete | Pydantic models for all payloads |
| Database | `app/db.py` | ✓ Complete | Load & query customer profiles |
| PAN Validation | `app/pan_validator.py` | ✓ Complete | Validate PAN format |
| Data Fetch | `app/data_fetch.py` | ✓ Complete | Retrieve customer by PAN |
| PII Parser | `app/pii_parser.py` | ✓ Complete | Mask sensitive data |
| Precompute | `app/precompute.py` | ✓ Complete | Compute 74 facts |
| Rule Engine | `app/rule_engine.py` | ✓ Complete | Fire 32 labels |
| KB Loader | `app/kb_loader.py` | ✓ Complete | Load knowledge base |
| Prompt Builder | `app/prompt_builder.py` | ✓ Complete | Assemble LLM prompt |
| LLM Invoke | `app/llm_invoke.py` | ✓ Complete | Call OpenAI |
| Citations | `app/citations.py` | ✓ Complete | Annotate output |

## Key Features

✓ **Deterministic Pipeline** — Same (customer, date) → identical facts every run  
✓ **PII Privacy** — All raw identifiers masked before LLM exposure  
✓ **Coverage Guaranteed** — All 32 labels fire on the 23 seed customers  
✓ **Paise Arithmetic** — All money is integer paise, no float errors  
✓ **Indian Context** — CIBIL terminology, INR formatting, RBI thresholds  
✓ **Grounded Reasoning** — LLM cites specific numbers from the profile  
✓ **LangSmith Ready** — Traces every run for observability (if API key provided)  

## Configuration

Edit `app/config.py` to modify constants:

```python
AS_OF_DATE = date(2026, 7, 25)  # Anchor for time-windowed facts
CIBIL_SCORE_MIN = 300           # Score range floor
CIBIL_SCORE_MAX = 900           # Score range ceiling
RBI_HIGH_DTI = 0.36             # High DTI threshold
RBI_SEVERE_DTI = 0.50           # Severe DTI threshold
```

Environment variables override defaults:

```bash
export OPENAI_MODEL="gpt-4-turbo"
export LLM_TEMPERATURE="0.2"
export LLM_MAX_TOKENS="1500"
```

## Testing

```bash
# Validate build.yaml integrity
python3 scripts/validate_build_doc.py --summary

# End-to-end test (no LLM calls)
python3 scripts/end_to_end_test.py

# Real LLM test (requires OPENAI_API_KEY)
python3 scripts/real_llm_test.py ABCPS1234A 75000
```

## File Structure

```
/Users/rr/DEV/CIBIL Coach/
├── app/                    # Core pipeline
│   ├── __init__.py
│   ├── schemas.py         # Pydantic models
│   ├── config.py          # Constants
│   ├── db.py              # Database layer
│   ├── pan_validator.py   # PAN validation
│   ├── data_fetch.py      # Customer fetch
│   ├── pii_parser.py      # PII masking
│   ├── precompute.py      # 74 features
│   ├── rule_engine.py     # 32 label rules
│   ├── kb_loader.py       # KB in memory
│   ├── prompt_builder.py  # LLM prompt
│   ├── llm_invoke.py      # LLM call
│   └── citations.py       # Citations
├── scripts/
│   ├── validate_build_doc.py    # Build validation
│   ├── end_to_end_test.py       # E2E test (all 23 customers)
│   └── real_llm_test.py         # Real LLM test
├── build_docs/
│   ├── build.yaml              # Build progress & context
│   ├── README.md               # Data package docs
│   ├── precompute_list.md      # 74 feature spec
│   ├── cibil_data.json         # 23 seed customers
│   └── label_kb.json           # 32 label KB
├── .env                         # Local config (never commit)
├── .env.example                 # Template
├── .gitignore                   # Git ignore rules
└── requirements.txt             # Python dependencies

```

## Known Limitations / Future Work

- **Streaming:** Currently returns full LLM response at once. Can add streaming (SSE) for real-time UI.
- **Authentication:** No auth layer yet. Add before any shared deployment.
- **Database:** Currently in-memory dict. Swap for SQLite/PostgreSQL/etc.
- **Rate Shopping:** 14-30 day inquiry dedup not yet implemented.
- **Multi-bureau:** Single CIBIL source. Can add Experian, Equifax, CRIF High Mark.
- **Deployment:** No API server yet. Can add FastAPI wrapper.

## Support & Questions

For issues or questions:
1. Check `.env` is configured with valid API keys
2. Run `python3 scripts/validate_build_doc.py --summary` to verify build integrity
3. Run `python3 scripts/end_to_end_test.py` to verify pipeline logic
4. Check OpenAI API status at https://status.openai.com

## License & Attribution

- CIBIL Score Factors: https://www.cibil.com/cibil-score-factors/
- RBI Guidelines: https://www.rbi.org.in/
- Seed data: 23 representative Indian credit profiles (synthetic for testing)
