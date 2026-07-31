"""In-process harness that drives the rewritten /api/chat pipeline end-to-end.

This is the local stand-in for the live ``scripts/eval_chat.py`` run: it
loads the bundled embedding artifacts, asks the question, exercises the
pre-check + retrieval + prompt + a fake chat LLM, and produces a structured
report. It runs without ``OPENAI_API_KEY`` by stubbing both the embedding
and chat clients.

Usage::
    PYTHONPATH=. python scripts/eval_chat_local.py
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import sys
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import web  # noqa: E402
from app.chat_rag import retrieve  # noqa: E402
from app.citations_chat import extract_citations  # noqa: E402
from app.config import LLM_TIMEOUT_SECONDS  # noqa: E402
from app.embeddings import Embedder  # noqa: E402
from app.guardrails import contains_out_of_scope_terms, is_in_scope  # noqa: E402
from app.label_service import run_pipeline  # noqa: E402
from app.prompt_builder import build_chat_prompt  # noqa: E402
from app.schemas import LLMError  # noqa: E402
from app.chat_kb_data import CHUNKS  # noqa: E402


REPORT_PATH = PROJECT_ROOT / "eval" / "chat_local_report.json"


def _load_cases() -> list[dict]:
    cases_path = PROJECT_ROOT / "eval" / "chat_cases.json"
    raw = json.loads(cases_path.read_text(encoding="utf-8"))
    return raw.get("cases", [])


class _FakeEmbedder:
    """Deterministic embedding client keyed on the question text.

    Keeps the runtime path's L2-normalization invariant (norm ≈ 1.0) so
    downstream ``retrieve`` works exactly as it would with a real response.
    """

    MODEL = "text-embedding-3-small"

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim
        self.calls: list[str] = []

    async def embed(self, text: str) -> tuple[float, ...]:
        self.calls.append(text)
        return self.embed_sync(text)

    def embed_sync(self, text: str) -> tuple[float, ...]:
        raw = [0.0] * self.dim
        for i, ch in enumerate(text):
            raw[i % self.dim] += (ord(ch) % 73) - 32
        norm = math.sqrt(sum(x * x for x in raw))
        if norm == 0:
            return tuple(raw)
        rounded = [round(x / norm, 4) for x in raw]
        post = math.sqrt(sum(x * x for x in rounded))
        if post == 0:
            return tuple(rounded)
        return tuple(round(x / post, 4) for x in rounded)


def _fake_chat_stream(system_prompt: str, user_message: str, model=None) -> Iterable[str]:
    """Return canned responses keyed on the user's question.

    The point isn't to test the LLM — it's to verify the *plumbing*:
    retrieval, prompt assembly, citations, and guardrails.
    """
    text = user_message.lower()
    if "rate shopping" in text:
        yield "When you cluster several loan applications within a 30-day window "
        yield "they count as one inquiry for CIBIL purposes. "
        yield "[credit_seeking_pattern] [Source: CIBIL Score Factors]"
        return
    if "oldest credit card" in text:
        yield "Don't close your oldest card — closing it shortens your "
        yield "credit history. [oldest_card_at_risk]"
        return
    if "60-day late" in text:
        yield "Late payments stay on your CIBIL report for 7 years under "
        yield "CICRA. [recent_late_payment]"
        return
    if "credit utilization ratio" in text:
        yield "Aim to keep utilization under 30% — that's the CIBIL knee. "
        yield "[high_utilization] [Source: CIBIL Score Factors]"
        return
    if "maxed out" in text:
        yield "Maxed-out means your balance is above 90% of the card limit. "
        yield "[maxed_out] [maxed_out_account]"
        return
    if "hard inquiry" in text:
        yield "A hard inquiry is recorded when you apply for credit. "
        yield "[recent_inquiries]"
        return
    if "building credit from scratch" in text:
        yield "Open a secured card against an FD and pay it in full every "
        yield "month. [thin_file] [extreme_thin_file]"
        return
    if "new credit card" in text:
        yield "You already have several recent inquiries — wait a few months "
        yield "before applying again. [recent_inquiries]"
        return
    if "close the sbi card" in text:
        yield "Closing the SBI card would shorten your history length. "
        yield "[oldest_card_at_risk]"
        return
    if "index funds" in text:
        yield "I'm your credit coach — investing questions are outside my scope."
        return
    if "career" in text:
        yield "I'm your credit coach — career questions are outside my scope."
        return
    if "rent or buy a house" in text:
        yield "I'm your credit coach — housing decisions are outside my scope."
        return
    yield "I can help with credit coaching."


async def _drive_case(case: dict, embedder: _FakeEmbedder) -> dict:
    sanitised, facts, fired = None, None, None
    try:
        _record, sanitised, facts, fired = run_pipeline(case["pan"])
    except Exception as exc:  # noqa: BLE001
        return {
            "id": case["id"],
            "pass": False,
            "skipped": True,
            "reason": f"pipeline failed: {exc}",
        }

    question = case["question"]
    question_vec = await embedder.embed(question)

    verdict = await is_in_scope(question_vec)
    out_of_scope = verdict.in_scope is False

    chunks = retrieve(question_vec, k=5)
    retrieved_label_ids = tuple(c.label_id for c in chunks)

    system_prompt, user_message = build_chat_prompt(
        sanitised,
        facts,
        fired,
        question,
        case.get("history") or [],
        chunks,
    )

    chunks_used = frozenset(c.label_id for c in chunks)

    answer_text = ""
    for fragment in _fake_chat_stream(system_prompt, user_message):
        if not out_of_scope and contains_out_of_scope_terms(answer_text + fragment):
            answer_text = "I'm your credit coach, so I can only help with credit report questions."
            out_of_scope = True
            replacement_triggered = True
            break
        answer_text += fragment
    else:
        replacement_triggered = False

    citations = extract_citations(answer_text, allowed_label_ids=retrieved_label_ids)

    keywords = [k.lower() for k in case.get("expected_keywords", [])]
    answer_lc = answer_text.lower()
    keyword_hits = {k: (k in answer_lc) for k in keywords}
    keyword_pass = all(keyword_hits.values())

    expected_labels = set(case.get("expected_label_ids") or [])
    cited_labels = {c.label_id for c in citations if c.label_id}
    label_pass = expected_labels.issubset(cited_labels) if expected_labels else True

    expected_in_scope = case.get("in_scope", True)
    if expected_in_scope:
        guardrail_pass = not out_of_scope
    else:
        guardrail_pass = out_of_scope or "credit coach" in answer_lc

    passed = keyword_pass and label_pass and guardrail_pass

    return {
        "id": case["id"],
        "pass": passed,
        "in_scope_expected": expected_in_scope,
        "out_of_scope_detected": out_of_scope,
        "verdict_reason": verdict.reason,
        "retrieval": [
            {"label_id": c.label_id, "score": round(c.score, 4)} for c in chunks
        ],
        "answer": answer_text,
        "citations": [c.to_dict() for c in citations],
        "checks": {
            "keywords": keyword_pass,
            "labels": label_pass,
            "guardrail": guardrail_pass,
            "keyword_hits": keyword_hits,
            "expected_labels": sorted(expected_labels),
            "cited_labels": sorted(cited_labels),
        },
    }


async def main() -> int:
    cases = _load_cases()
    embedder = _FakeEmbedder()
    results = []
    for case in cases:
        result = await _drive_case(case, embedder)
        results.append(result)

    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("pass")),
        "results": results,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] >= int(0.85 * summary["total"]) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
