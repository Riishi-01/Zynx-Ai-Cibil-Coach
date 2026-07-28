"""Import data/supabase_seed.json into Supabase Postgres.

Requires:
  * SUPABASE_URL — e.g. https://abcdefgh.supabase.co
  * SUPABASE_SERVICE_ROLE_KEY — from Supabase Settings → API (secret)

Usage:
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \\
        python scripts/import_to_supabase.py [--dry-run]

Strategy
--------
Uses the official supabase-py client's table.insert(). Tables are inserted in
FK-respecting order, so a single transaction could in principle wrap them all.
In practice each table is inserted in one or more batches (Supabase's REST API
accepts at most ~1000 rows per request), and the script reports per-table row
counts so a partial failure is obvious.

This script is idempotent-ish: it will fail on a re-run because the primary
keys collide. If you need to re-seed, drop the affected tables in the Supabase
SQL Editor first or call DELETE FROM <table> with no WHERE clause.

Safety
------
The service_role key bypasses RLS. Use it only from a trusted environment
(typically your local dev machine). Never commit it to git. Never use it in
the frontend.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SEED_PATH = PROJECT_ROOT / "data" / "supabase_seed.json"


# Tables in FK-respecting order. children after parents.
IMPORT_TABLES = [
    "customers",
    "scores",
    "accounts",
    "inquiries",
    "collections",
    "public_records",
    "kb_labels",
    "kb_mitigation_steps",
    "kb_facts_to_cite",
    "kb_reason_codes",
    "kb_sources",
    "kb_meta",
]


def _get_client():
    """Lazy-import and instantiate the Supabase client.

    Reads SUPABASE_URL and a service-role key from the environment. Accepts
    both key formats: the classic JWT `SUPABASE_SERVICE_ROLE_KEY` and the
    new `sb_secret_…` token exposed as `SUPABASE_SECRET_KEY`.

    Raises a helpful error if the URL or any acceptable key is missing.
    """
    url = os.environ.get("SUPABASE_URL")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
    )
    if not url or not key:
        print(
            "ERROR: SUPABASE_URL and a service-role key must be set.",
            file=sys.stderr,
        )
        print(
            "  export SUPABASE_URL=https://xxx.supabase.co",
            file=sys.stderr,
        )
        print(
            "  export SUPABASE_SERVICE_ROLE_KEY=eyJ...  (or SUPABASE_SECRET_KEY=sb_secret_...)",
            file=sys.stderr,
        )
        sys.exit(2)

    # Imported lazily so this script can be --help'd without the dep.
    from supabase import create_client
    return create_client(url, key)


def _insert_table(client, table: str, rows: list[dict], dry_run: bool) -> int:
    """Insert `rows` into `table`. Returns the count actually written."""
    if not rows:
        print(f"  {table}: nothing to insert, skipping")
        return 0

    if dry_run:
        print(f"  {table}: would insert {len(rows)} rows (dry-run)")
        return 0

    # Supabase REST caps inserts at ~1000 rows. The seed is small (max 106),
    # but we batch anyway to stay safe and to report progress on bigger seeds.
    batch_size = 500
    written = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        client.table(table).insert(batch).execute()
        written += len(batch)

    print(f"  {table}: inserted {written} rows")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without contacting Supabase.",
    )
    args = parser.parse_args()

    if not SEED_PATH.exists():
        print(f"ERROR: seed file not found at {SEED_PATH}", file=sys.stderr)
        print("Run scripts/export_sqlite_to_supabase.py first.", file=sys.stderr)
        return 1

    print(f"Loading {SEED_PATH.relative_to(PROJECT_ROOT)}")
    with SEED_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    total_rows = sum(len(payload.get(t, [])) for t in IMPORT_TABLES)
    print(f"Seed contains {total_rows} rows across {len(IMPORT_TABLES)} tables")

    if args.dry_run:
        for table in IMPORT_TABLES:
            _insert_table(None, table, payload.get(table, []), dry_run=True)
        print("\n(dry-run complete; no data was written)")
        return 0

    client = _get_client()

    print("\nInserting in FK order:")
    for table in IMPORT_TABLES:
        rows = payload.get(table, [])
        try:
            _insert_table(client, table, rows, dry_run=False)
        except Exception as exc:
            print(f"  {table}: FAILED — {exc}", file=sys.stderr)
            print(
                "\nIf the error is 'duplicate key value', the table already has rows.\n"
                "Drop affected tables in Supabase SQL Editor or use DELETE FROM <table>.\n"
                "Then re-run this script.",
                file=sys.stderr,
            )
            return 3

    print(f"\nMigration complete. Total: {total_rows} rows across {len(IMPORT_TABLES)} tables.")
    print("Run scripts/verify_supabase_data.py to confirm row counts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())