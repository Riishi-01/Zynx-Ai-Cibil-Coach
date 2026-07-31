"""Tests for ``app.citations_chat`` — citation extraction from streamed text."""

from __future__ import annotations

from app.citations_chat import ChatCitation, extract_citations


def test_extract_label_id():
    answer = "Pay the HDFC card [high_utilization] to drop your utilization."
    citations = extract_citations(answer)
    assert citations == [ChatCitation(label_id="high_utilization")]


def test_extract_source_title():
    answer = "CIBIL weighs utilization heavily [Source: CIBIL Score Factors]."
    citations = extract_citations(answer)
    assert citations == [ChatCitation(source_title="CIBIL Score Factors")]


def test_extract_mixed_markers():
    answer = (
        "Pay the maxed card down [maxed_out]. "
        "CIBIL considers utilization a high-impact factor "
        "[Source: CIBIL Score Factors]."
    )
    citations = extract_citations(answer)
    assert citations == [
        ChatCitation(label_id="maxed_out"),
        ChatCitation(source_title="CIBIL Score Factors"),
    ]


def test_extract_dedupes_repeated_label():
    answer = "Lower util [high_utilization]. Keep paying [high_utilization]."
    citations = extract_citations(answer)
    assert citations == [ChatCitation(label_id="high_utilization")]


def test_extract_ignores_unknown_label_id():
    answer = "Generic advice [rate_shopping_window] with no KB backing."
    citations = extract_citations(answer)
    assert citations == []


def test_extract_strict_label_allowlist():
    answer = (
        "Mention maxed_out [maxed_out] and old_card [unused_revolving_cards]."
    )
    citations = extract_citations(answer, allowed_label_ids=("maxed_out",))
    assert citations == [ChatCitation(label_id="maxed_out")]


def test_extract_strict_label_allowlist_empty_falls_back_to_all():
    """An empty allowlist should not silently drop every label_id."""
    answer = "Use [high_utilization] cues."
    citations = extract_citations(answer, allowed_label_ids=())
    assert citations == [ChatCitation(label_id="high_utilization")]


def test_extract_strips_whitespace_in_source_title():
    answer = "[Source:   CIBIL Score Factors   ]"
    citations = extract_citations(answer)
    assert citations == [ChatCitation(source_title="CIBIL Score Factors")]


def test_extract_returns_empty_for_no_markers():
    assert extract_citations("Plain prose answer.") == []


def test_extract_handles_empty_input():
    assert extract_citations("") == []


def test_to_dict_for_label():
    assert ChatCitation(label_id="high_utilization").to_dict() == {
        "label_id": "high_utilization"
    }


def test_to_dict_for_source():
    assert ChatCitation(source_title="CIBIL Score Factors").to_dict() == {
        "source_title": "CIBIL Score Factors"
    }
