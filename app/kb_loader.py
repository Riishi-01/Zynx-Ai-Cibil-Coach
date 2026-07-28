"""Load the knowledge base from the kb_* tables in SQLite.

The KB used to be read from label_kb.json on disk. It now lives in the same
database as the customer data, seeded by scripts/seed_kb.py.

The public surface is deliberately unchanged — get_knowledge_base(), .get(),
.get_or_error(), .count() and .all_label_ids() behave exactly as before, so
prompt_builder.py and citations.py require no modification. load_from_file()
is retained for tests that need to compare the DB against the authored JSON.

The KB is small (32 labels) and immutable at runtime, so it is loaded once and
cached in memory rather than queried per request.
"""

import json
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import selectinload

from app.schemas import KBEntry, KBSource, LabelCategory, LabelSeverity, KBUnavailable
from app.config import LABEL_KB_PATH


class KnowledgeBase:
    """In-memory KB of labels, keyed by label_id."""

    def __init__(self):
        self._entries: dict[str, KBEntry] = {}

    # ---------------------------------------------------------------- load ----

    def load_from_db(self) -> None:
        """Load every label from the kb_* tables.

        Child collections are eager-loaded so this is a fixed number of queries
        regardless of label count, rather than one query per label.
        """
        # Imported here to keep this module importable without a live database
        # (scripts and tests that only parse JSON do not need an engine).
        from app.database import get_db_session
        from app.models import KBLabelModel

        session = get_db_session()
        try:
            rows = (
                session.query(KBLabelModel)
                .options(
                    selectinload(KBLabelModel.mitigation_steps),
                    selectinload(KBLabelModel.facts_to_cite),
                    selectinload(KBLabelModel.reason_codes),
                    selectinload(KBLabelModel.sources),
                )
                .order_by(KBLabelModel.priority_rank, KBLabelModel.label_id)
                .all()
            )

            if not rows:
                raise KBUnavailable(
                    "No labels found in kb_labels. Run: python3 scripts/seed_kb.py --reset"
                )

            self._entries = {row.label_id: self._to_entry(row) for row in rows}
        finally:
            session.close()

    def load_from_file(self, path: Path = None) -> None:
        """Load the KB from the authored label_kb.json.

        Retained so tests can assert the DB-backed load is lossless against the
        original file. Not used by the application at runtime.
        """
        path = path or LABEL_KB_PATH
        raw = json.loads(Path(path).read_text(encoding="utf-8"))

        for label_data in raw.get("labels", []):
            entry = KBEntry(
                label_id=label_data["label_id"],
                display_name=label_data.get("display_name", ""),
                category=LabelCategory(label_data.get("category", "utilization")),
                severity=LabelSeverity(label_data.get("severity", "info")),
                priority_rank=label_data.get("priority_rank", 5),
                fact_id=label_data.get("fact_id", ""),
                condition=label_data.get("condition", ""),
                condition_human=label_data.get("condition_human", ""),
                what_it_means_cibil=label_data.get("what_it_means_cibil", ""),
                why_it_matters=label_data.get("why_it_matters", ""),
                mitigation_steps=label_data.get("mitigation_steps", []),
                facts_to_cite=label_data.get("facts_to_cite", []),
                cibil_reason_codes=[str(c) for c in label_data.get("cibil_reason_codes", [])],
                personalized_response_template=label_data.get(
                    "personalized_response_template", ""
                ),
                sources=[
                    KBSource(title=s.get("title", ""), url=s.get("url", ""))
                    for s in label_data.get("sources", [])
                ],
            )
            self._entries[entry.label_id] = entry

    @staticmethod
    def _to_entry(row) -> KBEntry:
        """Rebuild a KBEntry from its ORM rows."""
        return KBEntry(
            label_id=row.label_id,
            display_name=row.display_name,
            category=LabelCategory(row.category),
            severity=LabelSeverity(row.severity),
            priority_rank=row.priority_rank,
            fact_id=row.fact_id,
            condition=row.condition,
            condition_human=row.condition_human,
            what_it_means_cibil=row.what_it_means_cibil,
            why_it_matters=row.why_it_matters,
            # Relationships carry order_by, so sequence is already correct.
            mitigation_steps=[s.step_text for s in row.mitigation_steps],
            facts_to_cite=[f.fact_name for f in row.facts_to_cite],
            cibil_reason_codes=[c.reason_code for c in row.reason_codes],
            personalized_response_template=row.personalized_response_template,
            sources=[KBSource(title=s.title, url=s.url) for s in row.sources],
        )

    # ------------------------------------------------------------- lookups ----

    def get(self, label_id: str) -> Optional[KBEntry]:
        """Retrieve a KB entry by label_id, or None if not found."""
        return self._entries.get(label_id)

    def get_or_error(self, label_id: str) -> KBEntry:
        """Retrieve a KB entry by label_id, or raise KeyError if not found."""
        if label_id not in self._entries:
            raise KeyError(f"Label '{label_id}' not found in knowledge base")
        return self._entries[label_id]

    def count(self) -> int:
        """Return the count of entries in the KB."""
        return len(self._entries)

    def all_label_ids(self) -> list[str]:
        """Return all label IDs in the KB."""
        return list(self._entries.keys())

    def all_entries(self) -> list[KBEntry]:
        """Every entry, ordered by priority_rank then label_id.

        Used by the labels API, which reports unfired labels alongside fired
        ones and therefore needs the full set.
        """
        return list(self._entries.values())


# Singleton KB instance
_kb: Optional[KnowledgeBase] = None


def get_knowledge_base() -> KnowledgeBase:
    """Get the global knowledge base, initialising it from the database if needed."""
    global _kb
    if _kb is None:
        kb = KnowledgeBase()
        kb.load_from_db()
        _kb = kb
    return _kb


def reset_knowledge_base() -> None:
    """Drop the cached KB so the next call reloads from the database.

    Only needed by tests and by the seeding scripts.
    """
    global _kb
    _kb = None
