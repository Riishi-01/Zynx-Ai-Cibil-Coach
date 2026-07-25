# CIBIL Coach — System Architecture & Data Flow

**Complete pipeline flow with error handling (Class Diagram Style)**

---

## 📊 End-to-End Workflow: PAN=ABCPS1234A, Income=₹100,000/month

```mermaid
classDiagram
    class WebInterface {
        Input: PAN, Income
        Action: POST /api/analyze
        Validation: PAN format check
        Error: InvalidPAN → 400
    }

    class PanValidator {
        pan_card: str
        is_valid: bool
        format_check: 5 letters + 4 digits + 1 letter
        Error: InvalidPAN
        Return: bool
    }

    class DataFetchLayer {
        pan_card: ABCPS1234A
        Error: CustomerNotFound → 404
        Action: Query SQLite db
    }

    class CustomerRecord {
        customer_id: cust_001
        first_name: Anjali
        pan_card: ABCPS1234A
        dob_year: 1997
        income_monthly_paise: 10000000
        region: IN-HYD
        score: 715
        band: Good
        accounts: Account[]
        inquiries: Inquiry[]
        collections: Collection[]
        public_records: PublicRecord[]
    }

    class PiiParser {
        Input: CustomerRecord
        Action: Mask identifiers
        pan_masked: ABCDE****F
        first_name_opt: null
        dob_year_opt: null
        Error: PIILeakDetected → 500
    }

    class SanitisedRecord {
        customer_id: cust_001
        pan_masked: ABCDE****F
        first_name_opt: null
        dob_year_opt: null
        income_monthly_paise: 10000000
        region: IN-HYD
        score: 715
        score_band: Good
        accounts: SanitisedAccount[]
    }

    class PrecomputeEngine {
        Input: SanitisedRecord, income_inr=100000
        Compute: 74 deterministic facts
        facts.score: 715
        facts.dti_ratio: 0.12
        facts.overall_utilization: 0.70
        facts.n_lates_90_24mo: 0
        facts.score_trend: stable
        Error: DataComputeError → 500
    }

    class FactSet {
        score: 715
        score_band: Good
        overall_utilization: 0.70
        utilization_concentration: 0.58
        total_credit_limit_paise: 600000
        total_balance_paise: 420000
        n_lates_30_24mo: 0
        n_lates_60_24mo: 0
        n_lates_90_24mo: 0
        inquiries_6mo: 2
        n_collections: 1
        n_revolving_accounts: 4
        dti_ratio: 0.12
        is_high_dti: false
        is_severe_dti: false
        as_of_date: 2026-07-25
    }

    class RuleEngine {
        Input: FactSet
        Action: Evaluate 32 rules
        Rule1: overall_utilization > 0.90
        Rule2: n_lates_90_24mo > 0
        Rule3: dti_ratio > 0.36
        Condition: Threshold-based
        Error: RuleEvaluationError → 500
    }

    class FiredLabels {
        label_id: high_utilization
        priority: 2
        evidence_facts: overall_utilization
        label_id: disputable_collection
        priority: 3
        evidence_facts: n_collections, is_disputable
        label_id: perfect_payment
        priority: 1
        evidence_facts: n_lates_90_24mo
        count: 11
    }

    class LabelKB {
        label_id: high_utilization
        display_name: High Utilization
        mitigation_steps: Lower balance, Request increase
        facts_to_cite: overall_utilization, total_balance_paise
        cibil_reason_codes: [RC-07, RC-08]
        personalized_template: Your utilization is at 70%...
        sources: CIBIL Score Factors
    }

    class KBIngestion {
        Input: FiredLabels (11 labels)
        Action: Lookup KB for each label
        Fetch: mitigation_steps, facts_to_cite
        Enrich: Add citations, sources
        Error: KBUnavailable → 503
    }

    class PromptBuilder {
        system_prompt: You are CIBIL coach...
        user_message: Customer Anjali, score 715...
        facts_context: 74 computed facts
        fired_labels_context: 11 labels with evidence
        kb_context: Mitigation steps per label
        cite_format: ₹X from account Y
        Error: PromptBuilderError → 500
    }

    class SystemPrompt {
        role: CIBIL credit coach
        instructions: Use ONLY provided facts
        rules: Never invent numbers, Always cite
        format: INR paise, CIBIL terminology
        output_structure: Score, What to Fix, How to Fix, What to Avoid
    }

    class UserMessage {
        customer: Anjali (PAN masked)
        score: 715, Good
        income: 100000
        fired_labels: 11 with evidence
        facts: 74 fact values
        kb_entries: Matched KB for each label
        ask: Analyze profile, provide recommendations
    }

    class LLMInvoke {
        service: OpenAI
        model: gpt-4o-mini
        temperature: 0.3
        max_tokens: 1000
        timeout: 30s
        Error: LLMError → 500 OR Timeout → 504
    }

    class LLMResponse {
        score_analysis: Based on 715 score...
        what_to_fix_first: High utilization at 70%
        how_to_fix: Lower balance on maxed card
        what_to_avoid: New hard inquiries
        citations: [RC-07 (High Util), RC-03 (Payment)]
        raw_response: Full LLM output
    }

    class CitationEngine {
        Input: LLMResponse + FactSet
        Action: Extract citations
        cite_format: ₹4,20,000 of ₹6,00,000
        sources: CIBIL, RBI guidelines
        verify: Facts present in FactSet
        Error: CitationMismatch → warn (non-blocking)
    }

    class FinalResponse {
        status: success
        session_id: ABCPS1234A_timestamp
        score: 715
        band: Good
        analysis: Full personalized text
        citations: Verified with sources
        timestamp: 2026-07-25T19:07:27Z
    }

    class WebResponse {
        status_code: 200
        content_type: text/event-stream
        delivery: Server-Sent Events (SSE)
        format: data: {type, content, session_id}
        browser_storage: localStorage (session history)
        Error: 400/404/500 with error message
    }

    %% Relationships
    WebInterface --> PanValidator
    PanValidator --> DataFetchLayer
    DataFetchLayer --> CustomerRecord
    CustomerRecord --> PiiParser
    PiiParser --> SanitisedRecord
    SanitisedRecord --> PrecomputeEngine
    PrecomputeEngine --> FactSet
    FactSet --> RuleEngine
    RuleEngine --> FiredLabels
    FiredLabels --> LabelKB
    LabelKB --> KBIngestion
    KBIngestion --> PromptBuilder
    PromptBuilder --> SystemPrompt
    PromptBuilder --> UserMessage
    SystemPrompt --> LLMInvoke
    UserMessage --> LLMInvoke
    LLMInvoke --> LLMResponse
    LLMResponse --> CitationEngine
    CitationEngine --> FinalResponse
    FinalResponse --> WebResponse
```

---

## 🔍 Detailed Stage Breakdown

### **Stage 1: Web Input & Validation**
```
Input:
  - PAN: ABCPS1234A
  - Income: 100000 (INR)

Validation:
  ✓ PAN format check (AAAAA9999A)
  ✓ Income > 0

Error Handling:
  ✗ Invalid format → 400 Bad Request
  ✗ Missing field → 400 Bad Request
```

### **Stage 2: Data Fetch**
```
Query: SQLite database
  SELECT * FROM customers WHERE pan_card = 'ABCPS1234A'
  → Join with scores, accounts, inquiries, collections, public_records

Result: CustomerRecord
  {
    customer_id: cust_001,
    first_name: Anjali,
    score: 715,
    accounts: [4 credit cards + loans],
    inquiries: [3 recent],
    collections: [1 medical],
    public_records: []
  }

Error Handling:
  ✗ PAN not found → 404 CustomerNotFound
  ✗ DB connection error → 503 DataFetchError
```

### **Stage 3: PII Masking**
```
Input: CustomerRecord (with raw PAN, name, DOB)

Action: Anonymize for LLM exposure
  pan_card: ABCPS1234A → pan_masked: ABCDE****F
  first_name: Anjali → first_name_opt: null
  dob_year: 1997 → dob_year_opt: null

Output: SanitisedRecord (safe for LLM)

Error Handling:
  ✗ Leak detected (raw PAN in output) → 500 PIILeakDetected
```

### **Stage 4: Precompute (74 Facts)**
```
Input: SanitisedRecord + monthly_income_inr=100000

Deterministic Computation:
  • Utilization: balance/limit = 420k/600k = 0.70 (70%)
  • DTI: (15k/cc + 5k/loan) / 100k = 0.20 (20%)
  • Payment history: Last 24 months = [0,0,0,...,0] (perfect)
  • Score trend: 715 (1mo) vs 730 (3mo) = falling trend
  • Age: oldest account = 36 months (> 2 years, not thin)
  • Inquiries: 6mo = 2, 24mo = 5
  • Collections: 1 medical (disputable)

Output: FactSet (74 fields)
  {
    score: 715,
    overall_utilization: 0.70,
    dti_ratio: 0.20,
    n_lates_90_24mo: 0,
    score_trend: falling,
    thin_file: false,
    n_collections: 1,
    is_disputable: true,
    ...62 more facts
  }

Error Handling:
  ✗ Missing field → 500 DataComputeError
  ✗ Invalid calculation → 500 ComputeException
```

### **Stage 5: Rule Engine (32 Labels)**
```
Input: FactSet (74 facts)

32 Rules Evaluated:
  Rule 1: IF overall_utilization > 0.90 → FIRE maxed_out
  Rule 2: IF n_lates_90_24mo > 0 → FIRE major_delinquency
  Rule 3: IF dti_ratio > 0.36 → FIRE high_dti
  Rule 4: IF dti_ratio > 0.50 → FIRE severe_dti
  Rule 5: IF n_lates_90_24mo == 0 AND score > 700 → FIRE perfect_payment
  ...
  Rule 32: IF is_disputable AND status == open → FIRE disputable_collection

Fired Labels (11 for Anjali):
  1. high_utilization (priority 2)
  2. perfect_payment (priority 1)
  3. disputable_collection (priority 3)
  4. score_falling (priority 4)
  5. unused_revolving_cards (priority 5)
  6-11. [6 more labels]

Error Handling:
  ✗ Rule evaluation error → 500 RuleEvaluationError
```

### **Stage 6: Label Knowledge Base Ingestion**
```
Input: FiredLabels (11 labels)

For Each Label, Fetch KB:
  label_id: high_utilization
  ├─ mitigation_steps:
  │   1. Lower balance on highest-util card
  │   2. Request credit limit increase
  │   3. Avoid new hard inquiries
  ├─ facts_to_cite: [overall_utilization, total_balance_paise, credit_limit_paise]
  ├─ cibil_reason_codes: [RC-07, RC-08]
  ├─ sources: [CIBIL Score Factors, RBI Guidelines]
  └─ personalized_template: Your utilization is at {util}%...

Output: Enriched context with citations

Error Handling:
  ✗ KB file missing → 503 KBUnavailable
  ✗ Label not in KB → warn (non-blocking, use generic)
```

### **Stage 7: Prompt Assembly**
```
System Prompt (951 chars):
  "You are a CIBIL credit coach. You ONLY use provided facts.
   Never invent numbers. Always cite specific amounts in paise.
   Use INR formatting: ₹50,000 not $50,000.
   Use CIBIL terminology (not FICO).
   Output format: 1) Score, 2) What to Fix, 3) How to Fix, 4) What to Avoid"

User Message (7,798 chars):
  "Customer: Anjali (PAN masked)
   Score: 715 (Good)
   Income: ₹100,000/month
   
   Fired Labels:
   1. high_utilization: Overall util 70% (₹4,20,000 of ₹6,00,000)
   2. perfect_payment: No lates in 24 months
   3. disputable_collection: 1 medical collection, open
   ...
   
   Facts:
   • DTI: 0.20 (20%) — manageable
   • Credit age: 36 months (good)
   • Inquiries: 2 in 6mo
   
   Provide personalized analysis with specific numbers."

Error Handling:
  ✗ Prompt too large → 413 PayloadTooLarge
  ✗ Missing context → 500 PromptBuilderError
```

### **Stage 8: LLM Invocation**
```
Service: OpenAI
Model: gpt-4o-mini
Parameters:
  temperature: 0.3 (deterministic, not creative)
  max_tokens: 1000
  timeout: 30 seconds

Request:
  POST https://api.openai.com/v1/chat/completions
  {
    "model": "gpt-4o-mini",
    "temperature": 0.3,
    "messages": [
      {"role": "system", "content": system_prompt},
      {"role": "user", "content": user_message}
    ]
  }

Response:
  "Based on your 715 CIBIL score (Good band), here's my analysis:
   
   1. SCORE & BAND: Your 715 places you in Good — solid for most products.
   
   2. WHAT TO FIX FIRST: High utilization (70%). Your credit limit is ₹6,00,000
      but balance is ₹4,20,000. This impacts your score.
   
   3. HOW TO FIX:
      • Pay down HDFC card balance by ₹1,50,000 to reach 50% utilization
      • Request credit limit increase (easier with perfect payment history)
      • Don't apply for new cards in next 3 months
   
   4. WHAT TO AVOID:
      • Hard inquiries (clusters 2+ in 30 days = rate shopping)
      • Missed payments (you have perfect record — keep it)
      • Closing old cards (oldest is 36 months, valuable)"

Error Handling:
  ✗ API key invalid → 401 Unauthorized → 500 LLMError
  ✗ Rate limited → 429 → 503 LLMError (retry)
  ✗ Timeout (> 30s) → 504 LLMTimeout
  ✗ Model unavailable → 503 LLMError
```

### **Stage 9: Citation Verification**
```
Input: LLM Response + FactSet

Verify Each Claim:
  Claim: "Your balance is ₹4,20,000"
  ✓ Source: FactSet.total_balance_paise = 420000
  ✓ Cite: account_id = acc_001_1, display_name = HDFC Millennia
  
  Claim: "Perfect payment history"
  ✓ Source: FactSet.n_lates_90_24mo = 0
  ✓ Cite: All 24 months = 0
  
  Claim: "Oldest account is 36 months"
  ✓ Source: FactSet.oldest_account_months = 36
  ✓ Cite: HDFC Millennia, opened 2021-03-15

Output: Annotated response with citations

Error Handling:
  ✗ Claim not in FactSet → warn (add [UNCITED] tag, non-blocking)
  ✗ Math error in citation → warn (log for audit)
```

### **Stage 10: Web Delivery (SSE Streaming)**
```
Response Format: Server-Sent Events

Event 1: Metadata
  data: {
    "type": "metadata",
    "session_id": "ABCPS1234A_2026-07-25T19:07:27Z",
    "score": 715,
    "band": "Good",
    "labels_fired": 11
  }

Events 2-N: Token Streaming
  data: {"type": "token", "content": "Based on your"}
  data: {"type": "token", "content": " 715 CIBIL"}
  data: {"type": "token", "content": " score (Good band)..."}

Final Event: Done
  data: {"type": "done", "session_id": "ABCPS1234A_2026-07-25T19:07:27Z"}

Browser Handling:
  • Display score card immediately (metadata)
  • Stream tokens in real-time (append as they arrive)
  • Store session in localStorage (persist on page refresh)
  • Show in "Previous Sessions" history

Error Handling:
  ✗ Network interrupted → Show error box, retry option
  ✗ LLM error during stream → Send error event, stop stream
  ✗ Invalid JSON in stream → Log, skip, continue
```

---

## ⚠️ Error Handling Summary

| Stage | Error | HTTP | Action |
|-------|-------|------|--------|
| **Validation** | Invalid PAN format | 400 | Reject input, show format hint |
| **DB Query** | PAN not found | 404 | Show "Wrong PAN Number" |
| **PII** | Leak detected | 500 | Log incident, reject response |
| **Precompute** | Calc error | 500 | Log, return 500 error |
| **Rules** | Eval error | 500 | Log, return 500 error |
| **KB** | File missing | 503 | Use generic advice, warn user |
| **Prompt** | Too large | 413 | Truncate context, retry |
| **LLM API** | Invalid key | 401 | Check .env, show setup help |
| **LLM API** | Rate limit | 429 | Retry after 60s |
| **LLM API** | Timeout | 504 | Show "Analysis taking longer..." |
| **Citation** | Uncited claim | warn | Tag as [UNCITED], log for review |
| **Stream** | Network fail | error | Retry from last position |

---

## 📈 Performance Metrics (Example: ABCPS1234A)

```
Stage                      Time        Data Size
─────────────────────────────────────────────────
1. Validation              < 1ms       PAN + income
2. DB Query                ~2ms        CustomerRecord (4 accounts, 3 inquiries, 1 collection)
3. PII Masking             < 1ms       SanitisedRecord
4. Precompute (74 facts)   ~10ms       FactSet (74 fields)
5. Rule Engine (32 labels) ~5ms        FiredLabels (11 fired)
6. KB Ingestion            ~3ms        Enriched context
7. Prompt Assembly         ~2ms        System (951 chars) + User (7,798 chars)
8. LLM Invocation          2-5 sec     GPT-4o-mini response
9. Citation Verify         ~5ms        Annotated output
10. Streaming              100-500ms   SSE delivery
─────────────────────────────────────────────────
Total (no LLM)             ~30ms
Total (with LLM)           2-5 sec
```

---

## 📚 Key Attributes at Each Stage

| Stage | Key Attributes |
|-------|---|
| **DB Query** | customer_id, first_name, pan_card, score, accounts[], inquiries[], collections[] |
| **Precompute** | score, overall_utilization, dti_ratio, n_lates_90_24mo, inquiries_6mo, is_high_dti |
| **Rule Engine** | label_id, priority, evidence_facts, account_id (if per-account) |
| **Labeler/KB** | display_name, mitigation_steps, facts_to_cite, cibil_reason_codes, sources |
| **Prompt** | system_prompt, user_message, facts_context, fired_labels_context |
| **LLM Response** | what_to_fix_first, how_to_fix, what_to_avoid, citations[] |
| **Final** | session_id, score, band, analysis, citations, timestamp |

---

## 🎯 Example: Full Log for ABCPS1234A, Income ₹100,000

```
[19:07:27.100] Web Request: POST /api/analyze
  ├─ PAN: ABCPS1234A
  └─ Income: 100000 (INR)

[19:07:27.101] Validation ✓
  ├─ PAN format valid: ABCPS1234A
  └─ Income valid: 100000 > 0

[19:07:27.103] DB Query ✓
  ├─ Customer found: Anjali (cust_001)
  ├─ Score: 715 (Good)
  ├─ Accounts: 4
  ├─ Inquiries: 3
  ├─ Collections: 1
  └─ Public Records: 0

[19:07:27.104] PII Masking ✓
  ├─ pan_masked: ABCDE****F
  ├─ first_name_opt: null
  └─ dob_year_opt: null

[19:07:27.115] Precompute (74 facts) ✓
  ├─ score: 715
  ├─ overall_utilization: 0.70
  ├─ dti_ratio: 0.20
  ├─ n_lates_90_24mo: 0
  ├─ score_trend: falling
  ├─ thin_file: false
  ├─ n_collections: 1
  ├─ is_disputable: true
  ├─ inquiries_6mo: 2
  ├─ is_high_dti: false
  └─ ...64 more facts

[19:07:27.120] Rule Engine (32 rules) ✓
  ├─ Rule: overall_utilization > 0.90 → NO
  ├─ Rule: n_lates_90_24mo > 0 → NO
  ├─ Rule: n_lates_90_24mo == 0 AND score > 700 → YES (perfect_payment)
  ├─ Rule: overall_utilization > 0.60 → YES (high_utilization)
  ├─ Rule: is_disputable AND open → YES (disputable_collection)
  ├─ Fired Labels: 11
  └─ Label IDs: high_utilization, perfect_payment, disputable_collection, score_falling, ...

[19:07:27.123] KB Ingestion ✓
  ├─ Label: high_utilization
  │  ├─ Mitigation: Lower balance, request increase, avoid inquiries
  │  ├─ Facts to cite: overall_utilization, total_balance_paise, credit_limit_paise
  │  └─ Sources: CIBIL Score Factors, RBI Guidelines
  ├─ Label: perfect_payment
  │  ├─ Mitigation: Maintain streak, no late payments
  │  └─ Facts to cite: n_lates_90_24mo, n_lates_24mo
  └─ [9 more labels with KB entries]

[19:07:27.126] Prompt Builder ✓
  ├─ System prompt: 951 chars
  ├─ User message: 7,798 chars
  ├─ Facts context: 74 fields
  ├─ Fired labels: 11 with evidence
  └─ KB context: Mitigation steps for each

[19:07:27.200] LLM Invocation ✓
  ├─ Service: OpenAI
  ├─ Model: gpt-4o-mini
  ├─ Temperature: 0.3
  ├─ Tokens generated: 287
  └─ Duration: 2.1 seconds

[19:07:29.300] Citation Verification ✓
  ├─ Claim: "₹4,20,000" → ✓ Verified (total_balance_paise)
  ├─ Claim: "70% utilization" → ✓ Verified (0.70 * 100)
  ├─ Claim: "Perfect payment" → ✓ Verified (n_lates_90_24mo == 0)
  ├─ Claim: "36 months old" → ✓ Verified (oldest_account_months)
  └─ All claims cited: 12/12

[19:07:29.305] Stream Response ✓
  ├─ Session ID: ABCPS1234A_2026-07-25T19:07:27Z
  ├─ Score: 715 (Good)
  ├─ Labels fired: 11
  ├─ Tokens streamed: 287
  ├─ Content-Type: text/event-stream
  └─ Delivery: Server-Sent Events (SSE)

[19:07:29.500] Browser Response ✓
  ├─ Display score card: 715 / Good
  ├─ Stream analysis text in real-time
  ├─ Save session to localStorage
  ├─ Update "Previous Sessions" UI
  └─ Total time: 2.4 seconds

✅ COMPLETE SUCCESS
```

---

**Status:** Full pipeline documented with error handling, data flow, and real example (ABCPS1234A, ₹100,000).
