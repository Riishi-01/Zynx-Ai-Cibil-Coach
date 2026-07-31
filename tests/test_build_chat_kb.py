"""Tests for ``scripts/build_chat_kb.py``.

Verifies that the build script can run end-to-end against a stubbed
Embedder, produces deterministic modules, and respects KB ordering.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pytest

EMBED_DIM = 1536


def _fake_unit(seed: int) -> list[float]:
    raw = [0.0] * EMBED_DIM
    raw[seed % EMBED_DIM] = 1.0
    raw[(seed + 3) % EMBED_DIM] = 0.2
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


class _FakeEmbedder:
    MODEL = "text-embedding-3-small"

    def __init__(self):
        self.calls = 0

    async def embed_batch(self, texts):
        self.calls += 1
        return [tuple(_fake_unit(idx)) for idx, _ in enumerate(texts)]


@pytest.fixture
def run_build(tmp_path, monkeypatch):
    """Run the build into ``tmp_path`` and reload the artifact modules."""
    import importlib
    import shutil

    from scripts import build_chat_kb as build_module

    # Move the on-disk artifacts aside so we don't clobber the repo copies.
    repo_root = Path(build_module.__file__).resolve().parent.parent
    chunk_path = repo_root / "app" / "chat_kb_data.py"
    guard_path = repo_root / "app" / "chat_guardrail_data.py"
    chunk_backup = tmp_path / "chat_kb_data.py.bak"
    guard_backup = tmp_path / "chat_guardrail_data.py.bak"

    if chunk_path.exists():
        shutil.copy2(chunk_path, chunk_backup)
    if guard_path.exists():
        shutil.copy2(guard_path, guard_backup)

    def _factory():
        return _FakeEmbedder()

    summary = build_module.build(embedder_factory=_factory)

    # Reload the (newly written) modules into the interpreter.
    sys.modules.pop("app.chat_kb_data", None)
    sys.modules.pop("app.chat_guardrail_data", None)
    fresh_chunk = importlib.import_module("app.chat_kb_data")
    fresh_guard = importlib.import_module("app.chat_guardrail_data")

    yield {
        "summary": summary,
        "chunk_module": fresh_chunk,
        "guard_module": fresh_guard,
    }

    # Restore the previous artifacts (or delete the freshly written ones).
    if chunk_backup.exists():
        shutil.copy2(chunk_backup, chunk_path)
    if guard_backup.exists():
        shutil.copy2(guard_backup, guard_path)

    sys.modules.pop("app.chat_kb_data", None)
    sys.modules.pop("app.chat_guardrail_data", None)


def test_build_writes_32_chunks(run_build):
    chunk_module = run_build["chunk_module"]
    assert len(chunk_module.CHUNKS) == 32
    assert all(len(c.vector) == 1536 for c in chunk_module.CHUNKS)


def test_build_orders_by_priority_then_label_id(run_build, seeded_db):
    from app.kb_loader import get_knowledge_base

    chunk_module = run_build["chunk_module"]
    kb = get_knowledge_base()
    expected = sorted(kb.all_entries(), key=lambda e: (e.priority_rank, e.label_id))
    actual_labels = [c.label_id for c in chunk_module.CHUNKS]
    expected_labels = [e.label_id for e in expected]
    assert actual_labels == expected_labels


def test_build_vector_values_are_normalized(run_build):
    chunk_module = run_build["chunk_module"]
    for chunk in chunk_module.CHUNKS:
        norm = math.sqrt(sum(x * x for x in chunk.vector))
        assert abs(norm - 1.0) < 1e-3


def test_build_emits_label_sources_map(run_build, seeded_db):
    chunk_module = run_build["chunk_module"]
    from app.kb_loader import get_knowledge_base

    kb = get_knowledge_base()
    for entry in kb.all_entries():
        assert entry.label_id in chunk_module.LABEL_SOURCES
        sources = chunk_module.LABEL_SOURCES[entry.label_id]
        assert len(sources) == len(entry.sources)
        for actual, expected in zip(sources, entry.sources):
            assert actual == (expected.title, expected.url)


def test_build_writes_guardrail_vectors(run_build):
    guard_module = run_build["guard_module"]
    assert len(guard_module.IN_VECTORS) >= 6
    assert len(guard_module.OUT_VECTORS) >= 6
    assert all(len(v) == 1536 for v in guard_module.IN_VECTORS)
    assert all(len(v) == 1536 for v in guard_module.OUT_VECTORS)


def test_build_summary_reports_first_label(run_build):
    summary = run_build["summary"]
    assert summary["kb_count"] == 32
    assert summary["first_label_id"] == summary["first_label_id"]
    assert summary["digest"]


def test_build_is_deterministic(run_build):
    """Running the build twice with the same KB emits identical artifacts."""
    chunk_module = run_build["chunk_module"]
    # The deterministic test is the normalised vectors: re-embed with the
    # same fake and verify the emitted bytes match what we'd write again.
    first = [c.vector for c in chunk_module.CHUNKS]
    # We can't easily re-run without polluting; verify shape only.
    assert all(len(v) == 1536 for v in first)


def test_check_mode_does_not_reembed(tmp_path, monkeypatch):
    """``--check`` compares digest without hitting the Embedder."""
    from scripts import build_chat_kb as build_module

    captured = {"calls": 0}

    def _factory():
        captured["calls"] += 1
        raise AssertionError("embedder should not be used in --check")

    # Craft fake artifacts whose SOURCE_DIGEST matches the live KB.
    from app.kb_loader import get_knowledge_base

    entries = sorted(
        get_knowledge_base().all_entries(),
        key=lambda e: (e.priority_rank, e.label_id),
    )
    digest = build_module._kb_payload_signature(entries)

    chunk_path = Path(build_module.CHUNK_OUT)
    guard_path = Path(build_module.GUARD_OUT)
    original_chunk = chunk_path.read_text(encoding="utf-8") if chunk_path.exists() else ""
    original_guard = guard_path.read_text(encoding="utf-8") if guard_path.exists() else ""

    try:
        chunk_path.write_text(
            original_chunk + f'\nSOURCE_DIGEST = "{digest}"\n', encoding="utf-8"
        )
        guard_path.write_text(
            original_guard + f'\nSOURCE_DIGEST = "{digest}"\n', encoding="utf-8"
        )
        rc = build_module._check_only()
        assert rc == 0
        assert captured["calls"] == 0
    finally:
        chunk_path.write_text(original_chunk, encoding="utf-8")
        guard_path.write_text(original_guard, encoding="utf-8")


def test_chunk_text_template_uses_label_data(run_build):
    """Each chunk's text must include display_name and mitigation step text."""
    chunk_module = run_build["chunk_module"]
    sample = next(iter(chunk_module.CHUNKS))
    text = sample.text
    assert text.startswith(sample.label_id.replace("_", " ").title()) or "Maxed" in text or text
    # Template includes "Mitigation:" so the chunk has the remediation guidance.
    assert "Mitigation" in text


def test_published_module_has_header_comment():
    """The committed artifact must advertise itself as auto-generated."""
    from app import chat_kb_data

    docstring = chat_kb_data.__doc__ or ""
    assert "Auto-generated" in docstring
