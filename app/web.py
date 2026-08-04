"""FastAPI web server with streaming structured LLM output."""

import os
import json
import logging
import dataclasses
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from app.data_fetch import fetch_customer_by_pan
from app.pii_parser import sanitise_record
from app.precompute import precompute_facts
from app.rule_engine import fire_labels
from app.prompt_builder import build_prompt, build_chat_prompt
from app.llm_stream import astream_plan, astream_chat
from app.citations import cite_plan
from app.chat_rag import TOP_K as CHAT_TOP_K, retrieve
from app.citations_chat import ChatCitation, extract_citations
from app.embeddings import Embedder
from app.guardrails import (
    ScopeGuard,
    check_response,
    contains_out_of_scope_terms,
)
from app.label_service import build_labels_response, run_pipeline
from app.canvas_service import build_canvas_response
from app.api_schemas import LabelsResponse, CanvasResponse
from app.schemas import InvalidPAN, CustomerNotFound, LLMError, KBUnavailable

# Initialize FastAPI app
app = FastAPI(
    title="CIBIL Credit Coach",
    description="AI-powered credit analysis engine for Indian credit profiles",
    version="1.0.0",
)

# Enable CORS. The wildcard origin is fine for this portfolio demo — both
# the frontend and the backend live on the same Vercel domain in production
# (no cross-origin requests in practice). If you ever split them, restrict
# allow_origins to the deployed frontend URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Streaming headers. X-Accel-Buffering disables nginx response buffering, without
# which a reverse proxy holds the stream until it completes.
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


# =========================================================== observability ==
#
# LangSmith is the observability layer for LLM calls. The env vars below are
# the standard LangChain tracing variables — when LANGCHAIN_API_KEY is set,
# every LangChain chain (incl. our ChatOpenAI wrapper in llm_stream.py) is
# auto-traced. When unset, LangChain runs without tracing and there is no
# overhead. Local dev defaults to no tracing; production sets the key in
# Vercel env vars.
_LANGSMITH_ENABLED = bool(os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY"))
if _LANGSMITH_ENABLED:
    # LangChain reads these from os.environ at chain construction time. They
    # have to be set before the first ChatOpenAI() call — typically the first
    # request after the function cold-starts.
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", os.environ.get("LANGCHAIN_API_KEY") or os.environ["LANGSMITH_API_KEY"])
    os.environ.setdefault("LANGCHAIN_PROJECT", os.environ.get("LANGSMITH_PROJECT", "cibil-coach"))
    logging.info("LangSmith tracing enabled (project=%s)", os.environ["LANGCHAIN_PROJECT"])


# =============================================================== turnstile ==
#
# Cloudflare Turnstile is the bot gate. When TURNSTILE_SECRET_KEY is set the
# /api/analyze and /api/chat endpoints verify the token from the request body
# against Cloudflare's siteverify API. When unset, the verify call returns
# True (no gate) so local dev and the Phase 1 deploy work without it.
#
# Phase 2 (after first deploy): add VITE_TURNSTILE_SITE_KEY + TURNSTILE_SECRET_KEY
# to Vercel env vars once the production URL is registered on Cloudflare.
import httpx

_TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET_KEY")
_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: Optional[str], ip: Optional[str]) -> bool:
    """Verify a Turnstile token with Cloudflare. Returns True when the gate
    is disabled (no TURNSTILE_SECRET_KEY configured).

    The "no key -> True" behaviour is the env-gate: every code path that calls
    this can ignore the return value when the gate is off, and the same
    endpoint stays protected when the key is set.
    """
    if not _TURNSTILE_SECRET:
        return True
    if not token:
        return False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                _TURNSTILE_VERIFY_URL,
                data={
                    "secret": _TURNSTILE_SECRET,
                    "response": token,
                    "remoteip": ip or "",
                },
            )
            response.raise_for_status()
            return bool(response.json().get("success", False))
    except Exception as exc:
        # Fail closed: a Cloudflare outage should not silently disable the gate.
        logging.warning("Turnstile verify failed: %s", exc)
        return False


def _turnstile_enabled() -> bool:
    """True when the Turnstile gate is actively enforcing."""
    return bool(_TURNSTILE_SECRET)


def _sse(event: str, data: Any) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


CHAT_OUT_OF_SCOPE_MESSAGE = (
    "I'm your credit coach, so I can only help with credit report "
    "questions — score, utilization, payment history, collections, and "
    "similar. I can't advise on investments, career, housing, or tax "
    "planning. Want to ask something credit-related instead?"
)

CHAT_MAX_QUESTION_CHARS = 1000
CHAT_MAX_HISTORY_TURNS = 6

_embedder: "Embedder | None" = None


def _get_embedder() -> Embedder:
    """Lazily construct a single Embedder per cold-start.

    Importing the OpenAI SDK is deferred until the first chat request so the
    module stays importable without ``OPENAI_API_KEY`` (tests rely on this).
    """
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def _reset_embedder_for_tests() -> None:
    """Test seam — drop the cached embedder so monkeypatched fakes take effect."""
    global _embedder
    _embedder = None


# Note: the Vite-built frontend in `frontend/dist/` is served by Vercel's CDN
# via the `outputDirectory` in vercel.json, NOT by this FastAPI app. Keeping
# `/` and `/assets` out of the function avoids dead code at cold-start and
# lets Vercel's edge cache handle static assets efficiently.


@app.post("/api/analyze")
async def analyze_customer(request: Request):
    """Analyse a customer and stream the result as Server-Sent Events.

    Event order matters:

      1. `canvas`     — the full deterministic payload (score, utilisation,
                        heatmap, all 32 labels). Emitted immediately, so the UI
                        renders charts without waiting on the model.
      2. `plan_delta` — the coaching plan as progressively complete JSON, from
                        JsonOutputParser under .astream().
      3. `metadata`   — {model, prompt_tokens, completion_tokens} captured from
                        LangChain's usage_metadata callback on the final AIMessage.
      4. `citations`  — figures in the plan traced back to precomputed facts.
      5. `done`       — terminal.

    An `error` event is emitted instead of 3/4 if generation fails; the canvas
    has already been delivered by then, so the UI degrades to charts-only.

    Body: {"pan": "ABCPS1234A", "income": 75000, "turnstile_token": "..." (optional)}
    """
    body = await request.json()
    await _enforce_turnstile(request, body)
    pan, income_inr = _parse_analysis_body(body)

    # Everything deterministic happens up front, so failures surface as proper
    # HTTP status codes rather than mid-stream errors.
    try:
        canvas = build_canvas_response(pan, monthly_income_inr=income_inr)
        _record, sanitised, facts, fired, _first_name = run_pipeline(pan, income_inr)
    except InvalidPAN as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CustomerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KBUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    system_prompt, user_message = build_prompt(sanitised, facts, fired)

    async def event_stream() -> AsyncGenerator[str, None]:
        yield _sse("canvas", canvas.model_dump(mode="json"))

        plan: dict = {}
        try:
            async for kind, data in astream_plan(system_prompt, user_message):
                if kind == "plan":
                    plan = data
                    yield _sse("plan_delta", data)
                elif kind == "metadata":
                    yield _sse("metadata", data)

            if plan:
                citations = cite_plan(plan, facts, fired)
                yield _sse(
                    "citations",
                    {"citations": [c.model_dump(mode="json") for c in citations]},
                )

                report = check_response(plan, facts, sanitised)
                if not report.overall_pass:
                    logging.warning(
                        "guardrail_failures",
                        extra={
                            "pan": pan,
                            "endpoint": "analyze",
                            "report": dataclasses.asdict(report),
                        },
                    )

            yield _sse("done", {"ok": True})

        except LLMError as exc:
            yield _sse("error", {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001 - surface any failure to the client
            yield _sse("error", {"message": f"Unexpected error: {exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


def _normalize_history(raw_history: list) -> tuple[list[dict], str | None]:
    """Validate the optional history list and return a trimmed version.

    Returns ``(history, error)`` — exactly one is meaningful. The trimmed
    history is capped to ``CHAT_MAX_HISTORY_TURNS`` completed pairs and
    cleaned to ``{role, content}`` shape.
    """
    cleaned: list[dict] = []
    for index, entry in enumerate(raw_history):
        if not isinstance(entry, dict):
            return [], f"history[{index}] must be an object"
        role = str(entry.get("role", "")).lower()
        if role not in {"user", "assistant"}:
            return [], f"history[{index}].role must be 'user' or 'assistant'"
        content = entry.get("content")
        if not isinstance(content, str):
            return [], f"history[{index}].content must be a string"
        cleaned.append({"role": role, "content": content})
    if len(cleaned) > CHAT_MAX_HISTORY_TURNS * 2:
        cleaned = cleaned[-(CHAT_MAX_HISTORY_TURNS * 2):]
    return cleaned, None


async def _emit_guardrail_redirect(reason: str) -> AsyncGenerator[str, None]:
    """Stream the fixed out-of-scope message in place of an LLM call.

    Emits a guardrail metadata event, then a single ``token`` event with the
    canonical copy, then ``done``. The frontend uses the guardrail event to
    decide whether to render the redirect as an answer or as a transient
    notice.
    """
    yield _sse(
        "guardrail",
        {
            "verdict": "out_of_scope",
            "reason": reason,
        },
    )
    yield _sse("token", {"content": CHAT_OUT_OF_SCOPE_MESSAGE})
    yield _sse("done", {"ok": True})


async def _embed_question(question: str) -> tuple[float, ...]:
    embedder = _get_embedder()
    return await embedder.embed(question)


@app.post("/api/chat")
async def chat_followup(request: Request):
    """Answer a follow-up question, streaming markdown as SSE.

    Body: {"pan": ..., "income": ..., "message": "...", "history": [...], "turnstile_token": "..." (optional)}
    History entries are {"role": "user"|"assistant", "content": "..."}.

    Event order::

        guardrail? token* replace?  citations? done
        (guardrail only when the question is out of scope)
        (replace only when the post-check regex trips mid-stream)

    The endpoint always returns ``text/event-stream`` 200 on success, even
    for out-of-scope questions, so the frontend ``useStream`` parser doesn't
    need to fork on content-type.
    """
    body = await request.json()
    await _enforce_turnstile(request, body)
    pan, income_inr = _parse_analysis_body(body)

    question = str(body.get("message", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="message is required")
    if len(question) > CHAT_MAX_QUESTION_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"message must be {CHAT_MAX_QUESTION_CHARS} chars or fewer",
        )

    raw_history = body.get("history") or []
    if not isinstance(raw_history, list):
        raise HTTPException(status_code=400, detail="history must be a list")
    history, history_error = _normalize_history(raw_history)
    if history_error:
        raise HTTPException(status_code=400, detail=history_error)

    try:
        _record, sanitised, facts, fired, _first_name = run_pipeline(pan, income_inr)
    except InvalidPAN as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CustomerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KBUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            question_vec = await _embed_question(question)
        except LLMError as exc:
            yield _sse("error", {"message": f"Embedding failed: {exc}"})
            return

        scope_guard = ScopeGuard()
        in_scope, reason, _confidence = await scope_guard.check(
            question, question_vec=question_vec
        )
        if not in_scope:
            async for frame in _emit_guardrail_redirect(reason):
                yield frame
            return

        retrieved = retrieve(question_vec, k=CHAT_TOP_K)
        retrieved_label_ids = tuple(item.label_id for item in retrieved)

        system_prompt, user_message = build_chat_prompt(
            sanitised,
            facts,
            fired,
            question,
            history,
            retrieved,
        )

        full_answer = ""
        replaced = False
        chat_metadata: dict | None = None
        try:
            async for item in astream_chat(system_prompt, user_message):
                # ``astream_chat`` yields strings during streaming and a
                # ``("metadata", {…})`` tuple at the end if usage was
                # reported. Detect the tuple shape and forward accordingly.
                if isinstance(item, tuple) and len(item) == 2 and item[0] == "metadata":
                    chat_metadata = item[1]
                    continue

                chunk = item
                if not replaced and contains_out_of_scope_terms(full_answer + chunk):
                    replaced = True
                    yield _sse(
                        "guardrail",
                        {"verdict": "out_of_scope", "reason": "post_check"},
                    )
                    yield _sse("replace", {"content": CHAT_OUT_OF_SCOPE_MESSAGE})
                    break
                full_answer += chunk
                yield _sse("token", {"content": chunk})
        except LLMError as exc:
            yield _sse("error", {"message": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": f"Unexpected error: {exc}"})
            return

        if not replaced and chat_metadata is not None:
            yield _sse("metadata", chat_metadata)

        citations: list[ChatCitation] = []
        if full_answer and not replaced:
            citations = extract_citations(
                full_answer,
                allowed_label_ids=retrieved_label_ids,
            )
            yield _sse(
                "citations",
                {"citations": [c.to_dict() for c in citations]},
            )

            report = check_response(full_answer, facts, sanitised)
            if not report.overall_pass:
                logging.warning(
                    "guardrail_failures",
                    extra={
                        "pan": pan,
                        "endpoint": "chat",
                        "report": dataclasses.asdict(report),
                    },
                )

        yield _sse("done", {"ok": True})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


def _parse_analysis_body(body: dict) -> tuple[str, Optional[int]]:
    """Validate the shared {pan, income} request body.

    Returns (pan, income_inr) with income None when not supplied.
    """
    pan = str(body.get("pan", "")).strip().upper()
    if not pan:
        raise HTTPException(status_code=400, detail="PAN is required")

    income_raw = body.get("income")
    income_inr = None
    if income_raw not in (None, ""):
        try:
            income_inr = int(income_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="income must be a whole number")
        if income_inr <= 0:
            raise HTTPException(status_code=400, detail="income must be > 0")

    return pan, income_inr


def _extract_turnstile_token(body: dict) -> Optional[str]:
    """Pull the Turnstile token from the request body if present.

    Optional in the body schema — when the gate is disabled (no TURNSTILE_SECRET_KEY
    in the env) the value is ignored, so existing callers that don't send the
    field keep working. The frontend sends it after Phase 2 Turnstile is wired up.
    """
    token = body.get("turnstile_token")
    return str(token).strip() if token else None


async def _enforce_turnstile(request: Request, body: dict) -> None:
    """Verify the Turnstile token from the body, if the gate is enabled.

    Raises HTTP 403 when the gate rejects the request. No-op when TURNSTILE_SECRET_KEY
    is unset (Phase 1 deploy before Turnstile is configured).
    """
    if not _turnstile_enabled():
        return
    ip = request.client.host if request.client else None
    token = _extract_turnstile_token(body)
    if not await verify_turnstile(token, ip):
        raise HTTPException(status_code=403, detail="Bot detected")


@app.post("/api/labels", response_model=LabelsResponse)
async def analyse_labels(request: Request) -> LabelsResponse:
    """Return the full 32-label diagnostic for a PAN.

    Deterministic and LLM-free: fetch -> sanitise -> precompute -> fire_labels,
    joined to knowledge base content with facts resolved to values.

    Body: {"pan": "ABCPS1234A", "income": 75000}
    `income` is optional; the customer's stored income is used when omitted.
    """
    pan, income_inr = _parse_analysis_body(await request.json())

    try:
        return build_labels_response(pan, monthly_income_inr=income_inr)
    except InvalidPAN as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CustomerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KBUnavailable as exc:
        # The KB lives in SQLite; an empty kb_labels table is an operator error.
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/canvas", response_model=CanvasResponse)
async def analyse_canvas(request: Request) -> CanvasResponse:
    """Return the deterministic canvas payload for a PAN.

    Score hero, 3-month trend, utilisation with per-card breakdown, 24-month
    payment heatmap, and the label diagnostic. No LLM, so the canvas can render
    before any coaching text has been generated.

    Body: {"pan": "ABCPS1234A", "income": 75000, "turnstile_token": "..." (optional)}
    """
    body = await request.json()
    await _enforce_turnstile(request, body)
    pan, income_inr = _parse_analysis_body(body)

    try:
        return build_canvas_response(pan, monthly_income_inr=income_inr)
    except InvalidPAN as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CustomerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KBUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/health")
async def health_check():
    """Health check endpoint.

    Reports which backend the app is talking to and whether the required env
    vars are present. Cheap, no DB round-trip — safe to call as a smoke test
    after every deploy. When `backend == "sqlite"` in production something is
    wrong (Supabase env vars were not picked up at cold-start).
    """
    from app.database import IS_POSTGRES

    supabase_url_set = bool(os.environ.get("SUPABASE_URL"))
    service_key_set = bool(
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
    )
    openai_set = bool(os.environ.get("OPENAI_API_KEY"))
    backend = "supabase" if (IS_POSTGRES or supabase_url_set) else "sqlite"

    return {
        "status": "healthy",
        "service": "CIBIL Credit Coach",
        "backend": backend,
        "env": {
            "supabase_url_set": supabase_url_set,
            "supabase_key_set": service_key_set,
            "openai_key_set": openai_set,
        },
    }


@app.get("/api/diag")
async def diagnose_gates(pan: str = "ABCPS1234A"):
    """Exercise the two upstream gates (DB fetch + precompute) end-to-end.

    If /api/canvas returns a hydration but no data, hit this endpoint to
    see exactly which gate is failing and how long each step takes. Safe to
    call from any browser — it does not invoke the LLM, does not require
    Turnstile, and never mutates state.

    Gates:
      1. customer fetch       (Supabase REST: customers + scores)
      2. KB load              (Supabase REST: kb_labels + 4 child tables)
      3. sanitise + precompute (pure Python, deterministic)

    Any failure surfaces as `{"ok": false, "gate": "<name>", "error": "..."}`
    with the upstream exception class and message so you can fix the right
    thing instead of guessing.
    """
    import time

    timings: dict[str, float] = {}
    started = time.perf_counter()

    # Gate 1: customer fetch
    try:
        t = time.perf_counter()
        record = fetch_customer_by_pan(pan)
        timings["fetch_customer_ms"] = round((time.perf_counter() - t) * 1000, 1)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "gate": "fetch_customer",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "pan": pan,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    # Gate 2: KB load (caches after first call, so this is also the cache test)
    try:
        t = time.perf_counter()
        from app.kb_loader import get_knowledge_base

        kb = get_knowledge_base()
        timings["load_kb_ms"] = round((time.perf_counter() - t) * 1000, 1)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "gate": "load_kb",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    # Gate 3: sanitise + precompute
    try:
        t = time.perf_counter()
        sanitised = sanitise_record(record)
        facts = precompute_facts(sanitised, monthly_income_inr=75000)
        timings["precompute_ms"] = round((time.perf_counter() - t) * 1000, 1)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "gate": "precompute",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    return {
        "ok": True,
        "pan": pan,
        "customer": {
            "first_name": record.customer.first_name,
            "score": record.score.score if record.score else None,
            "accounts": len(record.accounts),
            "inquiries": len(record.inquiries),
            "collections": len(record.collections),
        },
        "kb": {"labels": kb.count()},
        "facts": {
            "score": facts.score,
            "overall_utilization": round(facts.overall_utilization, 3),
            "worst_late_status": facts.worst_late_status,
            "n_recent_lates": facts.n_recent_lates,
        },
        "timings_ms": timings,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }
