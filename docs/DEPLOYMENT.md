# Deployment Runbook — CIBIL Credit Coach → Vercel + Supabase

Two-phase deploy from a fresh checkout. Phase 1 ships today; Phase 2 wires up bot protection after the public URL exists.

## Architecture at a glance

```
Browser (React + Vite, Vercel CDN)
   │  POST /api/analyze { pan, income, turnstile_token }
   ↓
Vercel Python function (api/index.py → app/web.py:app)
   │  ┌── verify_turnstile (Phase 2 only — env-gated)
   │  ├── pre-compute (74 features, pure Python)
   │  ├── rules engine → fired labels
   │  ├── build prompt
   │  ├── ChatOpenAI stream → JSON parser → SSE events
   │  └── verifier (numeric cross-check)
   │
   ↓ uses
Supabase Postgres (service_role key, server-side)
Cloudflare Turnstile (Phase 2 only)
OpenAI gpt-4o-mini
LangSmith (optional, auto-traces LangChain calls)
```

Customer data (23 PANs) and the knowledge base (32 labels, 106 mitigation steps, etc.) live in Supabase. The FastAPI app reads them via `app/supabase_repository.py` and `app/kb_loader.load_from_supabase()`.

---

## Phase 1 — first deploy (no Turnstile yet)

### 1. Create the Supabase project

1. Go to https://supabase.com → **New project**
2. Name: `cibil-credit-coach`
3. Database password: **save this somewhere safe** (you'll need it for `DATABASE_URL`)
4. Region: **Singapore** (closest to India)
5. Wait ~2 minutes for provisioning

### 2. Paste the schema

1. In your Supabase project: **SQL Editor → New query**
2. Open `docs/supabase_schema.sql` from this repo
3. Copy the entire file contents into the editor
4. Click **Run** (or `Ctrl/Cmd+Enter`)
5. Confirm: **Table Editor** should now show 13 tables (customers, scores, accounts, inquiries, collections, public_records, kb_labels, kb_mitigation_steps, kb_facts_to_cite, kb_reason_codes, kb_sources, kb_meta, requests)

### 3. Get the 3 Supabase keys

In your Supabase project: **Settings → API**

| Key | Variable name |
|---|---|
| Project URL | `SUPABASE_URL`, `VITE_SUPABASE_URL` |
| `anon` `public` | `SUPABASE_ANON_KEY`, `VITE_SUPABASE_ANON_KEY` |
| `service_role` `secret` | `SUPABASE_SERVICE_ROLE_KEY` (NEVER expose to frontend) |

### 4. Get the Supabase connection string (for `DATABASE_URL`)

**Settings → Database → Connection string → URI** tab. Pick **Direct connection** (not the pooler; the FastAPI app uses the supabase-py REST client, not psycopg, so this is only used by the supabase-py's REST endpoint).

Format:
```
postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

Note: the supabase-py client itself uses `SUPABASE_URL` (the REST endpoint), not `DATABASE_URL`. `DATABASE_URL` is used by SQLAlchemy only if you ever wire psycopg in. **For this deployment you can skip `DATABASE_URL`** — the FastAPI app uses `SUPABASE_URL` for everything via the supabase-py client. Leave `DATABASE_URL` unset unless you hit an issue that needs raw SQLAlchemy.

### 5. Export SQLite → seed JSON

On your local machine (with the project's `.venv` activated):

```bash
python scripts/export_sqlite_to_supabase.py
# writes data/supabase_seed.json (418 rows across 12 tables)
```

### 6. Import seed into Supabase

```bash
export SUPABASE_URL="https://xxxxxxxxxxxx.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="eyJ..."
python scripts/import_to_supabase.py
```

Expected output:
```
customers: inserted 23 rows
scores: inserted 23 rows
accounts: inserted 40 rows
...
Total: 418 rows across 12 tables
```

### 7. Verify parity

```bash
python scripts/verify_supabase_data.py
```

Should print `All row counts match.` plus the Anjali spot check. Exit code 0 = good.

### 8. Get the OpenAI key

Already in your `.env`. Copy to Vercel next.

### 9. (Optional) Get the LangSmith key

1. https://smith.langchain.com → sign up (free)
2. **Settings → API Keys → Create API Key**
3. Copy the key (starts with `lsv2_pt_…`)

Skip this if you don't want tracing.

### 10. Set Vercel env vars

In your Vercel project: **Settings → Environment Variables**. Add:

| Variable | Type | Value |
|---|---|---|
| `OPENAI_API_KEY` | Secret | `sk-…` |
| `SUPABASE_URL` | Plain | `https://xxx.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Secret | `eyJ…` |
| `SUPABASE_ANON_KEY` | Plain | `eyJ…` |
| `VITE_SUPABASE_URL` | Plain | `https://xxx.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Plain | `eyJ…` |
| `LANGCHAIN_API_KEY` | Secret (optional) | `lsv2_pt_…` |
| `LANGSMITH_PROJECT` | Plain (optional) | `cibil-coach` |

**Leave `TURNSTILE_SECRET_KEY` and `VITE_TURNSTILE_SITE_KEY` empty for Phase 1.** Without them, the bot gate short-circuits to True and the widget doesn't render.

For each variable, target all three environments: **Production**, **Preview**, **Development**.

### 11. Connect GitHub + set production branch

1. In Vercel: **Add New → Project → Import** your GitHub repo
2. **Framework Preset**: leave as `Other` (we provide `vercel.json`)
3. **Build Command**: leave the default (we override in `vercel.json`)
4. **Output Directory**: `frontend/dist` (overridden in `vercel.json`)
5. **Root Directory**: leave empty
6. **Environment Variables**: confirm the values from step 10 are picked up
7. Click **Deploy**

If Vercel asks for a production branch: change it to `production`.

### 12. First smoke test

Vercel gives you a URL like `https://cibil-credit-coach.vercel.app`.

1. Open it. The React app should load.
2. Type PAN `ABCPS1234A`, income `75000`, click **Analyze**
3. First SSE frame should be `event: canvas` (the charts hydrate). Within ~3-4s, `plan_delta` frames start arriving.
4. Check the browser DevTools Network tab: the response body shows `event: canvas` then `event: plan_delta …` frames.

If you see a clean run — Phase 1 is live.

### 13. (Optional) Confirm LangSmith

If you set `LANGCHAIN_API_KEY`: open https://smith.langchain.com → your project → **Runs**. You should see one trace per `/api/analyze` call, with the full prompt, completion, token counts, and latency.

---

## Phase 2 — Turnstile (after first deploy)

The Turnstile site key is bound to a specific domain. You can't register it before your URL exists, so this happens after Phase 1 ships.

### 1. Register the Vercel URL on Cloudflare

1. https://dash.cloudflare.com → **Turnstile → Add Site**
2. Site name: `CIBIL Credit Coach`
3. Domain: `cibil-credit-coach.vercel.app` (whatever Vercel gave you)
4. Widget Mode: **Invisible**
5. Click **Create**

You'll see two values:
- **Site Key** (starts with `0x4AAAAA…`) → `VITE_TURNSTILE_SITE_KEY`
- **Secret Key** (starts with `0x4AAAAA…`) → `TURNSTILE_SECRET_KEY`

### 2. Add the keys to Vercel

In your Vercel project: **Settings → Environment Variables**

| Variable | Value |
|---|---|
| `VITE_TURNSTILE_SITE_KEY` | `0x4AAAAA…` (site key) |
| `TURNSTILE_SECRET_KEY` | `0x4AAAAA…` (secret key) |

Target all three environments.

### 3. Redeploy

In Vercel: **Deployments → … → Redeploy**. The widget will mount on the form, and the backend will start verifying tokens. No code changes needed — the integration is env-gated.

### 4. Verify the gate

1. Open your Vercel URL
2. The form should look identical (Turnstile is invisible)
3. In DevTools → Network, the POST to `/api/analyze` should include `turnstile_token: "0.…"` in the body
4. Server-side, the response is normal — the gate is transparent to users

To verify the gate actually rejects bad tokens, hit your URL with curl and send a fake token:

```bash
curl -X POST https://your-app.vercel.app/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"pan":"ABCPS1234A","income":75000,"turnstile_token":"fake-token"}'
# → 403 {"detail":"Bot detected"}
```

If you get 403, the gate is live. ✅

---

## What's not changing

- `app/rule_engine.py` — the RULES_TABLE is the authority for which labels fire
- `app/prompt_builder.py`, `app/template_renderer.py`, `app/citations.py` — pure functions, backend-agnostic
- `app/schemas.py` — Pydantic, no SQL types
- The frontend components (`Canvas`, `Chat`, `MarkdownRenderer`, etc.) — only `InputForm.tsx` and `Analyzer.tsx` were touched for Turnstile
- `frontend/src/hooks/useStream.ts` — relative `/api/*` paths work on Vercel without changes

---

## Local dev after the migration

Without any env vars, the app still works exactly as before — SQLite is the default, the FastAPI app runs on `:8000` via `run_web.sh`, and Turnstile/LangSmith/Supabase are all no-ops. The Supabase code paths only activate when the corresponding env vars are set.

To smoke-test the Supabase path locally:

```bash
export DATABASE_URL="postgresql://..."   # optional
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="eyJ..."
export OPENAI_API_KEY="sk-..."
PYTHONPATH=. python -m uvicorn app.web:app --reload --port 8000
```

The frontend (Vite dev server on `:5173`) proxies `/api/*` to `:8000` per `frontend/vite.config.ts`. End-to-end behaviour matches production.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Build fails: `psycopg2-binary` build error | Python 3.14 incompatibility | Use `psycopg[binary]>=3.3.0` instead (already pinned in `api/requirements.txt`) |
| Function returns 500 immediately | Missing `OPENAI_API_KEY` env var | Add it in Vercel Environment Variables |
| `customer not found` for valid PAN | Migration didn't run, or wrong Supabase project | Re-run `scripts/import_to_supabase.py` and `scripts/verify_supabase_data.py` |
| LangSmith shows no traces | `LANGCHAIN_API_KEY` not set | Add it; restart Vercel function (push any commit or click Redeploy) |
| Turnstile widget doesn't mount | `VITE_TURNSTILE_SITE_KEY` not set or not exposed at build time | Confirm the var exists with no typos; rebuild |
| Cold start takes 5-8s on first request | Python runtime warming up | Expected on free tier; subsequent requests are warm |
| `Bot detected` 403 on all requests | Turnstile secret mismatch | Site key (frontend) and secret key (backend) must come from the same Cloudflare Turnstile widget |