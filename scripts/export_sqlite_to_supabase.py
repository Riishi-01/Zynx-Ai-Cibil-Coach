"""Export all data from SQLite to a single JSON seed file.

This is the one-shot migration step before deploying to Supabase. It reads
every row from cibil_coach.db, normalises the types so they round-trip cleanly
through Postgres, and writes data/supabase_seed.json.

Usage:
    python scripts/export_sqlite_to_supabase.py
    # writes data/supabase_seed.json

The output JSON is shaped for scripts/import_to_supabase.py (or the Supabase
SQL Editor via INSERT ... SELECT FROM jsonb_to_recordset()) — one array per
table, in FK-respecting insertion order.

The script is read-only against SQLite. It never touches the database file
apart from SELECT queries, so re-running it is safe.

NOTE on numbers: monetary amounts are stored as paise (integer). SQLite's
INTEGER is unbounded and Python's json module serialises them as-is. Postgres
BIGINT accepts the full int64 range without loss.

NOTE on dates: Python's date/datetime objects become ISO 8601 strings. The
Supabase schema accepts ISO strings for DATE and TIMESTAMPTZ columns.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "cibil_coach.db"
OUTPUT_PATH = PROJECT_ROOT / "data" / "supabase_seed.json"


# Tables to export, in FK-respecting order. Each entry maps to a JSON array
# in the output. Children come after parents.
EXPORT_TABLES = [
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


def _serialise(value):
    """Coerce SQLite row values into JSON-safe forms.

    SQLite returns dates as 'YYYY-MM-DD' strings and timestamps as 'YYYY-MM-DD HH:MM:SS'
    strings. We leave them as strings — Postgres accepts ISO 8601 for DATE and
    TIMESTAMPTZ columns, so no client-side conversion is needed.
    """
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _dump_table(conn: sqlite3.Connection, table: str) -> list[dict]:
    """Dump every row of `table` as a list of dicts, with types normalised."""
    cur = conn.execute(f"SELECT * FROM {table}")
    columns = [col[0] for col in cur.description]
    rows = []
    for raw in cur.fetchall():
        row = {col: _serialise(value) for col, value in zip(columns, raw)}
        rows.append(row)
    return rows


def main() -> int:
    if not DB_PATH.exists():
        print(f"ERROR: SQLite database not found at {DB_PATH}", file=sys.stderr)
        print("Run scripts/seed_db.py and scripts/seed_kb.py first.", file=sys.stderr)
        return 1

    print(f"Reading from {DB_PATH}")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = None  # default tuple rows; we handle dicts manually
        payload: dict[str, list[dict]] = {}
        for table in EXPORT_TABLES:
            rows = _dump_table(conn, table)
            payload[table] = rows
            print(f"  {table}: {len(rows)} rows")

    with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    print(f"\nWrote {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    total_rows = sum(len(rows) for rows in payload.values())
    print(f"Total rows: {total_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())