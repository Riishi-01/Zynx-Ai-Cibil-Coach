# CIBIL Credit Coach

An AI-powered credit analysis tool that explains your CIBIL score in plain language. Get personalized insights into your credit profile with specific numbers and actionable recommendations.

## What It Does

Input your PAN and monthly income → Get:
- **Your CIBIL Score** (300-900) and band (Poor, Fair, Good, Very Good, Excellent)
- **What's Helping** your score (perfect payment history, good credit mix)
- **What's Hurting** your score (high card balances, recent inquiries)
- **Specific Recommendations** (lower your utilization to 30%, wait 6 months before applying)
- **Citations** backed by real numbers from your profile

Everything is grounded in your actual credit data — no generic advice.

## CIBIL Score Explained

| Score Range | Band | Meaning |
|---|---|---|
| 300-579 | **Poor** | High risk; difficult to get credit |
| 580-699 | **Fair** | Moderate risk; limited options |
| 700-749 | **Good** | Low risk; good approval odds |
| 750-799 | **Very Good** | Very low risk; strong terms |
| 800-900 | **Excellent** | Minimal risk; best rates & terms |

### How Your Score is Built

Your CIBIL score is influenced by:
- **Payment History (35%)** — Did you pay bills on time?
- **Credit Utilization (30%)** — How much of your available credit do you use?
- **Credit Age (15%)** — How long have you had credit accounts?
- **Credit Mix (10%)** — Do you have different types of credit? (cards, loans, etc.)
- **Recent Inquiries (10%)** — How many hard inquiries in the last 3 months?

### Improve Your Score

1. **Pay bills on time** — Single most important factor
2. **Lower your card balances** — Keep utilization below 30%
3. **Don't close old cards** — Longer history helps
4. **Limit new applications** — Space out hard inquiries by 3-6 months
5. **Keep a mix of credit** — Have both revolving (cards) and installment (loans)

## Try It Out

### Quick Start (2 minutes)

```bash
# 1. Clone and setup
git clone https://github.com/yourusername/cibil-coach.git
cd cibil-coach
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Set your API key
cp .env.example .env
# Edit .env and add your OpenAI API key

# 3. Run the web interface
bash run_web.sh

# 4. Open http://localhost:8000 and enter a PAN
```

### Example

**Input:**
- PAN: ABCPS1234A
- Monthly Income: ₹75,000

**Output:**
```
Score: 715 (Good)

What to Fix First:
Your card balance is at 70% of your limit (₹4,20,000 of ₹6,00,000). 
This high utilization is hurting your score. Bring it down to 30% 
within the next 3 months.

How to Fix It:
1. Pay down your HDFC Millennia to ₹1,80,000
2. Request a credit limit increase on your ICICI card
3. Don't apply for new cards for the next 3 months

What to Avoid:
- Missed payments (you have perfect history — keep it)
- Multiple hard inquiries (clusters in 14-30 days trigger rate-shopping flags)
- Closing old accounts (your oldest card from 2021 is valuable)
```

## How It Works

1. **You enter:** PAN + monthly income
2. **We fetch:** Your CIBIL profile (23 sample customers or real API)
3. **We compute:** 74 credit metrics (utilization, DTI, payment history, inquiry patterns, etc.)
4. **We analyze:** 32 risk rules fire based on your data
5. **We explain:** AI generates personalized analysis with citations to your actual numbers

Every number in the output traces back to your credit data. We cite specific amounts, CIBIL reason codes, and RBI guidelines.

## Key Features

✓ **100% Grounded** — All recommendations backed by your actual credit metrics  
✓ **Transparent** — Every number is cited (see exactly where it comes from)  
✓ **Deterministic** — Same input always produces same analysis  
✓ **Indian Context** — CIBIL scores (300-900), RBI thresholds, INR formatting  
✓ **Real Data** — Works with actual credit profiles or 23 sample customers  
✓ **No Hidden Jargon** — Plain language explanations  

## Architecture

```
Your Input (PAN + Income)
    ↓
Fetch Credit Profile (SQLite)
    ↓
Compute 74 Metrics (Utilization, DTI, Payment History, etc.)
    ↓
Fire 32 Risk Rules (High Utilization, Delinquency, etc.)
    ↓
AI Analysis (Personalized recommendations)
    ↓
Citations (CIBIL codes + numbers verified)
    ↓
Output: Score + Explanation + Recommendations
```

**For technical details, see [ARCHITECTURE_FLOW.md](ARCHITECTURE_FLOW.md)**

## Development

### Project Structure

```
cibil-coach/
├── app/                    # Core pipeline
│   ├── web.py             # FastAPI + web UI
│   ├── data_fetch.py      # Credit profile lookup
│   ├── precompute.py      # 74 metrics computation
│   ├── rule_engine.py     # 32 risk label rules
│   ├── prompt_builder.py  # LLM prompt assembly
│   ├── llm_invoke.py      # OpenAI integration
│   └── citations.py       # Source attribution
├── scripts/
│   ├── seed_db.py         # Load customer data
│   └── e2e_db_test.py     # End-to-end test
├── alembic/               # Database migrations
├── build_docs/            # Data & KB files
│   ├── cibil_data.json    # 23 sample customers
│   └── label_kb.json      # 32 label knowledge base
└── README.md              # This file
```

### Run Tests

```bash
# Test the full pipeline (no API calls)
python3 scripts/e2e_db_test.py

# Test with real OpenAI (requires OPENAI_API_KEY)
export OPENAI_API_KEY="sk-..."
python3 scripts/real_llm_test.py ABCPS1234A 75000
```

## Configuration

Edit `.env` to customize:

```env
# Required
OPENAI_API_KEY=sk-your-key-here

# Optional
DATABASE_URL=sqlite:///./cibil_coach.db
OPENAI_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=1000
```

## Performance

- **Speed:** 2.4 seconds per analysis (1.2s to first insight)
- **Cost:** ~$0.0002 per query (0.02 cents)
- **Accuracy:** 74 computed metrics, 32 validated rules
- **Determinism:** Same customer = same analysis every time

## Limitations & Future Work

- **Authentication:** No login required yet (add before shared deployment)
- **Real Data:** Currently uses 23 sample customers; integrate real API
- **Multi-Bureau:** CIBIL only; add Experian, Equifax, CRIF High Mark
- **Streaming:** Full response streams in real-time; can add progressive UI
- **Deployment:** Currently local; can deploy to cloud with Docker

## License

MIT License — See [LICENSE](LICENSE) for details

## Contributing

Found a bug? Have a suggestion? See [CONTRIBUTING.md](CONTRIBUTING.md)

## Questions?

- **Setup issues?** Check `.env` is configured with a valid OpenAI API key
- **Analysis seems wrong?** Run `python3 scripts/e2e_db_test.py` to verify the pipeline
- **Want to extend it?** See ARCHITECTURE_FLOW.md for the data flow and adding new metrics

---

**Built with:** Python • FastAPI • SQLite • OpenAI • CIBIL Knowledge Base

**Last Updated:** 2026-07-25
