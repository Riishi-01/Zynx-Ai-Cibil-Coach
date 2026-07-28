"""Supabase-backed customer repository.

Parallel implementation to CustomerRepository (which targets SQLite). Both
classes expose the same surface — get_by_pan(), get_by_customer_id(),
list_all_customers(), count() — so callers in app/data_fetch.py and the
pipeline orchestrators are backend-agnostic.

Selection happens once at import time in get_repository(): if SUPABASE_URL is
set in the environment, SupabaseRepository is instantiated; otherwise the
SQLite repository takes over. This keeps the local-dev experience (run a
script with no env vars → reads cibil_coach.db) identical to before, while
the Vercel deployment routes through Supabase via the service_role key.

Schema expectations are documented in docs/supabase_schema.sql. Both backends
return the same Pydantic types from app.schemas (CustomerRecord, Customer,
Score, Account, etc.), so no downstream code needs to know which backend
answered.

NOTE on JSONB columns
---------------------
The supabase-py REST client returns JSONB columns as `str` (raw JSON
text), not as a parsed list/dict. Every consumer of payment_history,
kb_meta.value, or any other JSONB field needs to json.loads() the value
first. _coerce_jsonb() centralises that coercion.

NOTE: this module imports the supabase SDK lazily so test environments and
CLI scripts that don't need Supabase don't pay the import cost or fail when
the package is missing.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Optional

from app.schemas import (
    Account,
    AccountStatus,
    AccountType,
    Collection,
    Customer,
    CustomerNotFound,
    CustomerRecord,
    Inquiry,
    PublicRecord,
    Score,
    ScoreBand,
)


def _coerce_jsonb(value: Any) -> Any:
    """Decode JSONB columns returned by supabase-py as raw strings.

    The supabase-py REST client (v2.20+) returns JSONB columns as their
    raw JSON text. SQLite's ORM returns them already-decoded as lists /
    dicts. This helper normalises both shapes to the decoded form so
    downstream Pydantic models receive the type they expect.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value  # leave it as-is if it isn't JSON
    return value


class SupabaseRepository:
    """Read customer credit profiles from Supabase Postgres.

    Uses the supabase-py REST client, so it works from serverless functions
    without a long-lived TCP connection. Trade-off: every call is a network
    round-trip (~50-200ms), so list_all_customers() fans out into one query
    per parent table — fine for 23 customers, would need rethinking at
    thousands.
    """

    def __init__(self, client):
        # `client` is a supabase.Client. Injected so tests can pass a mock.
        self._client = client

    # ----------------------------------------------------------------- reads --

    def get_by_pan(self, pan_card: str) -> CustomerRecord:
        """Fetch a customer record by PAN. Raises CustomerNotFound if absent."""
        cust = self._fetch_customer_row(pan_card)
        return self._reconstruct(cust)

    def get_by_customer_id(self, customer_id: str) -> CustomerRecord:
        """Fetch a customer record by customer_id."""
        resp = (
            self._client.table("customers")
            .select("pan_card")
            .eq("customer_id", customer_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise CustomerNotFound(f"Unknown customer ID {customer_id}")
        return self.get_by_pan(rows[0]["pan_card"])

    def list_all_customers(self) -> list[CustomerRecord]:
        """Return every customer. Linear in customer count."""
        resp = self._client.table("customers").select("pan_card").execute()
        return [self.get_by_pan(row["pan_card"]) for row in (resp.data or [])]

    def count(self) -> int:
        """Return the count of customers."""
        resp = self._client.table("customers").select("*", count="exact").limit(0).execute()
        return resp.count or 0

    # ---------------------------------------------------------- internals ----

    def _fetch_customer_row(self, pan_card: str) -> dict:
        """Load one customer with all related rows in a single REST query.

        Supabase's embed syntax returns nested rows in one round-trip:
            ?select=*,accounts(*),inquiries(*),collections(*),public_records(*)
        Scores live in their own 1-to-1 table, fetched in a follow-up.
        """
        resp = (
            self._client.table("customers")
            .select(
                "pan_card, customer_id, first_name, dob_year, income_bracket, "
                "income_monthly_paise, region, "
                "accounts(*), inquiries(*), collections(*), public_records(*)"
            )
            .eq("pan_card", pan_card)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise CustomerNotFound(f"No credit file for PAN {pan_card}")
        cust = rows[0]

        # Scores are 1-to-1; one extra round-trip. Could be embedded if we
        # added the FK to a scores view, but this is plenty fast for 23 PANs.
        score_resp = (
            self._client.table("scores")
            .select("*")
            .eq("pan_card", pan_card)
            .limit(1)
            .execute()
        )
        score_rows = score_resp.data or []
        cust["score_row"] = score_rows[0] if score_rows else None
        return cust

    @staticmethod
    def _reconstruct(cust: dict) -> CustomerRecord:
        """Build a CustomerRecord Pydantic object from a Supabase row dict."""
        customer = Customer(
            customer_id=cust["customer_id"],
            first_name=cust["first_name"],
            dob_year=cust["dob_year"],
            income_bracket=cust["income_bracket"],
            income_monthly_paise=cust["income_monthly_paise"],
            region=cust["region"],
            pan_card=cust["pan_card"],
        )

        score: Optional[Score] = None
        score_row = cust.get("score_row")
        if score_row:
            score = Score(
                score=score_row["score"],
                previous_score_1mo=score_row.get("previous_score_1mo"),
                previous_score_3mo=score_row.get("previous_score_3mo"),
                band=ScoreBand(score_row["band"]),
                score_as_of_date=_parse_date(score_row["score_as_of_date"]),
            )

        accounts = [
            Account(
                account_id=acc["account_id"],
                display_name=acc["display_name"],
                account_type=AccountType(acc["account_type"]),
                balance_paise=acc["balance_paise"],
                credit_limit_paise=acc.get("credit_limit_paise"),
                monthly_payment_paise=acc["monthly_payment_paise"],
                opened_date=_parse_date(acc["opened_date"]),
                status=AccountStatus(acc["status"]),
                is_revolving=bool(acc["is_revolving"]),
                payment_history=list(_coerce_jsonb(acc.get("payment_history")) or []),
            )
            for acc in cust.get("accounts", [])
        ]

        inquiries = [
            Inquiry(
                inquiry_id=inq["inquiry_id"],
                creditor_name=inq["creditor_name"],
                inquiry_date=_parse_date(inq["inquiry_date"]),
                inquiry_type=inq["inquiry_type"],
            )
            for inq in cust.get("inquiries", [])
        ]

        collections = [
            Collection(
                collection_id=col["collection_id"],
                original_creditor=col["original_creditor"],
                collection_agency=col.get("collection_agency"),
                balance_paise=col["balance_paise"],
                opened_date=_parse_date(col["opened_date"]),
                status=col["status"],
                is_past_sol=bool(col.get("is_past_sol", False)),
                is_disputable=bool(col.get("is_disputable", False)),
                is_medical=bool(col.get("is_medical", False)),
            )
            for col in cust.get("collections", [])
        ]

        public_records = [
            PublicRecord(
                record_id=pr["record_id"],
                record_type=pr["record_type"],
                filed_date=_parse_date(pr["filed_date"]),
                amount_paise=pr.get("amount_paise"),
                status=pr.get("status"),
                jurisdiction=pr.get("jurisdiction"),
            )
            for pr in cust.get("public_records", [])
        ]

        return CustomerRecord(
            customer=customer,
            score=score,
            accounts=accounts,
            inquiries=inquiries,
            collections=collections,
            public_records=public_records,
        )


def _parse_date(value) -> date:
    """Coerce a string/datetime from Supabase into a date.

    Supabase returns DATE columns as 'YYYY-MM-DD' strings, but TIMESTAMPTZ
    columns can leak through when embed-joined. Handle both.
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.fromisoformat(str(value)).date()


# ============================================================ factory =====


from app.database import IS_POSTGRES  # noqa: E402  (kept here so the SQLite path doesn't pay the supabase import)


def _build_supabase_repository():
    """Instantiate SupabaseRepository using the service-role key from env.

    Realtime is disabled explicitly. We use supabase-py only for its
    PostgREST client (customers, scores, KB tables) — never for websockets.
    Leaving realtime on creates an inert SyncRealtimeClient whose
    auto_reconnect background behaviour can produce confusing log noise
    (and in some Supabase projects with Realtime toggled off, websocket
    handshake rejections). Setting auto_reconnect=False here short-circuits
    that side of the client entirely — the SyncRealtimeClient object still
    exists but never attempts to open a websocket.
    """
    import os

    from supabase import ClientOptions, create_client

    url = os.environ.get("SUPABASE_URL")
    # Accept both the classic JWT (SUPABASE_SERVICE_ROLE_KEY) and the new
    # sb_secret_… token (SUPABASE_SECRET_KEY) introduced in late 2024.
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
    )
    if not url or not key:
        raise RuntimeError(
            "SupabaseRepository requires SUPABASE_URL and a service-role key "
            "(SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY). Both must be set "
            "in the environment when DATABASE_URL targets Postgres."
        )

    options = ClientOptions(
        realtime={
            "auto_reconnect": False,  # never auto-open websocket
            "hb_interval": 0,         # never heartbeat
            "max_retries": 0,         # never retry connect
            "initial_backoff": 0.0,
        },
    )
    return SupabaseRepository(create_client(url, key, options=options))


def get_repository():
    """Return the right repository for the current backend.

    On SQLite (default local dev): returns the existing SQLAlchemy-backed
    CustomerRepository. On Postgres (Supabase): returns SupabaseRepository
    wrapping a supabase-py client. Both expose the same get_by_pan() /
    get_by_customer_id() / list_all_customers() / count() surface.

    Selection: the Supabase repo activates when EITHER DATABASE_URL targets
    Postgres (classic path, used by SQLAlchemy) OR SUPABASE_URL is set with
    a service-role key (typical Vercel deploy — the supabase-py client uses
    SUPABASE_URL directly, not DATABASE_URL).
    """
    from app.database import IS_POSTGRES
    import os

    if IS_POSTGRES or os.environ.get("SUPABASE_URL"):
        return _build_supabase_repository()

    # Lazy import so the SQLite path doesn't import the supabase SDK.
    # Note: this branch is unreachable through app.db.get_repository() (the
    # canonical entry point dispatches to app.sqlite_repository instead), but
    # keeping the fallback correct lets tests call this function directly.
    from app.sqlite_repository import CustomerRepository
    return CustomerRepository()