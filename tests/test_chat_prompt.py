"""Tests for the chat prompt builder after the RAG changes."""

from __future__ import annotations

import pytest

from app.chat_rag import Retrieval
from app.label_service import run_pipeline
from app.prompt_builder import build_chat_prompt


@pytest.fixture
def pipeline_outputs(seeded_db):
    record, sanitised, facts, fired, _first_name = run_pipeline("ABCPS1234A", 75000)
    return record, sanitised, facts, fired


def test_chat_prompt_includes_retrieved_chunks(pipeline_outputs):
    _record, sanitised, facts, fired = pipeline_outputs
    retrieved = (
        Retrieval(
            label_id="maxed_out",
            text="Maxed out (utilization, critical). Pay the highest card down to 30%.",
            score=0.81,
        ),
        Retrieval(
            label_id="recent_inquiries",
            text="Recent inquiries (inquiries, warning). Hard pulls cost 5-10 points each.",
            score=0.74,
        ),
    )

    system_prompt, user_message = build_chat_prompt(
        sanitised, facts, fired, "Should I apply for a card?", [], retrieved
    )

    assert "Retrieved KB context" in user_message
    assert "1. **maxed_out**" in user_message
    assert "2. **recent_inquiries**" in user_message
    # Scores are internal ranking signals, not part of the user-visible body.
    assert "0.81" not in user_message
    assert "0.74" not in user_message
    # The retrieval instructions live in the system prompt, not the body.
    assert "Retrieved KB context" in user_message


def test_chat_prompt_handles_no_retrieval(pipeline_outputs):
    _record, sanitised, facts, fired = pipeline_outputs
    _, user_message = build_chat_prompt(
        sanitised, facts, fired, "Should I pay more than the minimum?", []
    )
    assert "Retrieved KB context" not in user_message


def test_chat_prompt_accepts_legacy_signature_without_retrieved(pipeline_outputs):
    """Existing callers should keep working when they don't pass retrieved."""
    _record, sanitised, facts, fired = pipeline_outputs
    _, user_message = build_chat_prompt(
        sanitised, facts, fired, "Why is my score falling?"
    )
    assert "Why is my score falling?" in user_message


def test_chat_system_prompt_documents_citation_rule():
    from app.prompt_builder import CHAT_SYSTEM_PROMPT

    assert "CITATIONS" in CHAT_SYSTEM_PROMPT
    assert "[label_id]" in CHAT_SYSTEM_PROMPT


def test_chat_system_prompt_documents_untrusted_kb_text():
    from app.prompt_builder import CHAT_SYSTEM_PROMPT

    assert "untrusted reference" in CHAT_SYSTEM_PROMPT.lower()
    assert "do not cover the question" in CHAT_SYSTEM_PROMPT.lower()
