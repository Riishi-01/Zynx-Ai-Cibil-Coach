"""Task 1 — schema migration tests.

Verifies the KB tables exist and that adding them left the six customer
tables and their 23 rows untouched.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

KB_TABLES = [
    "kb_labels",
    "kb_mitigation_steps",
    "kb_facts_to_cite",
    "kb_reason_codes",
    "kb_sources",
    "kb_meta",
]

CUSTOMER_TABLES = [
    "customers",
    "scores",
    "accounts",
    "inquiries",
    "collections",
    "public_records",
]


def test_kb_tables_exist(seeded_db):
    from app.database import engine

    tables = set(inspect(engine).get_table_names())
    missing = [t for t in KB_TABLES if t not in tables]
    assert not missing, f"missing KB tables: {missing}"


def test_customer_tables_untouched(seeded_db):
    """The KB migration is purely additive."""
    from app.database import engine

    tables = set(inspect(engine).get_table_names())
    missing = [t for t in CUSTOMER_TABLES if t not in tables]
    assert not missing, f"customer tables disappeared: {missing}"


def test_customer_row_count_still_23(seeded_db):
    from app.database import engine

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar()
    assert count == 23, f"expected 23 customers, found {count}"


def test_kb_labels_columns(seeded_db):
    """kb_labels carries every field the coaching layer needs."""
    from app.database import engine

    cols = {c["name"] for c in inspect(engine).get_columns("kb_labels")}
    expected = {
        "label_id",
        "display_name",
        "category",
        "severity",
        "priority_rank",
        "fact_id",
        "condition",
        "condition_human",
        "what_it_means_cibil",
        "why_it_matters",
        "personalized_response_template",
        "created_at",
        "updated_at",
    }
    assert expected <= cols, f"kb_labels missing columns: {expected - cols}"


def test_migration_upgrade_downgrade_roundtrip(tmp_path, project_root):
    """alembic upgrade head then downgrade -1 runs clean on a fresh database.

    Uses its own empty DB file so the seeded test database is unaffected.
    """
    db_file = tmp_path / "roundtrip.db"
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "DATABASE_URL": f"sqlite:///{db_file}",
        "PYTHONPATH": str(project_root),
    }
    alembic = project_root / ".venv" / "bin" / "alembic"
    if not alembic.exists():
        pytest.skip("alembic executable not present in .venv")

    up = subprocess.run(
        [str(alembic), "upgrade", "head"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert up.returncode == 0, f"upgrade failed:\n{up.stdout}\n{up.stderr}"

    from sqlalchemy import create_engine

    eng = create_engine(f"sqlite:///{db_file}")
    tables = set(inspect(eng).get_table_names())
    eng.dispose()
    assert set(KB_TABLES) <= tables, f"upgrade did not create KB tables: {set(KB_TABLES) - tables}"

    down = subprocess.run(
        [str(alembic), "downgrade", "-1"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"

    eng = create_engine(f"sqlite:///{db_file}")
    tables_after = set(inspect(eng).get_table_names())
    eng.dispose()
    # KB tables gone, customer tables still present.
    assert not (set(KB_TABLES) & tables_after), "downgrade left KB tables behind"
    assert set(CUSTOMER_TABLES) <= tables_after, "downgrade removed customer tables"
