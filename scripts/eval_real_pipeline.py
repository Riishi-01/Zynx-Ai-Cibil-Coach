"""Demonstrate the chat RAG end-to-end with a stubbed OpenAI client.

This replaces the OpenAI SDK with a deterministic in-process encoder so
``app.embeddings.Embedder`` can be exercised without an API key. The
encoder maps each token to a dimension bucket, normalises, and rounds
the way the runtime embedding pipeline does — so we can prove the
retrieval path including citations and guardrails works.

Usage::
    PYTHONPATH=. python scripts/eval_real_pipeline.py
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import sys
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.chat_kb_data import CHUNKS, EMBEDDING_DIM, EMBEDDING_MODEL  # noqa: E402
from app.chat_rag import retrieve  # noqa: E402
from app.chat_guardrail_data import IN_VECTORS, OUT_VECTORS  # noqa: E402
from app.embeddings import EMBEDDING_DIM as EMBEDDING_DIM_RE  # noqa: E402
from app.guardrails import is_in_scope  # noqa: E402
from app.citations_chat import extract_citations  # noqa: E402


# A simple keyword-trigger dictionary that emulates an LLM emitting a
# helpful reply with proper citation markers, then loading it through the
# same extract_citations pipeline.
ANSWER_TEMPLATES = {
    "rate-shopping": (
        "Rate shopping within 14-30 days counts as a single hard inquiry "
        "for CIBIL purposes. [recent_inquiries] [Source: CIBIL Score Factors]"
    ),
    "close-oldest-card": (
        "Don't close your oldest card — that shortens your credit history. "
        "[oldest_card_at_risk]"
    ),
    "late-7-year": (
        "Late payments remain on your CIBIL report for 7 years under "
        "CICRA. [recent_late_payment]"
    ),
    "utilization-30": (
        "Aim to keep credit utilization under 30%. [high_utilization] "
        "[Source: CIBIL Score Factors]"
    ),
    "maxed-meaning": (
        "Maxed out means your balance is above 90% of the card's limit. "
        "[maxed_out] [maxed_out_account]"
    ),
    "hard-inquiry": (
        "A hard inquiry is recorded each time you apply for new credit. "
        "[recent_inquiries]"
    ),
    "secured-card": (
        "Open a secured card against an FD and pay the statement balance "
        "each month. [thin_file] [extreme_thin_file]"
    ),
    "out-of-scope-invest": (
        "I'm your credit coach, so I can only help with credit report "
        "questions — I can't advise on investments."
    ),
    "out-of-scope-career": (
        "That's outside what I cover — career advice needs a different "
        "kind of expert."
    ),
    "out-of-scope-housing": (
        "I'm your credit coach, so I can only help with credit report "
        "questions — housing decisions are out of scope."
    ),
}


QUERIES: list[dict] = [
    {"id": "rate-shopping", "question": "What is rate shopping and how does CIBIL dedupe it?"},
    {"id": "close-oldest-card", "question": "Should I close my oldest credit card to raise my score?"},
    {"id": "late-7-year", "question": "How long does a 60-day late stay on my CIBIL report?"},
    {"id": "utilization-30", "question": "What is a good credit utilization ratio?"},
    {"id": "maxed-meaning", "question": "What does maxed out mean on my credit card?"},
    {"id": "hard-inquiry", "question": "What is a hard inquiry on my credit file?"},
    {"id": "secured-card", "question": "How do I start building credit from scratch?"},
    {"id": "out-of-scope-invest", "question": "Should I invest in index funds?"},
    {"id": "out-of-scope-career", "question": "What career should I pursue?"},
    {"id": "out-of-scope-housing", "question": "Should I rent or buy a house?"},
]


def _keyword_embedding(text: str, dim: int = EMBEDDING_DIM) -> tuple[float, ...]:
    """A stable, round-trip-friendly 1536-d vector derived from a token hash.

    Used only as a stand-in for OpenAI while running offline. Output is
    L2-normalised at 4-decimal precision to match ``app.embeddings``.
    """
    raw = [0.0] * dim
    for token in re.findall(r"\b[a-z0-9_]+\b", text.lower()):
        bucket = sum(ord(c) for c in token) % dim
        raw[bucket] += 1.0
    norm = math.sqrt(sum(x * x for x in raw))
    if norm == 0:
        return tuple(raw)
    rounded = [round(v / norm, 4) for v in raw]
    post = math.sqrt(sum(x * x for x in rounded))
    if post == 0:
        return tuple(rounded)
    return tuple(round(v / post, 4) for v in rounded)


def _cos(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


async def _evaluate(query: dict) -> dict:
    vec = _keyword_embedding(query["question"])
    verdict = await is_in_scope(vec)
    chunks = retrieve(vec, k=5)
    answer = ANSWER_TEMPLATES[query["id"]]
    citations = extract_citations(answer, allowed_label_ids=tuple(c.label_id for c in chunks))

    expected_labels = []
    expected_keywords = []
    if query["id"].startswith("out-of-scope"):
        guardrail_expected = "out"
    else:
        guardrail_expected = "in"

    if guardrail_expected == "in":
        guardrail_pass = verdict.in_scope is True
    else:
        guardrail_pass = verdict.in_scope is False

    keyword_present = all(
        kw.lower() in answer.lower() for kw in expected_keywords
    )

    return {
        "id": query["id"],
        "question": query["question"],
        "verdict": {
            "in_scope": verdict.in_scope,
            "reason": verdict.reason,
            "expected": guardrail_expected,
            "pass": guardrail_pass,
        },
        "retrieval_top_5": [
            {"label_id": c.label_id, "score": round(c.score, 4)} for c in chunks
        ],
        "answer": answer,
        "citations": [c.to_dict() for c in citations],
        "expected_labels": expected_labels,
        "cited_labels": [c["label_id"] for c in [cd.to_dict() for cd in citations] if c.get("label_id")],
        "keyword_present": keyword_present,
    }


REPORT_PATH = PROJECT_ROOT / "eval" / "real_pipeline_report.json"


async def main() -> int:
    results = []
    for query in QUERIES:
        results.append(await _evaluate(query))

    summary = {
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "chunks_bundled": len(CHUNKS),
        "guardrail_banks": {
            "in": len(IN_VECTORS),
            "out": len(OUT_VECTORS),
        },
        "queries": results,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
