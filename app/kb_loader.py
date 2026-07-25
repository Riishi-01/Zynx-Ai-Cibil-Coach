"""Load the knowledge base from label_kb.json at startup.

This is Phase 7: loads the KB once, keeps in memory.
Provides efficient lookup by label_id.
"""

import json
from pathlib import Path
from typing import Optional

from app.schemas import KBEntry, KBSource, LabelCategory, LabelSeverity
from app.config import LABEL_KB_PATH


class KnowledgeBase:
    """In-memory KB of labels, keyed by label_id."""

    def __init__(self):
        self._entries: dict[str, KBEntry] = {}

    def load_from_file(self, path: Path) -> None:
        """Load KB from label_kb.json."""
        raw = json.loads(path.read_text(encoding="utf-8"))
        
        for label_data in raw.get("labels", []):
            label_id = label_data["label_id"]
            
            # Parse sources
            sources = [
                KBSource(
                    title=src.get("title", ""),
                    url=src.get("url", "")
                )
                for src in label_data.get("sources", [])
            ]
            
            # Construct KBEntry
            entry = KBEntry(
                label_id=label_id,
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
                cibil_reason_codes=label_data.get("cibil_reason_codes", []),
                personalized_response_template=label_data.get("personalized_response_template", ""),
                sources=sources,
            )
            
            self._entries[label_id] = entry

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


# Singleton KB instance
_kb: Optional[KnowledgeBase] = None


def get_knowledge_base() -> KnowledgeBase:
    """Get the global knowledge base, initialising it if needed."""
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
        _kb.load_from_file(LABEL_KB_PATH)
    return _kb
