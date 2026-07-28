"""Task 2 — KB ingestion tests.

Verifies all 32 labels reached the database intact, that the rule engine and
the KB agree on which labels exist, and that mitigation step ordering survives
the round trip.
"""

import pytest


def test_all_32_labels_ingested(db_session):
    from app.models import KBLabelModel

    assert db_session.query(KBLabelModel).count() == 32


def test_label_ids_match_json(db_session, kb_json):
    from app.models import KBLabelModel

    db_ids = {row.label_id for row in db_session.query(KBLabelModel).all()}
    json_ids = {item["label_id"] for item in kb_json["labels"]}
    assert db_ids == json_ids, f"symmetric difference: {db_ids ^ json_ids}"


def test_rule_table_and_kb_agree_both_directions(db_session):
    """Catches drift in either direction.

    A label in RULE_TABLE with no KB row would produce an "(unrecorded label)"
    line in the prompt. A KB row no rule can fire is dead content.
    """
    from app.models import KBLabelModel
    from app.rule_engine import RULE_TABLE

    rule_ids = {row[0] for row in RULE_TABLE}
    kb_ids = {row.label_id for row in db_session.query(KBLabelModel).all()}

    assert not (rule_ids - kb_ids), f"RULE_TABLE labels absent from KB: {rule_ids - kb_ids}"
    assert not (kb_ids - rule_ids), f"KB labels no rule can fire: {kb_ids - rule_ids}"


def test_mitigation_step_order_roundtrips(db_session, kb_json):
    """Steps come back in authored order, not insertion or alphabetical order."""
    from app.models import KBLabelModel

    by_id = {item["label_id"]: item for item in kb_json["labels"]}

    for label in db_session.query(KBLabelModel).all():
        expected = by_id[label.label_id].get("mitigation_steps", [])
        actual = [s.step_text for s in label.mitigation_steps]
        assert actual == expected, f"{label.label_id}: step order diverged"
        assert [s.step_order for s in label.mitigation_steps] == list(range(len(expected)))


def test_facts_to_cite_roundtrip(db_session, kb_json):
    from app.models import KBLabelModel

    by_id = {item["label_id"]: item for item in kb_json["labels"]}

    for label in db_session.query(KBLabelModel).all():
        expected = by_id[label.label_id].get("facts_to_cite", [])
        actual = [f.fact_name for f in label.facts_to_cite]
        assert actual == expected, f"{label.label_id}: facts_to_cite diverged"


def test_sources_roundtrip(db_session, kb_json):
    from app.models import KBLabelModel

    by_id = {item["label_id"]: item for item in kb_json["labels"]}

    for label in db_session.query(KBLabelModel).all():
        expected = [(s["title"], s["url"]) for s in by_id[label.label_id].get("sources", [])]
        actual = [(s.title, s.url) for s in label.sources]
        assert actual == expected, f"{label.label_id}: sources diverged"


def test_reason_codes_roundtrip(db_session, kb_json):
    from app.models import KBLabelModel

    by_id = {item["label_id"]: item for item in kb_json["labels"]}

    for label in db_session.query(KBLabelModel).all():
        expected = [str(c) for c in by_id[label.label_id].get("cibil_reason_codes", [])]
        actual = [c.reason_code for c in label.reason_codes]
        assert actual == expected, f"{label.label_id}: reason codes diverged"


def test_every_label_has_coaching_content(db_session):
    """No label may ship with empty copy — these fields drive the UI."""
    from app.models import KBLabelModel

    for label in db_session.query(KBLabelModel).all():
        assert label.display_name.strip(), f"{label.label_id}: empty display_name"
        assert label.why_it_matters.strip(), f"{label.label_id}: empty why_it_matters"
        assert label.what_it_means_cibil.strip(), f"{label.label_id}: empty what_it_means_cibil"
        assert label.personalized_response_template.strip(), f"{label.label_id}: empty template"
        assert len(label.mitigation_steps) > 0, f"{label.label_id}: no mitigation steps"


def test_priority_rank_in_range(db_session):
    from app.models import KBLabelModel

    for label in db_session.query(KBLabelModel).all():
        assert 1 <= label.priority_rank <= 5, f"{label.label_id}: rank {label.priority_rank}"


def test_kb_meta_holds_cibil_bands(db_session):
    """Band ranges must be readable from the DB so nothing hardcodes them."""
    from app.models import KBMetaModel

    row = db_session.query(KBMetaModel).filter_by(key="cibil_bands").first()
    assert row is not None, "cibil_bands missing from kb_meta"
    assert row.value == {
        "Poor": "300-579",
        "Fair": "580-699",
        "Good": "700-749",
        "Very Good": "750-799",
        "Excellent": "800-900",
    }


def test_kb_meta_bands_match_config():
    """The KB's bands and config.CIBIL_BANDS must not drift apart.

    frontend-charts-spec.md quotes FICO ranges (Fair 580-669, Good 670-739);
    this test pins the CIBIL ranges as authoritative.
    """
    from app.config import CIBIL_BANDS

    assert CIBIL_BANDS == {
        "Poor": (300, 579),
        "Fair": (580, 699),
        "Good": (700, 749),
        "Very Good": (750, 799),
        "Excellent": (800, 900),
    }


def test_seed_is_idempotent_with_reset(seeded_db):
    """Re-running with --reset leaves exactly 32 labels, not 64."""
    from app.models import KBLabelModel
    from app.database import SessionLocal
    from scripts.seed_kb import seed_kb

    seed_kb(reset=True, quiet=True)

    session = SessionLocal()
    try:
        assert session.query(KBLabelModel).count() == 32
    finally:
        session.close()
