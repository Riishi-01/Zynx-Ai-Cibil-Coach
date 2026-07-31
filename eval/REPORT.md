# Chat RAG eval — local run report

This note documents the offline eval carried out after the chat RAG build.
Three artefacts live alongside the source:

* `scripts/eval_chat_local.py` — runs `/api/chat` against a `run_pipeline`
  fixture, embeds the question via a deterministic in-process encoder
  (no API key), runs the **real** pre-check, retrieval, prompt build, and
  citation extraction against the bundled artifacts, then grades against
  `eval/chat_cases.json`.
* `scripts/eval_real_pipeline.py` — uses the real `app.chat_rag.retrieve`,
  `app.guardrails.is_in_scope`, and `app.citations_chat.extract_citations`
  against a canned answer template per case. This proves the runtime
  pipeline works end-to-end without an LLM call.
* `scripts/eval_chat.py` — the live SSE grader originally specified in
  the build prompt; requires `OPENAI_API_KEY` and a running `/api/chat`.

## Vercel bundle

```
+----------------------------+----------------+
| Asset                      |  Size          |
+----------------------------+----------------+
| api/requirements.txt deps  |  ~50 MiB       |
| app/chat_kb_data.py        |  416 KiB       |
| app/chat_guardrail_data.py |  196 KiB       |
| app source                 |  ~80 KiB       |
+----------------------------+----------------+
```

The Python runtime adds roughly 40 MiB once stdlib + CPython + the
requested packages are factored in, leaving the production bundle at
~90 MiB — well under the 225 MB Vercel Hobby cap. The chat RAG
artifacts are committed (verified) so the deploy step never re-embeds.

## Pipeline verification

* `pytest tests/ -q` — 327 passed, 1 skipped (windowed STREAMING test).
* `npm test` — 119 passed across 11 files.
* `npm run lint` — 0 warnings, 0 errors.
* `npx tsc -b` — clean.

## Eval takeaways

The offline harness reproduces the full pipeline shape but cannot
evaluate semantic recall without real embeddings. Calibration of the
`0.05` guardrail margin and the retrieval margin is therefore deferred
to `scripts/eval_chat.py`, which must run against a live `/api/chat`.

| Stage             | Status                                                                                          |
|-------------------|-------------------------------------------------------------------------------------------------|
| Embedding         | Lazy `Embedder` reuses the bundled 1536-d vectors — green.                                       |
| Pre-check         | Returns `in / out / ambiguous`. Defaults to **in** when ambiguous, per the build prompt.        |
| Retrieval         | `retrieve(question_vec, k=5)` returns ranked chunks from the committed index.                   |
| Citations         | `extract_citations` returns ordered, de-duped `ChatCitation` records limited to top-K labels.   |
| Prompt            | `build_chat_prompt` accepts `Sequence[Retrieval]` and inserts the retrieved block.             |
| Endpoint SSE      | `guardrail → token → done` for out-of-scope, `guardrail → replace → done` for post-check.       |
| Frontend          | Composer textarea, citations pills, two-stream `ChatPane`, full TS / lint clean.                |

Production readiness hinges on running `scripts/eval_chat.py` against a
real `/api/chat` and tuning the guardrail margin against observed
ambiguous-band traffic.
