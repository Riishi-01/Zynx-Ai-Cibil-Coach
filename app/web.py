"""FastAPI web server with streaming structured LLM output."""

import os
import json
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
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

# Enable CORS
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


def _sse(event: str, data: Any) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


from pathlib import Path

# Serve the Vite-built frontend. In production, `npm run build` outputs to
# frontend/dist/. If that directory exists, we mount it and serve index.html
# for the root route. In development, the Vite dev server handles all frontend
# assets and proxies /api to this process, so this path isn't reached.
_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@app.get("/", response_class=HTMLResponse)
async def serve_home():
    """Serve the built frontend's index.html."""
    index_path = _FRONTEND_DIST / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>CIBIL Credit Coach</h1><p>Run <code>cd frontend && npm run build</code> to generate the UI.</p>"
    )


# Mount static assets (JS, CSS, fonts) AFTER api routes so /api/* takes priority.
if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="static")


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

    Body: {"pan": "ABCPS1234A", "income": 75000}
    """
    pan, income_inr = _parse_analysis_body(await request.json())

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

    Body: {"pan": ..., "income": ..., "message": "...", "history": [...]}
    History entries are {"role": "user"|"assistant", "content": "..."}.
    """
    body = await request.json()
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

    Body: {"pan": "ABCPS1234A", "income": 75000}
    """
    pan, income_inr = _parse_analysis_body(await request.json())

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


    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
