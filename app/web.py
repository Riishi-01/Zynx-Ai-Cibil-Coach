"""FastAPI web server with streaming structured LLM output."""

import os
import json
import logging
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
        _record, sanitised, facts, fired = run_pipeline(pan, income_inr)
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


@app.post("/api/chat")
async def chat_followup(request: Request):
    """Answer a follow-up question, streaming markdown as SSE.

    Body: {"pan": ..., "income": ..., "message": "...", "history": [...], "turnstile_token": "..." (optional)}
    History entries are {"role": "user"|"assistant", "content": "..."}.
    """
    body = await request.json()
    await _enforce_turnstile(request, body)
    pan, income_inr = _parse_analysis_body(body)

    question = str(body.get("message", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="message is required")

    history = body.get("history") or []
    if not isinstance(history, list):
        raise HTTPException(status_code=400, detail="history must be a list")

    try:
        _record, sanitised, facts, fired = run_pipeline(pan, income_inr)
    except InvalidPAN as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except CustomerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KBUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    system_prompt, user_message = build_chat_prompt(
        sanitised, facts, fired, question, history
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in astream_chat(system_prompt, user_message):
                yield _sse("token", {"content": chunk})
            yield _sse("done", {"ok": True})
        except LLMError as exc:
            yield _sse("error", {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": f"Unexpected error: {exc}"})

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
    """Health check endpoint."""
    return {"status": "healthy", "service": "CIBIL Credit Coach"}
