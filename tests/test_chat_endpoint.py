"""End-to-end tests for the rewired ``/api/chat`` endpoint.

These tests stub out the embedding pipeline and chat LLM so they run with
``OPENAI_API_KEY`` unset, while exercising the new SSE contract: optional
``guardrail`` event, ``replace`` event, terminal ``citations`` and ``done``.
"""

from __future__ import annotations

import json
import math
from typing import AsyncIterator

import pytest


EMBED_DIM = 1536


def _unit(seed: int) -> list[float]:
    raw = [0.0] * EMBED_DIM
    raw[seed % EMBED_DIM] = 1.0
    raw[(seed + 5) % EMBED_DIM] = 0.4
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event, data) pairs."""
    events: list[tuple[str, dict]] = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        event = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event:
            events.append((event, data))
    return events


@pytest.fixture
def fake_embedder(monkeypatch):
    """A no-network Embedder that returns a deterministic unit vector."""
    from app import web

    class _StubEmbedder:
        MODEL = "text-embedding-3-small"

        def __init__(self):
            self.calls: list[str] = []

        async def embed(self, text: str) -> tuple[float, ...]:
            self.calls.append(text)
            return tuple(_unit(len(self.calls)))

    fake = _StubEmbedder()
    web._embedder = fake
    yield fake
    web._embedder = None


@pytest.fixture
def client(seeded_db):
    """TestClient against the FastAPI app — defined locally because this
    file intentionally doesn't import test_streaming_plan."""
    from fastapi.testclient import TestClient

    from app.web import app

    return TestClient(app)


def test_chat_streams_tokens_and_emits_done(client, fake_embedder, monkeypatch):
    from app import web

    async def fake_astream_chat(system_prompt, user_message, model=None):
        for chunk in ["Pay down your ", "Kotak card to ", "30% utilization."]:
            yield chunk

    monkeypatch.setattr(web, "astream_chat", fake_astream_chat)

    response = client.post(
        "/api/chat",
        json={
            "pan": "ABCPS1234A",
            "income": 75000,
            "message": "Why is my utilization so high?",
        },
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "token"
    assert names[-1] == "done"

    joined = "".join(data["content"] for name, data in events if name == "token")
    assert joined == "Pay down your Kotak card to 30% utilization."

    assert fake_embedder.calls and fake_embedder.calls[0] == "Why is my utilization so high?"


def test_chat_emits_citations_after_stream(client, fake_embedder, monkeypatch):
    from app import web

    async def fake_astream_chat(system_prompt, user_message, model=None):
        yield "Pay down the card [maxed_out]. Use autopay [Source: CIBIL Score Factors]."

    monkeypatch.setattr(web, "astream_chat", fake_astream_chat)

    response = client.post(
        "/api/chat",
        json={"pan": "ABCPS1234A", "income": 75000, "message": "Paying down card"},
    )
    events = _parse_sse(response.text)

    citation_events = [data for name, data in events if name == "citations"]
    assert citation_events and citation_events[0]["citations"]
    citation_records = citation_events[0]["citations"]
    label_ids = [c.get("label_id") for c in citation_records]
    source_titles = [c.get("source_title") for c in citation_records]
    assert "maxed_out" in label_ids
    assert "CIBIL Score Factors" in source_titles


def test_chat_emits_guardrail_and_token_redirect(client, fake_embedder, monkeypatch):
    """A pre-check rejection returns the fixed redirect instead of an LLM call."""
    from app import web
    from app.guardrails import ScopeGuard

    called = {"count": 0}

    async def should_not_run(*args, **kwargs):
        called["count"] += 1
        yield ""

    monkeypatch.setattr(web, "astream_chat", should_not_run)

    async def fake_check(self, text, *, question_vec=None):
        return (False, "out", 0.9)

    monkeypatch.setattr(ScopeGuard, "check", fake_check)

    response = client.post(
        "/api/chat",
        json={"pan": "ABCPS1234A", "income": 75000, "message": "Should I invest in stocks?"},
    )

    assert response.status_code == 200
    assert called["count"] == 0, "chat LLM must not be called for out-of-scope questions"

    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "guardrail"
    assert any(name == "token" for name in names)
    assert names[-1] == "done"

    guardrail_event = next(data for name, data in events if name == "guardrail")
    assert guardrail_event["verdict"] == "out_of_scope"
    assert guardrail_event["reason"] == "out"


def test_chat_post_check_replaces_partial_stream(client, fake_embedder, monkeypatch):
    """If the model's first sentence drifts out of scope, replace it."""
    from app import web
    from app.guardrails import ScopeGuard

    async def fake_astream_chat(system_prompt, user_message, model=None):
        for chunk in [
            "I can help. ",
            "Consider investing in index funds ",
            "and selling your credit cards.",
        ]:
            yield chunk

    monkeypatch.setattr(web, "astream_chat", fake_astream_chat)

    async def fake_check(self, text, *, question_vec=None):
        return (True, "in", 0.9)

    monkeypatch.setattr(ScopeGuard, "check", fake_check)

    response = client.post(
        "/api/chat",
        json={"pan": "ABCPS1234A", "income": 75000, "message": "Help me"},
    )

    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert "guardrail" in names
    assert "replace" in names
    replace_event = next(data for name, data in events if name == "replace")
    assert "credit coach" in replace_event["content"].lower()
    assert names[-1] == "done"


def test_chat_handles_too_long_message(client, fake_embedder):
    response = client.post(
        "/api/chat",
        json={
            "pan": "ABCPS1234A",
            "income": 75000,
            "message": "x" * 5000,
        },
    )
    assert response.status_code == 400
    assert "chars" in response.text


def test_chat_validates_history_entry_shape(client, fake_embedder):
    response = client.post(
        "/api/chat",
        json={
            "pan": "ABCPS1234A",
            "income": 75000,
            "message": "Hello",
            "history": [{"role": "user", "content": 1}],
        },
    )
    assert response.status_code == 400


def test_chat_history_is_truncated(client, fake_embedder, monkeypatch):
    from app import web

    captured_kwargs: dict = {}

    async def fake_astream_chat(system_prompt, user_message, model=None):
        captured_kwargs["user_message"] = user_message
        yield "ok"

    monkeypatch.setattr(web, "astream_chat", fake_astream_chat)

    long_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"}
        for i in range(40)
    ]
    response = client.post(
        "/api/chat",
        json={
            "pan": "ABCPS1234A",
            "income": 75000,
            "message": "Question",
            "history": long_history,
        },
    )
    assert response.status_code == 200
    user_message = captured_kwargs["user_message"]
    assert "turn 25" not in user_message  # only the last CHAT_MAX_HISTORY_TURNS*2 kept
    assert "turn 39" in user_message


def test_chat_embed_failure_is_an_sse_error(client, monkeypatch):
    from app import web

    class _Embedder:
        async def embed(self, text):
            raise web.LLMError("OPENAI_API_KEY not set in environment")

    web._embedder = _Embedder()
    try:
        response = client.post(
            "/api/chat",
            json={"pan": "ABCPS1234A", "income": 75000, "message": "Hello"},
        )
        assert response.status_code == 200
        events = _parse_sse(response.text)
        error_event = next(data for name, data in events if name == "error")
        assert "Embedding failed" in error_event["message"]
    finally:
        web._embedder = None
