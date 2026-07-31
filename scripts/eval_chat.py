#!/usr/bin/env python3
"""Run the chat RAG eval cases against a local or staging /api/chat.

Usage::

    # Start the API in another terminal, then:
    python scripts/eval_chat.py --base-url http://127.0.0.1:8000

    # Or dry-run against a stubbed answer provider to validate the harness:
    python scripts/eval_chat.py --offline
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES_PATH = PROJECT_ROOT / "eval" / "chat_cases.json"
REPORT_PATH = PROJECT_ROOT / "eval" / "chat_report.json"


def _stream_chat(base_url: str, pan: str, message: str) -> tuple[list[str], list[dict], str | None]:
    """Return (tokens, citations, guardrail_reason_or_None) from /api/chat."""
    body = {"pan": pan, "message": message}
    tokens: list[str] = []
    citations: list[dict] = []
    guardrail: str | None = None
    event: str | None = None
    data_lines: list[str] = []
    with httpx.Client(timeout=60.0) as client:
        with client.stream("POST", f"{base_url}/api/chat", json=body) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines():
                if raw_line is None or raw_line == "":
                    if event is not None:
                        data = "\n".join(data_lines).strip()
                        try:
                            parsed = json.loads(data)
                        except json.JSONDecodeError:
                            parsed = {}
                        if event == "token":
                            tokens.append(parsed.get("content", ""))
                        elif event == "citations":
                            citations = parsed.get("citations", citations)
                        elif event == "guardrail":
                            guardrail = parsed.get("reason", guardrail)
                        elif event == "error":
                            print(f"[chat error] {parsed}", file=sys.stderr)
                    event = None
                    data_lines = []
                    continue
                if raw_line.startswith("event: "):
                    event = raw_line[len("event: "):]
                elif raw_line.startswith("data: "):
                    data_lines.append(raw_line[len("data: "):])
    if event is not None and data_lines:
        try:
            parsed = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            parsed = {}
        if event == "token":
            tokens.append(parsed.get("content", ""))
        elif event == "citations":
            citations = parsed.get("citations", citations)
        elif event == "guardrail":
            guardrail = parsed.get("reason", guardrail)
    return tokens, citations, guardrail


def _grade_case(case: dict, tokens: list[str], citations: list[dict], guardrail: str | None) -> dict:
    answer = "".join(tokens).lower()
    keywords = [k.lower() for k in case.get("expected_keywords", [])]
    label_ids = {c.get("label_id") for c in citations if c.get("label_id")}
    expected_labels = set(case.get("expected_label_ids", []))

    keyword_pass = all(keyword in answer for keyword in keywords)
    label_pass = expected_labels.issubset(label_ids) if expected_labels else True
    in_scope = case.get("in_scope", True)

    if in_scope:
        # Out-of-scope must NOT have fired; pass when guardrail is None.
        guardrail_pass = guardrail is None
    else:
        # In-scope expected to be flagged out; check guardrail present.
        guardrail_pass = guardrail is not None or "credit coach" in answer

    return {
        "id": case["id"],
        "pass": keyword_pass and label_pass and guardrail_pass,
        "checks": {
            "keywords": keyword_pass,
            "labels": label_pass,
            "guardrail": guardrail_pass,
        },
        "answer_snippet": "".join(tokens)[:240],
        "guardrail_reason": guardrail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--report", default=str(REPORT_PATH))
    parser.add_argument("--offline", action="store_true", help="Skip network calls.")
    args = parser.parse_args()

    cases_path = Path(args.cases)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))["cases"]

    results = []
    if args.offline:
        for case in cases:
            results.append(
                {
                    "id": case["id"],
                    "pass": False,
                    "skipped": True,
                    "reason": "offline mode",
                }
            )
    else:
        for case in cases:
            try:
                tokens, citations, guardrail = _stream_chat(
                    args.base_url, case["pan"], case["question"]
                )
                results.append(_grade_case(case, tokens, citations, guardrail))
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "id": case["id"],
                        "pass": False,
                        "error": str(exc),
                    }
                )

    passed = sum(1 for r in results if r.get("pass"))
    total = len(results)
    summary = {
        "total": total,
        "passed": passed,
        "ratio": f"{passed}/{total}",
        "results": results,
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0 if passed >= max(1, int(0.85 * total)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
