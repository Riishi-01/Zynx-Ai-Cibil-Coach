"""Verify that Supabase row counts match the SQLite source-of-truth.

This is the post-migration parity check. Reads the same SQLite DB that
scripts/export_sqlite_to_supabase.py reads from, queries Supabase for the
matching row counts, and reports any drift.

Usage:
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \\
        python scripts/verify_supabase_data.py

Exit code is 0 when every table matches, 1 when any drift is detected.

The script also does one spot-check: it fetches the Anjali customer
(pan_card = ABCPS1234A) along with all her accounts, and prints them.
That's enough to confirm joins and column types round-tripped correctly.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "cibil_coach.db"


TABLES = [
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
        sys.exit(2)

    from supabase import create_client
    return create_client(url, key)


def _sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _supabase_count(client, table: str) -> int:
    # count='exact' is required to get the real count, otherwise Supabase
    # returns None and we cannot compare.
    response = client.table(table).select("*", count="exact").limit(0).execute()
    return response.count or 0


def main() -> int:
    if not DB_PATH.exists():
        print(f"ERROR: SQLite database not found at {DB_PATH}", file=sys.stderr)
        return 1

    client = _get_client()

    print(f"{'table':<25} {'sqlite':>10} {'supabase':>10} {'drift':>10}")
    print("-" * 60)

    drift_tables: list[str] = []

    with sqlite3.connect(DB_PATH) as conn:
        for table in TABLES:
            sqlite_n = _sqlite_count(conn, table)
            try:
                supabase_n = _supabase_count(client, table)
            except Exception as exc:
                print(f"{table:<25} {sqlite_n:>10} {'ERR':>10}     {exc}")
                drift_tables.append(table)
                continue

            drift = supabase_n - sqlite_n
            marker = " OK" if drift == 0 else " !!"
            print(f"{table:<25} {sqlite_n:>10} {supabase_n:>10} {drift:>+10}{marker}")
            if drift != 0:
                drift_tables.append(table)

    print()
    if drift_tables:
        print(f"DRIFT DETECTED on {len(drift_tables)} table(s): {drift_tables}")
        return 1

    print("All row counts match. Migration is parity-clean.")

    # Spot-check: Anjali's record with her accounts.
    print("\nSpot check — Anjali (ABCPS1234A):")
    try:
        resp = (
            client.table("customers")
            .select("first_name, pan_card, accounts(account_id, display_name, balance_paise)")
            .eq("pan_card", "ABCPS1234A")
            .single()
            .execute()
        )
        cust = resp.data
        print(f"  name: {cust['first_name']}, pan: {cust['pan_card']}")
        for acc in cust.get("accounts", []):
            print(f"  - {acc['display_name']}: ₹{acc['balance_paise'] / 100:,.2f} balance")
    except Exception as exc:
        print(f"  spot-check failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())