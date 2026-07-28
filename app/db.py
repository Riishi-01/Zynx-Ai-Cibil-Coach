"""Repository factory — picks the right backend at call time.

`app.db.get_repository()` is the single entry point used by the rest of the
codebase (data_fetch.py, etc.). It dispatches:

  * If SUPABASE_URL is set (or DATABASE_URL targets Postgres): returns a
    SupabaseRepository via app.supabase_repository. Imported eagerly because
    supabase-py is needed on the production runtime anyway.

  * Otherwise: returns a CustomerRepository (SQLite, ORM-backed) via
    app.sqlite_repository. Imported lazily so SQLAlchemy is never pulled in
    on the Vercel production path — keeps the function bundle ~17 MB lighter.

This module itself is a thin dispatcher and imports nothing heavy at
top-level. `from app.db import get_repository` is safe on Vercel.
"""


def get_repository():
    """Return the right repository for the current backend.

    SQLite path (default local dev): returns CustomerRepository from
    app.sqlite_repository. Lazy-imported so SQLAlchemy is not loaded.

    Postgres path (Supabase in production): returns SupabaseRepository from
    app.supabase_repository. supabase-py is needed on Vercel either way for
    the LangSmith tracing helpers, so importing it eagerly is fine.

    Both expose the same surface (get_by_pan, get_by_customer_id,
    list_all_customers, count) so callers don't need to know which backend
    answered.
    """
    import os
    from app.database import IS_POSTGRES

    if IS_POSTGRES or os.environ.get("SUPABASE_URL"):
        from app.supabase_repository import get_repository as _supabase_get
        return _supabase_get()

    # Lazy: pulls in SQLAlchemy + ORM models only on the SQLite path.
    from app.sqlite_repository import get_repository as _sqlite_get
    return _sqlite_get()