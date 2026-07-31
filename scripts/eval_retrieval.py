"""Run canned real queries through the bundled chat RAG pipeline.

Loads the committed ``app/chat_kb_data`` vectors, derives a deterministic
embedding for each question (matching ``app/embeddings``'s shape), and
reports the top-5 retrieval labels per question. There is no LLM call —
this is a sanity check that retrieval + citations + guardrails return
useful output without a network.

Usage::
    PYTHONPATH=. python scripts/eval_retrieval.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.chat_kb_data import CHUNKS, EMBEDDING_DIM, EMBEDDING_MODEL  # noqa: E402
from app.chat_rag import TOP_K, retrieve  # noqa: E402
from app.chat_guardrail_data import IN_VECTORS, OUT_VECTORS  # noqa: E402
from app.citations_chat import extract_citations  # noqa: E402


QUERIES: list[dict] = [
    {
        "label": "rate-shopping",
        "question": "What is rate shopping and how does CIBIL dedupe it?",
        "expected_label_ids": ["recent_inquiries", "credit_seeking_pattern"],
    },
    {
        "label": "close-oldest-card",
        "question": "Should I close my oldest credit card to increase my score?",
        "expected_label_ids": ["oldest_card_at_risk", "unused_revolving_cards"],
    },
    {
        "label": "late-7-year",
        "question": "How long does a 60-day late payment stay on my CIBIL report?",
        "expected_label_ids": ["recent_late_payment", "serious_delinquency"],
    },
    {
        "label": "utilization-30",
        "question": "What is a good credit utilization ratio?",
        "expected_label_ids": ["high_utilization", "low_utilization"],
    },
    {
        "label": "maxed-meaning",
        "question": "What does maxed out mean on my credit card?",
        "expected_label_ids": ["maxed_out", "maxed_out_account"],
    },
    {
        "label": "hard-inquiry",
        "question": "What is a hard inquiry on my credit file?",
        "expected_label_ids": ["recent_inquiries"],
    },
    {
        "label": "secured-card",
        "question": "How do I start building credit from scratch?",
        "expected_label_ids": ["thin_file", "extreme_thin_file"],
    },
    {
        "label": "out-of-scope-invest",
        "question": "Should I invest in index funds?",
        "expected_label_ids": [],
        "out_of_scope_expected": True,
    },
    {
        "label": "out-of-scope-career",
        "question": "What career should I pursue?",
        "expected_label_ids": [],
        "out_of_scope_expected": True,
    },
    {
        "label": "out-of-scope-housing",
        "question": "Should I rent or buy a house?",
        "expected_label_ids": [],
        "out_of_scope_expected": True,
    },
]


def _l2_normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in values))
    if norm == 0:
        return values
    rounded = [round(v / norm, 4) for v in values]
    post = math.sqrt(sum(x * x for x in rounded))
    if post == 0:
        return rounded
    return [round(v / post, 4) for v in rounded]


def _question_vec(text: str) -> tuple[float, ...]:
    """Hash-into-vector function mirroring ``_FakeEmbedder`` in eval_chat_local."""
    raw = [0.0] * EMBEDDING_DIM
    for i, ch in enumerate(text):
        raw[i % EMBEDDING_DIM] += (ord(ch) % 73) - 32
    return tuple(_l2_normalize(raw))


def _cos(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def _guardrail_score(vec):
    in_avg = sum(_cos(vec, v) for v in IN_VECTORS) / max(1, len(IN_VECTORS))
    out_avg = sum(_cos(vec, v) for v in OUT_VECTORS) / max(1, len(OUT_VECTORS))
    return in_avg, out_avg


REPORT_PATH = PROJECT_ROOT / "eval" / "retrieval_report.json"


def main() -> int:
    results = []
    for query in QUERIES:
        vec = _question_vec(query["question"])
        chunks = retrieve(vec, k=TOP_K)
        labels = [c.label_id for c in chunks]
        expected = set(query.get("expected_label_ids") or [])
        retrieved = set(labels)
        if expected:
            top_hit = next((label for label in labels if label in expected), None)
            recall_at_k = len(expected & retrieved) / len(expected)
        else:
            top_hit = None
            recall_at_k = None

        in_avg, out_avg = _guardrail_score(vec)
        out_of_scope = query.get("out_of_scope_expected", False)
        if out_of_scope:
            guardrail_pass = out_avg > in_avg  # type: ignore[operator]
        else:
            guardrail_pass = in_avg >= out_avg

        fake_answer = (
            f"Canned answer for: {query['question']}\n"
            f"Cited labels: {', '.join(labels[:2])}\n"
            f"[{labels[0] if labels else 'fallback'}]"
        )
        citations = extract_citations(
            fake_answer,
            allowed_label_ids=tuple(labels),
        )

        results.append(
            {
                "id": query["label"],
                "question": query["question"],
                "retrieved_top_5": [
                    {"label_id": c.label_id, "score": round(c.score, 4)}
                    for c in chunks
                ],
                "expected_labels": sorted(expected),
                "top_expected_in_top5": top_hit,
                "recall_at_5": recall_at_k,
                "guardrail": {
                    "in_avg": round(in_avg, 4),
                    "out_avg": round(out_avg, 4),
                    "out_of_scope_expected": out_of_scope,
                    "pass": bool(guardrail_pass),
                },
                "citations": [c.to_dict() for c in citations],
            }
        )

    summary = {
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "chunks_bundled": len(CHUNKS),
        "guardrail_in_count": len(IN_VECTORS),
        "guardrail_out_count": len(OUT_VECTORS),
        "queries": results,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
