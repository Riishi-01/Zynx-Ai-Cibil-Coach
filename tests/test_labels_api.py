"""Task 6 — labels API tests.

Covers the service output shape and the HTTP endpoint, for all 23 customers.
"""

import pytest

from app.api_schemas import LabelsResponse
from app.label_service import SEVERITY_ORDER, build_labels_response
from app.template_renderer import unresolved_placeholders


@pytest.fixture
def client(seeded_db):
    """A FastAPI test client bound to the throwaway database."""
    from fastapi.testclient import TestClient

    from app.web import app

    return TestClient(app)


@pytest.fixture
def all_pans(seeded_db):
    from app.db import get_repository

    return [c.customer.pan_card for c in get_repository().list_all_customers()]


# ------------------------------------------------------------- the service ----


def test_returns_all_32_labels(seeded_db):
    response = build_labels_response("ABCPS1234A")
    assert response.total_labels == 32
    assert len(response.labels) == 32


def test_returns_32_for_every_customer(all_pans, seeded_db):
    for pan in all_pans:
        response = build_labels_response(pan)
        assert len(response.labels) == 32, f"{pan} returned {len(response.labels)}"


def test_schema_validates_for_every_customer(all_pans, seeded_db):
    for pan in all_pans:
        LabelsResponse.model_validate(build_labels_response(pan).model_dump())


def test_labels_ordered_by_priority_rank(seeded_db):
    ranks = [label.priority_rank for label in build_labels_response("BCDRM2345B").labels]
    assert ranks == sorted(ranks)


def test_fired_flags_match_rule_engine(all_pans, seeded_db):
    """The API's fired flags must agree with fire_labels() exactly."""
    from app.label_service import run_pipeline

    for pan in all_pans:
        _, _, _, fired = run_pipeline(pan)
        expected = {f.label_id for f in fired}

        response = build_labels_response(pan)
        actual = {label.label_id for label in response.labels if label.fired}

        assert actual == expected, f"{pan}: {actual ^ expected}"


def test_n_fired_matches_fired_labels(seeded_db):
    response = build_labels_response("BCDRM2345B")
    assert response.n_fired == sum(1 for label in response.labels if label.fired)
    assert 0 < response.n_fired < 32


def test_unfired_labels_have_no_instances(seeded_db):
    response = build_labels_response("CDEPI3456C")
    for label in response.labels:
        if not label.fired:
            assert label.instances == []


def test_fired_labels_have_at_least_one_instance(all_pans, seeded_db):
    for pan in all_pans:
        for label in build_labels_response(pan).labels:
            if label.fired:
                assert label.instances, f"{pan}/{label.label_id} fired with no instance"


def test_unfired_labels_still_carry_kb_copy(seeded_db):
    """The UI dims unfired labels but still shows what they check for."""
    response = build_labels_response("CDEPI3456C")
    unfired = [label for label in response.labels if not label.fired]
    assert unfired, "expected some labels not to fire for a healthy profile"
    for label in unfired:
        assert label.display_name.strip()
        assert label.condition_human.strip()
        assert label.why_it_matters.strip()


def test_per_account_label_yields_one_instance_per_account(seeded_db):
    """Carlos has two maxed cards, so maxed_out_account fires twice."""
    response = build_labels_response("BCDRM2345B")
    maxed = next(label for label in response.labels if label.label_id == "maxed_out_account")

    assert maxed.fired
    assert len(maxed.instances) == 2

    account_ids = {instance.account_id for instance in maxed.instances}
    assert account_ids == {"acc_002_1", "acc_002_2"}

    names = {instance.account_name for instance in maxed.instances}
    assert names == {"Axis Bank Neo", "Kotak League Platinum"}


def test_instance_messages_are_rendered_and_clean(all_pans, seeded_db):
    """No instance may contain an unrendered placeholder."""
    for pan in all_pans:
        for label in build_labels_response(pan).labels:
            for instance in label.instances:
                assert instance.message.strip(), f"{pan}/{label.label_id}: empty message"
                assert not unresolved_placeholders(instance.message)
                for step in instance.mitigation_steps:
                    assert not unresolved_placeholders(step)


def test_facts_to_cite_are_resolved_to_values(seeded_db):
    """Anjali's high_utilization label cites her real numbers."""
    response = build_labels_response("ABCPS1234A")
    label = next(l for l in response.labels if l.label_id == "high_utilization")

    assert label.facts_to_cite["total_balance_paise"] == 515000
    assert label.facts_to_cite["total_credit_limit_paise"] == 900000
    assert label.facts_to_cite["overall_utilization"] == pytest.approx(0.5722, abs=1e-3)


def test_facts_to_cite_resolved_for_unfired_labels_too(seeded_db):
    """Unfired labels still resolve their facts so the UI can explain them."""
    response = build_labels_response("CDEPI3456C")
    unfired_with_facts = [
        label for label in response.labels if not label.fired and label.facts_to_cite
    ]
    assert unfired_with_facts


def test_alias_fact_names_resolve_in_response(seeded_db):
    """perfect_payment cites n_late_30d, which is an alias."""
    response = build_labels_response("CDEPI3456C")
    label = next(l for l in response.labels if l.label_id == "perfect_payment")
    assert "n_late_30d" in label.facts_to_cite
    assert label.facts_to_cite["n_late_30d"] == 0


def test_sources_and_reason_codes_present(seeded_db):
    response = build_labels_response("BCDRM2345B")
    maxed = next(label for label in response.labels if label.label_id == "maxed_out")
    assert maxed.cibil_reason_codes == ["2"]
    assert any("cibil.com" in source.url for source in maxed.sources)


def test_fired_by_severity_buckets(seeded_db):
    """Carlos's critical bucket leads with the maxed-out labels."""
    response = build_labels_response("BCDRM2345B")

    assert set(response.fired_by_severity) >= set(SEVERITY_ORDER)

    critical = response.fired_by_severity["critical"]
    assert "maxed_out" in critical
    assert "all_cards_maxed" in critical

    # Only fired labels appear in the buckets.
    bucketed = {lid for ids in response.fired_by_severity.values() for lid in ids}
    fired = {label.label_id for label in response.labels if label.fired}
    assert bucketed == fired


def test_overlapping_utilisation_tiers_are_ordered_not_suppressed(seeded_db):
    """The rule engine still fires all three tiers; the API orders them.

    This pins the agreed behaviour: the engine is untouched, and presentation
    puts the critical label ahead of the softer tiers.
    """
    response = build_labels_response("BCDRM2345B")
    fired_order = [label.label_id for label in response.labels if label.fired]

    assert "maxed_out" in fired_order
    assert "very_high_utilization" in fired_order
    assert fired_order.index("maxed_out") < fired_order.index("very_high_utilization")


def test_income_override_changes_dti_labels(seeded_db):
    """Passing a low income should push a profile into severe DTI."""
    default = build_labels_response("MNOPQ3456M")
    overridden = build_labels_response("MNOPQ3456M", monthly_income_inr=20000)

    assert not any(l.label_id == "severe_dti" and l.fired for l in default.labels)
    assert any(l.label_id == "severe_dti" and l.fired for l in overridden.labels)


def test_pan_is_masked_in_response(seeded_db):
    response = build_labels_response("ABCPS1234A")
    assert response.pan_masked == "ABCPS****A"
    assert "ABCPS1234A" not in response.model_dump_json()


def test_no_credit_history_customer(seeded_db):
    """Sana has no accounts; the endpoint must still return all 32 labels."""
    response = build_labels_response("HIJPL8901H")
    assert len(response.labels) == 32
    assert response.n_fired > 0


def test_coverage_contract_across_all_customers(all_pans, seeded_db):
    """Every one of the 32 labels fires for at least one customer."""
    fired = set()
    for pan in all_pans:
        fired.update(label.label_id for label in build_labels_response(pan).labels if label.fired)
    assert len(fired) == 32, f"never fired: {32 - len(fired)} labels"


# ---------------------------------------------------------------- endpoint ----


def test_endpoint_returns_200(client):
    response = client.post("/api/labels", json={"pan": "ABCPS1234A", "income": 75000})
    assert response.status_code == 200

    body = response.json()
    assert body["total_labels"] == 32
    assert len(body["labels"]) == 32
    assert body["score"] == 715


def test_endpoint_income_is_optional(client):
    response = client.post("/api/labels", json={"pan": "ABCPS1234A"})
    assert response.status_code == 200


def test_endpoint_lowercases_pan_input(client):
    response = client.post("/api/labels", json={"pan": "abcps1234a"})
    assert response.status_code == 200
    assert response.json()["pan_masked"] == "ABCPS****A"


def test_endpoint_requires_pan(client):
    assert client.post("/api/labels", json={}).status_code == 400


def test_endpoint_rejects_malformed_pan(client):
    assert client.post("/api/labels", json={"pan": "NOTAPAN"}).status_code == 400


def test_endpoint_404_for_unknown_pan(client):
    """Format-valid but not in the database."""
    response = client.post("/api/labels", json={"pan": "ZZZPZ9999Z"})
    assert response.status_code == 404


def test_endpoint_rejects_non_numeric_income(client):
    response = client.post("/api/labels", json={"pan": "ABCPS1234A", "income": "abc"})
    assert response.status_code == 400


def test_endpoint_rejects_zero_income(client):
    response = client.post("/api/labels", json={"pan": "ABCPS1234A", "income": 0})
    assert response.status_code == 400


def test_endpoint_response_is_json_serialisable(client):
    """Facts include dicts, dates and enums; all must serialise."""
    response = client.post("/api/labels", json={"pan": "BCDRM2345B"})
    assert response.status_code == 200

    body = response.json()
    concentration = next(
        l for l in body["labels"] if l["label_id"] == "utilization_concentration"
    )
    # account_utilizations is a dict fact and must survive serialisation.
    assert isinstance(concentration["facts_to_cite"]["account_utilizations"], dict)
