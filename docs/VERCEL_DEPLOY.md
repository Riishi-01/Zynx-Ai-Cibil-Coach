# Vercel Deploy Debugging Runbook

One-page triage for when the production deployment misbehaves. The app runs as:
- **Static frontend** built by `cd frontend && npm run build`, served from `frontend/dist` via Vercel's CDN.
- **Python serverless function** at `api/index.py` (ASGI, exposes `app` from `app/web.py`), routed via `vercel.json` rewrites for `/api/*`.
- **Supabase Postgres** for customer data + knowledge base; `supabase-py` REST client.

Three things can break: build, deploy, runtime. Each has its own diagnostic.

---

## 1. Build fails — `Command "cd frontend && npm install … && npm run build" exited with 2`

### 1a. TypeScript error like `TS2307: Cannot find module '../../data/customers'`

**Root cause**: A `.vercelignore` pattern is shadowing a required frontend source file. `.vercelignore` uses gitignore semantics — unanchored patterns match **anywhere in the tree**.

**Diagnostic**:

```bash
git ls-files | grep -E "<the missing module path>"
```

If the file is tracked in git, it's a `.vercelignore` problem (or `vercel.json` `functions.*.excludeFiles`).

**Fix**: prefer `vercel.json` `excludeFiles` (scoped to the Python function bundle) over `.vercelignore` (project-wide upload filter that can silently strip source files). Anchor root-level patterns with `/` if you must use `.vercelignore`.

### 1b. TypeScript error like `TS7006: Parameter X implicitly has an 'any' type`

Almost always downstream from `TS2307` (missing module → imports become `any` → lambdas have untyped parameters). Fix the missing-module root cause.

### 1c. Bundle too large — `Error: Total bundle size (XXX MB) exceeds the maximum function size (225 MB)`

Hits the Python function when `api/requirements.txt` (and its transitive deps) inflates the unzipped bundle.

**Mitigations, in order of effort**:

1. **Drop unused top-level imports** — every transitive dep pulled in counts. Audit `app/*.py` for imports only used on one code path.
2. **Lazy-load heavy deps** — guard `from sqlalchemy import …`, `from openai import …`, `from langchain import …` inside functions. Top-level imports are pulled into the bundle even if the function is never called.
3. **Slim `api/requirements.txt`** — keep only what the runtime path actually imports. Local dev uses the bigger `requirements.txt`; Vercel uses `api/requirements.txt`.
4. **Check the `excludeFiles` glob in `vercel.json`** — must stay under 256 characters. Trim paths when adding new ones.

Current size budget (~111 MB unzipped) is in `api/requirements.txt` docstring — keep that honest.

---

## 2. Deploy succeeds but the page is blank / chart cards stay skeleton

Layout renders, `/api/analyze` returns no `event: canvas` frame. The frontend is fine; the serverless function is failing silently (no SSE bytes sent).

### 2a. First stop: hit `/api/health`

```bash
curl -sS https://<your-app>.vercel.app/api/health | jq
```

Healthy response looks like:

```json
{
  "status": "healthy",
  "service": "CIBIL Credit Coach",
  "backend": "supabase",
  "env": {
    "supabase_url_set": true,
    "supabase_key_set": true,
    "openai_key_set": true
  }
}
```

Diagnostic matrix:

| `backend` | `supabase_url_set` | `supabase_key_set` | `openai_key_set` | Diagnosis |
|---|---|---|---|---|
| `sqlite` | * | * | * | Supabase env vars not picked up at cold-start. Check Vercel **Settings → Environment Variables**, ensure each var targets **Production** (not just Preview/Development). |
| `supabase` | `false` | * | * | `SUPABASE_URL` missing. |
| `supabase` | `true` | `false` | * | Service-role key missing (accepts either `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`). |
| `supabase` | `true` | `true` | `false` | `OPENAI_API_KEY` missing — canvas will still hydrate (deterministic), but the plan LLM call will fail. |
| `supabase` | `true` | `true` | `true` | Env is fine. Move to §2b. |

### 2b. Env is fine but still no canvas → check Supabase data

```bash
# After exporting SUPABASE_URL + a service-role key locally:
python scripts/verify_supabase_data.py
```

If it prints `All row counts match.` → DB is seeded; move to §2c.

If it errors or shows zero rows → the DB is empty. Seed it:

```bash
python scripts/export_sqlite_to_supabase.py    # writes data/supabase_seed.json
python scripts/import_to_supabase.py           # bulk-inserts ~418 rows
python scripts/verify_supabase_data.py         # confirm
```

Then redeploy Vercel (push any commit or click Redeploy).

### 2c. DB is fine but `/api/analyze` still fails → read Vercel runtime logs

Vercel dashboard → Deployments → click latest successful build → **Runtime Logs**. Look for the POST `/api/analyze` entry. Common failures:

- **`RuntimeError: SupabaseRepository requires SUPABASE_URL`** — env vars dropped at runtime despite being set (usually a target-environment mismatch; see §2a).
- **`KBUnavailable`** (HTTP 503) — `kb_labels` table is empty. Re-run `scripts/import_to_supabase.py`.
- **`CustomerNotFound`** (HTTP 404) — `customers` table is empty. Same fix.
- **`openai.AuthenticationError`** — bad `OPENAI_API_KEY`. Test with `curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"`.
- **Cold-start timeout (5–8s on first request, 504 on retry)** — expected on Vercel free tier; subsequent requests are warm.

### 2d. Direct curl test

```bash
curl -i -X POST https://<your-app>.vercel.app/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"pan":"ABCPS1234A","income":75000}'
```

- **`Content-Type: text/event-stream`** + first frame is `event: canvas\ndata: …` → backend is fine; frontend SSE consumption bug (rare; check `frontend/src/hooks/useStream.ts`).
- **`text/event-stream`** + first frame is `event: error\ndata: …` → backend ran but hit an error mid-stream. Read `error.message`.
- **`application/json` with `{"detail": "..."}`** → request never streamed; check the status code:
  - `400` → bad PAN format.
  - `403` → Turnstile rejected (only if `TURNSTILE_SECRET_KEY` is set; otherwise the gate is open).
  - `404` → `CustomerNotFound` (no row for that PAN).
  - `500` → unhandled Python exception; full stack trace in runtime logs.
  - `503` → `KBUnavailable`.

---

## 3. SSE works but the LLM plan never finishes / streams empty

The canvas frame hydrated (so `/api/analyze` reached the SSE generator), but no `plan_delta` events arrive, or `metadata` is missing.

### 3a. Check the model name in env

`app/config.py:63` reads `OPENAI_MODEL`, default `gpt-4o-mini`. If the env overrides it with a model that doesn't support `response_format={"type": "json_object"}` or `stream_options={"include_usage": True}`, the call hangs or fails. Stick to `gpt-4o-mini`, `gpt-4o`, `gpt-4.1-mini`, etc.

### 3b. Check the LLM is actually generating

The first token from OpenAI should land within ~3 seconds. If the canvas frame is there but `plan_delta` doesn't show up for 30 seconds, OpenAI is the bottleneck. Check OpenAI status page.

### 3c. Check token budget

`app/config.py:66` reads `LLM_MAX_TOKENS`, default `1100`. If set too low, the JSON may truncate mid-stream and never emit `done`. Bump it to `1500` if plans are getting cut off.

---

## 4. Things that should NOT be touched

- **`vercel.json` rewrites** — `/api/:path* → /api/index.py` and `/:path* → /index.html`. The SPA fallback is what makes the frontend route on hard refresh; don't remove it.
- **CORS** — `app/web.py:36` allows `*`. The frontend and backend share a Vercel domain in production, so this isn't strictly necessary, but it's harmless.
- **`X-Accel-Buffering: no`** in `_SSE_HEADERS` — without this, Vercel's reverse proxy buffers the entire stream before sending it. The frontend then sees nothing until the function completes (which never happens for a streaming SSE response).

---

## 5. Pre-deploy checklist

Before every push to `production`:

```bash
cd frontend && npm run build && npm run lint && npm test
PYTHONPATH=. pytest tests/ -q
```

Both must pass. Then `git push zynx production:main`. After Vercel deploys:

```bash
curl -sS https://<your-app>.vercel.app/api/health | jq
curl -i -X POST https://<your-app>.vercel.app/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"pan":"ABCPS1234A","income":75000}' | head -3
```

Expect `backend: "supabase"`, all envs `set: true`, and an `event: canvas` frame within ~500 ms.