"""Task 8 — streaming structured plan tests.

The LLM is always mocked: conftest removes OPENAI_API_KEY, so any real call
would fail. What is under test is the streaming contract, not the model.
"""

import json
from typing import AsyncIterator

import pytest

from app.prompt_builder import (
    CHAT_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    CoachAction,
    CoachPlan,
    build_chat_prompt,
    build_facts_block,
    build_findings_block,
    build_prompt,
)

# A plausible plan, streamed in fragments to exercise partial JSON parsing.
# Mirrors the 3-field output schema (current_situation, top_actions,
# what_to_avoid) — follow_up_question was dropped in v2.
PLAN = {
    "current_situation": "Your utilization is 96% and you have a 90+ day late.",
    "top_actions": [
        {
            "title": "Pay down your Kotak card",
            "why": "It is at 98% utilization, the highest on your profile.",
            "steps": ["Pay ₹13,500 to reach 30%", "Set up autopay"],
            "when_youll_see_results": "1-2 billing cycles",
        }
    ],
    "what_to_avoid": ["Do not close the maxed cards", "Do not apply for new credit"],
}


def _fragments(payload: dict, size: int = 24) -> list[str]:
    """Split JSON into small chunks, the way a model would emit it."""
    text = json.dumps(payload)
    return [text[i : i + size] for i in range(0, len(text), size)]


class FakeStreamingModel:
    """Stands in for ChatOpenAI in a LangChain chain.

    Implements the minimum for `model | parser` piping: astream() yielding
    AIMessageChunk objects that the output parsers can consume.
    """

    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    def __or__(self, parser):
        from langchain_core.runnables import RunnableGenerator

        async def generate(inputs):
            for chunk in self._chunks:
                yield chunk

        return RunnableGenerator(generate) | parser


@pytest.fixture
def mock_plan_stream(monkeypatch):
    """Patch astream_plan to yield (kind, payload) tuples.

    Mirrors the real contract: progressively-complete plan dicts, then one
    final ('metadata', {model, prompt_tokens, completion_tokens}) tuple.
    """
    from app import web

    async def fake_astream_plan(system_prompt, user_message, model=None):
        from langchain_core.output_parsers import JsonOutputParser

        parser = JsonOutputParser()
        buffer = ""
        for fragment in _fragments(PLAN):
            buffer += fragment
            try:
                partial = parser.parse(buffer)
            except Exception:
                continue
            if isinstance(partial, dict):
                yield ("plan", partial)

        # Mirror the real callback that captures LangChain's usage_metadata.
        yield (
            "metadata",
            {
                "model": "gpt-4o-mini",
                "prompt_tokens": 1234,
                "completion_tokens": 567,
            },
        )

    monkeypatch.setattr(web, "astream_plan", fake_astream_plan)
    return fake_astream_plan


@pytest.fixture
def mock_plan_stream_no_metadata(monkeypatch):
    """Variant of mock_plan_stream with no metadata frame — simulates a model
    that doesn't surface usage_metadata (older API responses)."""
    from app import web

    async def fake_astream_plan(system_prompt, user_message, model=None):
        from langchain_core.output_parsers import JsonOutputParser

        parser = JsonOutputParser()
        buffer = ""
        for fragment in _fragments(PLAN):
            buffer += fragment
            try:
                partial = parser.parse(buffer)
            except Exception:
                continue
            if isinstance(partial, dict):
                yield ("plan", partial)

    monkeypatch.setattr(web, "astream_plan", fake_astream_plan)
    return fake_astream_plan


@pytest.fixture
def mock_chat_stream(monkeypatch):
    from app import web

    async def fake_astream_chat(system_prompt, user_message, model=None):
        for chunk in ["Your utilization ", "is $96\\%$, ", "which is critical."]:
            yield chunk

    monkeypatch.setattr(web, "astream_chat", fake_astream_chat)
    return fake_astream_chat


@pytest.fixture
def client(seeded_db):
    from fastapi.testclient import TestClient

    from app.web import app

    return TestClient(app)


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event, data) pairs."""
    events = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        event = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if event:
            events.append((event, data))
    return events


# ------------------------------------------------------------------ schema ----


def test_coach_plan_schema_roundtrips():
    plan = CoachPlan.model_validate(PLAN)
    assert len(plan.top_actions) == 1
    assert plan.top_actions[0].when_youll_see_results == "1-2 billing cycles"


def test_coach_action_requires_all_fields():
    with pytest.raises(Exception):
        CoachAction.model_validate({"title": "Missing the rest"})


# ------------------------------------------------------------------ prompt ----


def test_system_prompt_states_grounding_and_indian_context():
    assert "Never invent" in SYSTEM_PROMPT
    assert "300-900" in SYSTEM_PROMPT
    assert "₹1,20,000" in SYSTEM_PROMPT


def test_system_prompt_carries_spec_latex_rules():
    """SPEC §4.1: $..$ delimiters, never inside code fences."""
    assert "$..$" in SYSTEM_PROMPT
    assert "$$..$$" in SYSTEM_PROMPT
    assert "NEVER wrap LaTeX in code fences" in SYSTEM_PROMPT


def test_chat_prompt_shares_the_same_rules():
    assert "300-900" in CHAT_SYSTEM_PROMPT
    assert "$..$" in CHAT_SYSTEM_PROMPT


# ---------------------------------------------------------------- Maya persona --


def test_system_prompt_declares_maya_persona():
    """The plan-mode prompt must declare Maya's persona verbatim."""
    assert "Maya" in SYSTEM_PROMPT
    assert "CFP-certified credit counselor" in SYSTEM_PROMPT
    assert "15 years" in SYSTEM_PROMPT
    assert "2,000+" in SYSTEM_PROMPT


def test_system_prompt_carries_scope_redirect():
    """Maya must redirect non-credit questions with the canonical clause."""
    assert "I'm your credit coach" in SYSTEM_PROMPT
    assert "you'd want a CFP" in SYSTEM_PROMPT
    assert "do NOT advise on" in SYSTEM_PROMPT
    # Specific out-of-scope topics called out.
    for topic in ("invest", "career", "discretionary", "housing", "tax"):
        assert topic.lower() in SYSTEM_PROMPT.lower(), f"missing scope topic: {topic}"


def test_system_prompt_states_debt_framework():
    """Modified avalanche + APR midpoints + 70% income rule + 70/20/10 split."""
    assert "modified avalanche" in SYSTEM_PROMPT.lower() or "DEBT MANAGEMENT FRAMEWORK" in SYSTEM_PROMPT
    # APR midpoints for the four core loan types.
    assert "39%" in SYSTEM_PROMPT  # credit card
    assert "13.5%" in SYSTEM_PROMPT  # personal loan
    assert "70% of surplus" in SYSTEM_PROMPT  # allocation split
    # 70% income survivability rule.
    assert "70% of income" in SYSTEM_PROMPT
    # Three plan types.
    assert "AGGRESSIVE PAYDOWN" in SYSTEM_PROMPT
    assert "CARRIED-FORWARD" in SYSTEM_PROMPT
    assert "MINIMUM PAYMENT PLAN" in SYSTEM_PROMPT


def test_system_prompt_lists_all_7_banned_actions():
    """Each banned-action clause must appear verbatim in the prompt."""
    banned_clauses = [
        "Cash withdrawals from credit cards",
        "Closing the oldest credit card",
        "Paying collections past the 7-year",
        "Paying down a card that is 30+ days overdue",
        "New debt to pay old debt",
        "Balance transfer cards",
        "Numbers not in the customer facts",
    ]
    for clause in banned_clauses:
        assert clause in SYSTEM_PROMPT, f"missing banned-action clause: {clause!r}"


def test_system_prompt_lists_all_7_label_adaptations():
    """Each Maya label adaptation must appear as an explicit rule."""
    adaptations = [
        "Disputable Collection",
        "Collection Past SOL",
        "Extreme Thin File",
        "Bankruptcy Filed",
        "Severe DTI",
        "Score Falling",
        "Zero Utilization Paradox",
    ]
    for label in adaptations:
        assert label in SYSTEM_PROMPT, f"missing label adaptation: {label!r}"


def test_system_prompt_includes_crisis_mode_block():
    """CRISIS MODE must be a labelled section with the 6 required rules."""
    assert "CRISIS MODE" in SYSTEM_PROMPT
    assert "MINIMUM PAYMENT PLAN" in SYSTEM_PROMPT
    assert "hardship plan" in SYSTEM_PROMPT
    assert "RBI-listed credit counselor" in SYSTEM_PROMPT
    assert "Do NOT recommend new debt to pay old debt" in SYSTEM_PROMPT


def test_system_prompt_enforces_300_to_400_word_cap():
    """The persona section must state the 300–400-word target."""
    assert "300" in SYSTEM_PROMPT and "400" in SYSTEM_PROMPT


def test_system_prompt_carries_citation_discipline():
    """Every claim must trace to a slot's specifics."""
    assert "specifics.pay_cents" in SYSTEM_PROMPT
    assert "specifics.creditor_name" in SYSTEM_PROMPT
    assert "specifics.target_utilization" in SYSTEM_PROMPT
    assert "staleness_warning" in SYSTEM_PROMPT


def test_system_prompt_tone_guidance():
    """Maya's tone rules — warm, first name once, plain English."""
    assert "Warm, supportive" in SYSTEM_PROMPT
    assert "first name" in SYSTEM_PROMPT.lower()
    assert "Plain English" in SYSTEM_PROMPT


def test_system_prompt_requests_three_field_json_output():
    """Output schema must list the 3 required fields (no follow_up_question)."""
    for field in ("current_situation", "top_actions", "what_to_avoid"):
        assert field in SYSTEM_PROMPT, f"output spec missing field: {field!r}"
    # The prompt must instruct the model NOT to emit follow_up_question.
    assert "Do NOT include a follow_up_question" in SYSTEM_PROMPT


def test_chat_prompt_carries_maya_scope_guardrails():
    """The chat prompt must carry the same scope redirect and hard rules."""
    assert "Maya" in CHAT_SYSTEM_PROMPT
    assert "I'm your credit coach" in CHAT_SYSTEM_PROMPT
    assert "you'd want a CFP" in CHAT_SYSTEM_PROMPT
    # Banned-action rules must carry over to chat mode.
    for clause in (
        "Cash withdrawals from credit cards",
        "Closing the oldest credit card",
        "New debt to pay old debt",
        "Balance transfer cards",
    ):
        assert clause in CHAT_SYSTEM_PROMPT, f"chat prompt missing clause: {clause!r}"


def test_chat_prompt_drops_framework_specifics():
    """Framework/label-adaptation blocks belong to plan-mode, not chat-mode."""
    assert "DEBT MANAGEMENT FRAMEWORK" not in CHAT_SYSTEM_PROMPT
    assert "LABEL ADAPTATIONS" not in CHAT_SYSTEM_PROMPT


def test_facts_block_contains_only_supplied_numbers(seeded_db):
    from app.label_service import run_pipeline

    _, sanitised, facts, _ = run_pipeline("BCDRM2345B", 40000)
    block = build_facts_block(facts, sanitised)

    assert "612" in block            # score
    assert "96%" in block           # utilisation
    assert "54%" in block           # DTI
    assert "Kotak League Platinum" in block


def test_findings_block_includes_kb_guidance(seeded_db):
    from app.label_service import run_pipeline

    _, sanitised, facts, fired = run_pipeline("BCDRM2345B", 40000)
    block = build_findings_block(facts, sanitised, fired)

    assert "Maxed Out" in block
    assert "Why it matters" in block
    assert "Recommended steps" in block
    assert "priority 1" in block


def test_build_prompt_requests_the_plan_fields(seeded_db):
    from app.label_service import run_pipeline

    _, sanitised, facts, fired = run_pipeline("ABCPS1234A", 75000)
    _system, user = build_prompt(sanitised, facts, fired)

    for field in CoachPlan.model_fields:
        assert field in user, f"prompt does not request {field}"


def test_chat_prompt_includes_question_and_history(seeded_db):
    from app.label_service import run_pipeline

    _, sanitised, facts, fired = run_pipeline("ABCPS1234A", 75000)
    _system, user = build_chat_prompt(
        sanitised,
        facts,
        fired,
        "Should I close my SBI card?",
        [{"role": "user", "content": "earlier question"}],
    )

    assert "Should I close my SBI card?" in user
    assert "earlier question" in user


def test_prompt_has_no_leaked_placeholders(seeded_db):
    """Findings embed rendered templates; none may carry a raw brace."""
    from app.db import get_repository
    from app.label_service import run_pipeline
    from app.template_renderer import unresolved_placeholders

    for cust in get_repository().list_all_customers():
        _, sanitised, facts, fired = run_pipeline(cust.customer.pan_card)
        _system, user = build_prompt(sanitised, facts, fired)
        assert not unresolved_placeholders(user), cust.customer.pan_card


# --------------------------------------------------------------- streaming ----


def test_analyze_emits_canvas_before_any_plan_delta(client, mock_plan_stream):
    """The canvas must arrive first so charts render without waiting."""
    response = client.post("/api/analyze", json={"pan": "BCDRM2345B", "income": 40000})
    assert response.status_code == 200

    events = _parse_sse(response.text)
    names = [name for name, _ in events]

    assert names[0] == "canvas"
    assert "plan_delta" in names
    assert names.index("canvas") < names.index("plan_delta")


def test_analyze_canvas_event_is_complete(client, mock_plan_stream):
    response = client.post("/api/analyze", json={"pan": "BCDRM2345B", "income": 40000})
    events = dict(_parse_sse(response.text))

    canvas = events["canvas"]
    assert canvas["score_hero"]["score"] == 612
    assert len(canvas["payment_heatmap"]["cells"]) == 24
    assert len(canvas["labels"]["labels"]) == 32


def test_analyze_terminates_with_done(client, mock_plan_stream):
    response = client.post("/api/analyze", json={"pan": "BCDRM2345B", "income": 40000})
    names = [name for name, _ in _parse_sse(response.text)]
    assert names[-1] == "done"


def test_plan_deltas_are_monotonically_more_complete(client, mock_plan_stream):
    """Every delta parses, and the last one is the whole plan."""
    response = client.post("/api/analyze", json={"pan": "BCDRM2345B", "income": 40000})
    deltas = [data for name, data in _parse_sse(response.text) if name == "plan_delta"]

    assert len(deltas) > 1, "expected progressive deltas, not a single payload"
    for delta in deltas:
        assert isinstance(delta, dict)

    final = deltas[-1]
    assert final["current_situation"] == PLAN["current_situation"]
    CoachPlan.model_validate(final)


def test_metadata_event_reports_token_usage(client, mock_plan_stream):
    """After the plan stream completes, a metadata event carries token counts."""
    response = client.post("/api/analyze", json={"pan": "BCDRM2345B", "income": 40000})
    events = dict(_parse_sse(response.text))

    assert "metadata" in events, "expected metadata event after plan_delta frames"
    md = events["metadata"]
    assert md["model"] == "gpt-4o-mini"
    assert md["prompt_tokens"] == 1234
    assert md["completion_tokens"] == 567


def test_metadata_event_emitted_after_plan_deltas(client, mock_plan_stream):
    """The metadata event lands AFTER all plan_delta frames and BEFORE done."""
    response = client.post("/api/analyze", json={"pan": "BCDRM2345B", "income": 40000})
    names = [name for name, _ in _parse_sse(response.text)]

    last_plan_idx = max(i for i, n in enumerate(names) if n == "plan_delta")
    md_idx = names.index("metadata")
    done_idx = names.index("done")
    assert last_plan_idx < md_idx < done_idx


def test_metadata_event_omitted_when_no_usage_captured(client, mock_plan_stream_no_metadata):
    """If the chain emits no metadata, the stream must not invent one."""
    response = client.post("/api/analyze", json={"pan": "BCDRM2345B", "income": 40000})
    events = dict(_parse_sse(response.text))

    assert "metadata" not in events
    # plan + canvas + done still all flow.
    assert "canvas" in events
    assert "plan_delta" in events
    assert "done" in events


def test_citations_event_references_real_facts(client, mock_plan_stream):
    response = client.post("/api/analyze", json={"pan": "BCDRM2345B", "income": 40000})
    events = dict(_parse_sse(response.text))

    assert "citations" in events
    citations = events["citations"]["citations"]
    assert citations, "expected at least one grounded figure to be cited"

    from app.schemas import FactSet

    for citation in citations:
        for fact_id in citation["fact_ids"]:
            assert fact_id in FactSet.model_fields, f"{fact_id} is not a real fact"


def test_streaming_headers_disable_buffering(client, mock_plan_stream):
    response = client.post("/api/analyze", json={"pan": "BCDRM2345B", "income": 40000})
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["cache-control"] == "no-cache"
    assert "text/event-stream" in response.headers["content-type"]


def test_llm_failure_still_delivers_canvas(client, monkeypatch):
    """When generation fails the charts must survive; only the plan is lost."""
    from app import web
    from app.schemas import LLMError

    async def failing_stream(system_prompt, user_message, model=None):
        raise LLMError("model unavailable")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(web, "astream_plan", failing_stream)

    response = client.post("/api/analyze", json={"pan": "BCDRM2345B", "income": 40000})
    assert response.status_code == 200

    events = dict(_parse_sse(response.text))
    assert "canvas" in events
    assert "error" in events
    assert "model unavailable" in events["error"]["message"]


def test_analyze_validates_before_streaming(client):
    """Bad input is a proper HTTP error, not a mid-stream error event."""
    assert client.post("/api/analyze", json={}).status_code == 400
    assert client.post("/api/analyze", json={"pan": "ZZZPZ9999Z"}).status_code == 404


# -------------------------------------------------------------------- chat ----


def test_chat_streams_tokens(client, mock_chat_stream):
    response = client.post(
        "/api/chat",
        json={"pan": "ABCPS1234A", "income": 75000, "message": "Why is my score falling?"},
    )
    assert response.status_code == 200

    events = _parse_sse(response.text)
    tokens = [data["content"] for name, data in events if name == "token"]

    assert tokens
    assert "".join(tokens) == "Your utilization is $96\\%$, which is critical."
    assert events[-1][0] == "done"


def test_chat_requires_a_message(client):
    response = client.post("/api/chat", json={"pan": "ABCPS1234A", "income": 75000})
    assert response.status_code == 400


def test_chat_rejects_non_list_history(client):
    response = client.post(
        "/api/chat",
        json={"pan": "ABCPS1234A", "message": "hi", "history": "not a list"},
    )
    assert response.status_code == 400


def test_chat_error_is_reported_as_event(client, monkeypatch):
    from app import web
    from app.schemas import LLMError

    async def failing_stream(system_prompt, user_message, model=None):
        raise LLMError("rate limited")
        yield  # pragma: no cover

    monkeypatch.setattr(web, "astream_chat", failing_stream)

    response = client.post(
        "/api/chat", json={"pan": "ABCPS1234A", "message": "hello"}
    )
    events = dict(_parse_sse(response.text))
    assert "rate limited" in events["error"]["message"]


# ------------------------------------------------------------------ retired ----


def test_sessions_endpoint_is_gone(client):
    """The in-memory session store was dead weight and has been removed."""
    assert client.get("/api/sessions").status_code == 404


# --------------------------------------------------------------- citations ----


def test_cite_plan_finds_figures_across_nested_fields(seeded_db):
    from app.citations import cite_plan
    from app.label_service import run_pipeline

    _, _, facts, fired = run_pipeline("BCDRM2345B", 40000)
    citations = cite_plan(PLAN, facts, fired)

    assert citations
    cited = {fact_id for c in citations for fact_id in c.fact_ids}
    assert cited, "no facts were traced"


def test_citations_ignore_ungrounded_numbers(seeded_db):
    """A number that matches no fact must not be cited."""
    from app.citations import generate_citations
    from app.label_service import run_pipeline

    _, _, facts, fired = run_pipeline("BCDRM2345B", 40000)
    citations = generate_citations("The answer is 987654321.", facts, fired)
    assert citations == []


def test_citations_ignore_prose_numerals(seeded_db):
    """'1-2 billing cycles' is prose, not a profile figure."""
    from app.citations import generate_citations
    from app.label_service import run_pipeline

    _, _, facts, fired = run_pipeline("BCDRM2345B", 40000)
    citations = generate_citations(
        "Do this in 1-2 billing cycles, following all 3 steps.", facts, fired
    )
    assert citations == []


def test_citations_reject_ambiguous_matches(seeded_db):
    """A token matching many facts tells the reader nothing."""
    from app.citations import MAX_AMBIGUITY, generate_citations
    from app.label_service import run_pipeline

    _, _, facts, fired = run_pipeline("BCDRM2345B", 40000)
    citations = generate_citations(
        "Utilisation is 96% and the top card is at 98%.", facts, fired
    )

    assert citations
    for citation in citations:
        assert len(citation.fact_ids) <= MAX_AMBIGUITY


def test_citations_match_distinctive_figures(seeded_db):
    """Carlos's 96% utilisation and 98% top card are unambiguous."""
    from app.citations import generate_citations
    from app.label_service import run_pipeline

    _, _, facts, fired = run_pipeline("BCDRM2345B", 40000)
    citations = generate_citations(
        "Your utilisation is 96%, driven by a card at 98%.", facts, fired
    )

    cited = {fid for c in citations for fid in c.fact_ids}
    assert "overall_utilization" in cited
    assert "max_single_card_utilization" in cited


def test_citations_attach_reason_codes(seeded_db):
    from app.citations import generate_citations
    from app.label_service import run_pipeline

    _, _, facts, fired = run_pipeline("BCDRM2345B", 40000)
    citations = generate_citations(f"Your score is {facts.score}.", facts, fired)

    assert citations
    assert "2" in citations[0].sources  # utilisation reason code
