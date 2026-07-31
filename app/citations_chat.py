"""Extract [label_id] and [Source: title] citations from streamed chat text.

Pinned to the label_ids known to the live KB so the model's free-form
``[foo_bar]`` embellishments don't surface as citations. Source titles are
accepted verbatim (they don't share a controlled vocabulary), but with the
same first-occurrence de-duplication the spec calls for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

from app.chat_kb_data import CHUNKS

_KNOWN_LABEL_IDS = frozenset(c.label_id for c in CHUNKS)

# Either [label_id] or [Source: <title>]. label_id must start with a letter and
# contain only snake_case chars; the source branch accepts anything up to the
# closing bracket.
_CITE_PATTERN = re.compile(
    r"\[([a-z_][a-z0-9_]*)\]|\[Source:\s*([^\]]+)\]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChatCitation:
    """One bibliography entry extracted from the model's streamed reply."""

    label_id: Optional[str] = None
    source_title: Optional[str] = None

    def to_dict(self) -> dict:
        if self.label_id is not None:
            return {"label_id": self.label_id}
        return {"source_title": self.source_title or ""}


def extract_citations(
    answer: str,
    *,
    allowed_label_ids: Optional[Sequence[str]] = None,
) -> list[ChatCitation]:
    """Return ChatCitations in the order they first appear in ``answer``.

    A label_id is included only when it resolves to a chunk bundled in
    ``app/chat_kb_data``. ``allowed_label_ids``, when supplied, narrows the
    accepted set further (use it to restrict citations to the top-K retrieved
    sources for the question).

    Each citation is returned at most once. The order is the order of the
    first occurrence of each accepted marker.
    """
    if not answer:
        return []

    allowed: Optional[set[str]]
    if allowed_label_ids is None:
        allowed = None
    else:
        allowed = {label for label in allowed_label_ids if label in _KNOWN_LABEL_IDS}
        if not allowed:
            allowed = set(_KNOWN_LABEL_IDS)

    seen_labels: set[str] = set()
    seen_titles: set[str] = set()
    out: list[ChatCitation] = []

    for label_id, source_title in _CITE_PATTERN.findall(answer):
        if label_id:
            normalized = label_id.lower()
            if (
                normalized in _KNOWN_LABEL_IDS
                and (allowed is None or normalized in allowed)
                and normalized not in seen_labels
            ):
                out.append(ChatCitation(label_id=normalized))
                seen_labels.add(normalized)
        elif source_title:
            cleaned = source_title.strip()
            if cleaned and cleaned not in seen_titles:
                out.append(ChatCitation(source_title=cleaned))
                seen_titles.add(cleaned)

    return out


__all__ = ["ChatCitation", "extract_citations"]
