#!/usr/bin/env python3
"""Seed the knowledge base tables from Frontend_docs/label_kb.json.

The KB lives in the same SQLite database as the customer data, in its own
kb_* tables. This script is the only writer for those tables.

Usage:
  python3 scripts/seed_kb.py           # Insert/replace all 32 labels
  python3 scripts/seed_kb.py --reset   # Delete existing KB rows first
"""

import json
import sys
from pathlib import Path

# Allow running as a bare script from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import LABEL_KB_PATH
from app.database import get_db_session, init_db
from app.models import (
    KBLabelModel,
    KBMitigationStepModel,
    KBFactToCiteModel,
    KBReasonCodeModel,
    KBSourceModel,
    KBMetaModel,
)
from app.schemas import KBEntry, KBSource, LabelCategory, LabelSeverity


def _parse_entry(raw: dict) -> KBEntry:
    """Validate one raw JSON label into a KBEntry before it touches the DB."""
    return KBEntry(
        label_id=raw["label_id"],
        display_name=raw["display_name"],
        category=LabelCategory(raw["category"]),
        severity=LabelSeverity(raw["severity"]),
        priority_rank=raw["priority_rank"],
        fact_id=raw.get("fact_id", ""),
        condition=raw.get("condition", ""),
        condition_human=raw.get("condition_human", ""),
        what_it_means_cibil=raw.get("what_it_means_cibil", ""),
        why_it_matters=raw.get("why_it_matters", ""),
        mitigation_steps=raw.get("mitigation_steps", []),
        facts_to_cite=raw.get("facts_to_cite", []),
        cibil_reason_codes=[str(c) for c in raw.get("cibil_reason_codes", [])],
        personalized_response_template=raw.get("personalized_response_template", ""),
        sources=[
            KBSource(title=s.get("title", ""), url=s.get("url", ""))
            for s in raw.get("sources", [])
        ],
    )


def _clear_kb(session) -> None:
    """Delete every KB row. Children first to respect foreign keys."""
    session.query(KBMitigationStepModel).delete()
    session.query(KBFactToCiteModel).delete()
    session.query(KBReasonCodeModel).delete()
    session.query(KBSourceModel).delete()
    session.query(KBLabelModel).delete()
    session.query(KBMetaModel).delete()
    session.flush()


def seed_kb(reset: bool = False, quiet: bool = False, kb_path: Path = None) -> int:
    """Load labels from label_kb.json into the kb_* tables.

    Returns the number of labels inserted.
    """
    path = kb_path or LABEL_KB_PATH

    def log(msg: str = "", **kw) -> None:
        if not quiet:
            print(msg, **kw)

    log(f"[*] Loading KB from {path}...")
    raw = json.loads(path.read_text(encoding="utf-8"))

    raw_labels = raw.get("labels", [])
    entries = [_parse_entry(item) for item in raw_labels]
    log(f"[*] Parsed {len(entries)} labels (schema_version {raw.get('schema_version')})")

    session = get_db_session()
    try:
        if reset:
            log("[*] Clearing existing KB rows...")
            _clear_kb(session)

        for i, entry in enumerate(entries, 1):
            log(f"[{i:2d}/{len(entries)}] {entry.label_id}...", end=" ")

            session.add(
                KBLabelModel(
                    label_id=entry.label_id,
                    display_name=entry.display_name,
                    category=entry.category.value,
                    severity=entry.severity.value,
                    priority_rank=entry.priority_rank,
                    fact_id=entry.fact_id,
                    condition=entry.condition,
                    condition_human=entry.condition_human,
                    what_it_means_cibil=entry.what_it_means_cibil,
                    why_it_matters=entry.why_it_matters,
                    personalized_response_template=entry.personalized_response_template,
                )
            )
            session.flush()

            # step_order preserves the authored sequence of the remediation steps.
            for order, step in enumerate(entry.mitigation_steps):
                session.add(
                    KBMitigationStepModel(
                        label_id=entry.label_id, step_order=order, step_text=step
                    )
                )

            for fact_name in entry.facts_to_cite:
                session.add(
                    KBFactToCiteModel(label_id=entry.label_id, fact_name=fact_name)
                )

            for code in entry.cibil_reason_codes:
                session.add(
                    KBReasonCodeModel(label_id=entry.label_id, reason_code=code)
                )

            for source in entry.sources:
                session.add(
                    KBSourceModel(
                        label_id=entry.label_id, title=source.title, url=source.url
                    )
                )

            log("OK")

        # The conventions block is the authoritative source for CIBIL band
        # ranges, so the API and frontend never hardcode them separately.
        conventions = raw.get("conventions", {})
        for key, value in conventions.items():
            session.add(KBMetaModel(key=key, value=value))

        for key in ("schema_version", "kb_name", "description"):
            if key in raw:
                session.add(KBMetaModel(key=key, value=raw[key]))

        session.commit()
        log(f"\n[+] Seeded {len(entries)} labels and {len(conventions)} convention keys")
        return len(entries)

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    reset = "--reset" in sys.argv
    init_db()
    count = seed_kb(reset=reset)
    if count == 0:
        print("[!] No labels were inserted", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
