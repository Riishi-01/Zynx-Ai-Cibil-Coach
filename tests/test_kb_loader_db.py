"""Task 4 — DB-backed KB loading tests.

The contract: loading from SQLite must be indistinguishable from loading the
authored JSON, and swapping the source must not change rule engine behaviour.
"""

import pytest

from app.kb_loader import KnowledgeBase, get_knowledge_base, reset_knowledge_base


@pytest.fixture
def db_kb(seeded_db):
    """A KB loaded from the database."""
    kb = KnowledgeBase()
    kb.load_from_db()
    return kb


@pytest.fixture
def json_kb(kb_json_path):
    """A KB loaded from the authored JSON file."""
    kb = KnowledgeBase()
    kb.load_from_file(kb_json_path)
    return kb


def test_db_load_returns_32_entries(db_kb):
    assert db_kb.count() == 32


def test_db_and_json_have_same_label_ids(db_kb, json_kb):
    assert set(db_kb.all_label_ids()) == set(json_kb.all_label_ids())


def test_db_entries_are_field_for_field_identical_to_json(db_kb, json_kb):
    """The lossless-swap proof.

    Compares every field of every KBEntry, so a dropped mitigation step, a
    reordered list, or a mangled template all surface here.
    """
    for label_id in json_kb.all_label_ids():
        from_json = json_kb.get(label_id)
        from_db = db_kb.get(label_id)
        assert from_db is not None, f"{label_id} missing from DB-loaded KB"
        assert from_db == from_json, f"{label_id} differs between DB and JSON"


def test_mitigation_steps_keep_order_through_db(db_kb, json_kb):
    """Ordering is the field most likely to silently degrade via a join."""
    for label_id in json_kb.all_label_ids():
        assert db_kb.get(label_id).mitigation_steps == json_kb.get(label_id).mitigation_steps


def test_templates_survive_verbatim(db_kb, json_kb):
    """Templates carry {placeholders} that must not be altered in transit."""
    for label_id in json_kb.all_label_ids():
        assert (
            db_kb.get(label_id).personalized_response_template
            == json_kb.get(label_id).personalized_response_template
        )


# ------------------------------------------------------- public interface ----


def test_get_returns_none_for_unknown(db_kb):
    assert db_kb.get("no_such_label") is None


def test_get_or_error_raises_for_unknown(db_kb):
    with pytest.raises(KeyError):
        db_kb.get_or_error("no_such_label")


def test_get_or_error_returns_entry(db_kb):
    assert db_kb.get_or_error("maxed_out").label_id == "maxed_out"


def test_all_entries_ordered_by_priority(db_kb):
    ranks = [e.priority_rank for e in db_kb.all_entries()]
    assert ranks == sorted(ranks)


def test_singleton_is_cached(seeded_db):
    reset_knowledge_base()
    first = get_knowledge_base()
    second = get_knowledge_base()
    assert first is second, "KB should be loaded once and cached"


def test_reset_forces_reload(seeded_db):
    reset_knowledge_base()
    first = get_knowledge_base()
    reset_knowledge_base()
    second = get_knowledge_base()
    assert first is not second
    assert first.count() == second.count() == 32


# ------------------------------------------- independence from the JSON file ----


def test_kb_loads_without_the_json_file(seeded_db, kb_json_path, tmp_path):
    """The app must work when label_kb.json is absent.

    Temporarily moves the file aside to prove the DB is the runtime source.
    """
    moved = tmp_path / "label_kb.json.moved"
    kb_json_path.rename(moved)
    try:
        reset_knowledge_base()
        kb = get_knowledge_base()
        assert kb.count() == 32
        assert kb.get("maxed_out") is not None
    finally:
        moved.rename(kb_json_path)
        reset_knowledge_base()


# ------------------------------------------------- rule engine unaffected ----


def test_rule_engine_output_unchanged_by_kb_source(seeded_db):
    """fire_labels() must be identical regardless of where the KB came from.

    The rule engine reads RULE_TABLE, never the KB, so switching the KB source
    must not perturb it. This pins that separation.
    """
    from app.data_fetch import fetch_customer_by_pan
    from app.db import get_repository
    from app.pii_parser import sanitise_record
    from app.precompute import precompute_facts
    from app.rule_engine import fire_labels

    def fired_for(pan):
        record = fetch_customer_by_pan(pan)
        facts = precompute_facts(
            sanitise_record(record),
            monthly_income_inr=record.customer.income_monthly_paise // 100,
        )
        return [(f.label_id, f.priority, f.account_id) for f in fire_labels(facts)]

    pans = [c.customer.pan_card for c in get_repository().list_all_customers()]

    reset_knowledge_base()
    with_db_kb = {pan: fired_for(pan) for pan in pans}

    # Swap the singleton for a JSON-loaded KB and re-run.
    import app.kb_loader as kb_loader

    json_backed = KnowledgeBase()
    json_backed.load_from_file()
    kb_loader._kb = json_backed
    try:
        with_json_kb = {pan: fired_for(pan) for pan in pans}
    finally:
        reset_knowledge_base()

    assert with_db_kb == with_json_kb


def test_coverage_contract_holds_with_db_kb(seeded_db):
    """All 32 labels still fire across the 23 customers."""
    from app.data_fetch import fetch_customer_by_pan
    from app.db import get_repository
    from app.pii_parser import sanitise_record
    from app.precompute import precompute_facts
    from app.rule_engine import RULE_TABLE, fire_labels

    fired = set()
    for cust in get_repository().list_all_customers():
        record = fetch_customer_by_pan(cust.customer.pan_card)
        facts = precompute_facts(
            sanitise_record(record),
            monthly_income_inr=record.customer.income_monthly_paise // 100,
        )
        fired.update(f.label_id for f in fire_labels(facts))

    expected = {r[0] for r in RULE_TABLE}
    assert fired == expected, f"missing: {expected - fired}"


def test_every_fired_label_has_kb_content(seeded_db):
    """No fired label may fall through to the '(unrecorded label)' path."""
    from app.data_fetch import fetch_customer_by_pan
    from app.db import get_repository
    from app.pii_parser import sanitise_record
    from app.precompute import precompute_facts
    from app.rule_engine import fire_labels

    reset_knowledge_base()
    kb = get_knowledge_base()

    for cust in get_repository().list_all_customers():
        record = fetch_customer_by_pan(cust.customer.pan_card)
        facts = precompute_facts(
            sanitise_record(record),
            monthly_income_inr=record.customer.income_monthly_paise // 100,
        )
        for label in fire_labels(facts):
            assert kb.get(label.label_id) is not None, f"no KB entry for {label.label_id}"


def test_prompt_builder_works_against_db_kb(seeded_db):
    """prompt_builder.py was not modified; confirm it still assembles."""
    from app.data_fetch import fetch_customer_by_pan
    from app.pii_parser import sanitise_record
    from app.precompute import precompute_facts
    from app.prompt_builder import build_prompt
    from app.rule_engine import fire_labels

    reset_knowledge_base()
    record = fetch_customer_by_pan("ABCPS1234A")
    sanitised = sanitise_record(record)
    facts = precompute_facts(sanitised, monthly_income_inr=75000)
    fired = fire_labels(facts)

    system_prompt, user_message = build_prompt(sanitised, facts, fired)

    assert system_prompt.strip()
    assert "(unrecorded label)" not in user_message
    assert "Maxed Out" in user_message or "Utilization" in user_message
