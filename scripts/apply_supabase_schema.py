"""Apply docs/supabase_schema.sql to a Supabase Postgres database via psycopg.

Runs the entire schema file in one transaction. Safe to re-run: every CREATE
uses IF NOT EXISTS, and policies use CREATE POLICY which is idempotent in
Postgres when the policy name already exists.

Usage:
    SUPABASE_PROJECT_REF=hhvgsbhrihvrvymuzxki \\
    SUPABASE_DB_PASSWORD=voDRrXUvWT0mjp4q \\
        python scripts/apply_supabase_schema.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = PROJECT_ROOT / "docs" / "supabase_schema.sql"


def main() -> int:
    project_ref = os.environ.get("SUPABASE_PROJECT_REF")
    password = os.environ.get("SUPABASE_DB_PASSWORD")
    if not project_ref or not password:
        print(
            "ERROR: SUPABASE_PROJECT_REF and SUPABASE_DB_PASSWORD must be set.",
            file=sys.stderr,
        )
        print(
            "  export SUPABASE_PROJECT_REF=hhvgsbhrihvrvymuzxki",
            file=sys.stderr,
        )
        print("  export SUPABASE_DB_PASSWORD=...", file=sys.stderr)
        return 2

    if not SCHEMA_PATH.exists():
        print(f"ERROR: schema file not found at {SCHEMA_PATH}", file=sys.stderr)
        return 1

    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    print(f"Loaded {len(sql):,} chars of SQL from {SCHEMA_PATH.relative_to(PROJECT_ROOT)}")

    # Direct (non-pooler) connection. The pooler is on port 6543 with a
    # different username format (postgres.PROJECTREF) which is awkward;
    # direct on 5432 with user=postgres is the most reliable path for DDL.
    conn_str = (
        f"postgresql://postgres:{password}"
        f"@db.{project_ref}.supabase.co:5432/postgres"
    )

    # Imported lazily so --help works without the dependency.
    import psycopg

    print(f"Connecting to db.{project_ref}.supabase.co:5432 ...")
    with psycopg.connect(conn_str, autocommit=False) as conn:
        with conn.cursor() as cur:
            # Execute the entire file as one batch. psycopg splits on
            # semicolons internally and runs each statement; a failure on
            # any statement aborts the transaction.
            cur.execute(sql)
        conn.commit()

    print("Schema applied successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())