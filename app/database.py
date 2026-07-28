"""Database engine and session management for CIBIL Credit Coach.

Backends
--------
  * SQLite (default, local dev): file at cibil_coach.db, schema managed by
    Alembic migrations which run on first session.
  * Postgres (Supabase, production): set DATABASE_URL to a postgresql:// URL.
    Schema is managed out-of-band via docs/supabase_schema.sql pasted into the
    Supabase SQL Editor. Auto-migration is skipped — SQLite-flavoured Alembic
    revisions would not run cleanly against Postgres.

The dialect is detected from the URL scheme, so the same models in
app/models.py work against either backend (JsonColumn adapts JSON/JSONB,
DateTime(timezone=True) adapts naive/TIMESTAMPTZ).

Bundle-size note
----------------
SQLAlchemy (and its `Base.metadata` machinery) is heavy — ~17 MB of compiled
modules plus transitive `numpy` if you let it in. On the Vercel function path
the runtime uses Supabase over REST, so SQLAlchemy is never imported. All
SQLAlchemy symbols are imported lazily inside the SQLite-only code paths
(`get_db_session`, `init_db`, `drop_db`). This module remains importable
without pulling SQLAlchemy, so `from app.web import app` on Vercel is lean.
"""

import os
from pathlib import Path


# Determine database URL from environment or use default SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cibil_coach.db")

# Detect dialect. Postgres connects via psycopg2 (driver bundled by Supabase's
# direct-connection string; Vercel installs it via api/requirements.txt).
IS_POSTGRES = DATABASE_URL.startswith(("postgresql://", "postgres://"))
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# Engine and sessionmaker are constructed lazily — only on the SQLite path.
# On Postgres, callers go through app/supabase_repository.py which uses the
# supabase-py REST client (no SQLAlchemy required at runtime).
_engine = None
_SessionLocal = None
_migrations_run = False


def _get_engine():
    """Return the SQLAlchemy engine, building it on first call (SQLite only)."""
    global _engine, _SessionLocal
    if _engine is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        _engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False} if "memory" in DATABASE_URL else {},
            poolclass=StaticPool if "memory" in DATABASE_URL else None,
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def _get_session_factory():
    """Return the sessionmaker, building it on first call (SQLite only)."""
    _get_engine()  # ensure engine + sessionmaker are constructed together
    return _SessionLocal


# Resolve alembic config relative to this file, not the process CWD, so that
# migrations work regardless of where the app is launched from. Used only on
# the SQLite path; on Postgres the schema is owned by docs/supabase_schema.sql.
_PROJECT_ROOT = Path(__file__).parent.parent
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"
_ALEMBIC_DIR = _PROJECT_ROOT / "alembic"


def get_db_session():
    """Get a new database session.

    On SQLite, automatically runs pending Alembic migrations on first call
    so a fresh checkout is ready to use. On Postgres this is a no-op — the
    schema is expected to exist already (see docs/supabase_schema.sql).

    Note: returns an SQLAlchemy Session only when IS_SQLITE is true. On
    Postgres the function raises RuntimeError so the caller fails fast
    rather than silently using a misconfigured engine.

    Usage:
      session = get_db_session()
      try:
          customer = session.query(CustomerModel).filter_by(pan_card="ABCPS1234A").first()
      finally:
          session.close()
    """
    if not IS_SQLITE:
        raise RuntimeError(
            "get_db_session() is only valid on SQLite. On Postgres use "
            "app.supabase_repository.get_repository() instead."
        )

    global _migrations_run

    # Auto-run migrations only on SQLite. Serverless invocations against
    # Postgres must not try to apply SQLite-flavoured revisions.
    if not _migrations_run:
        try:
            import alembic.config
            import alembic.command

            alembic_cfg = alembic.config.Config(str(_ALEMBIC_INI))
            # Point alembic at the same database this module is bound to.
            # alembic.ini hardcodes sqlite:///./cibil_coach.db, so without this
            # override the migration would run against the wrong database
            # whenever DATABASE_URL differs (tests, staging, production).
            alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
            alembic_cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
            # upgrade() returns the current version; we just call it for side effects
            alembic.command.upgrade(alembic_cfg, "head")
        except Exception:
            # Silently ignore migration errors (schema may already exist)
            pass
        finally:
            _migrations_run = True  # Mark as run regardless to prevent retries

    return _get_session_factory()()


def init_db() -> None:
    """Initialize the database schema (create all tables).

    Called on application startup or manually before seeding.
    On Postgres this is a defensive no-op since the schema is owned by
    docs/supabase_schema.sql.
    """
    if IS_POSTGRES:
        return  # schema managed via SQL Editor
    from app.models import Base
    Base.metadata.create_all(bind=_get_engine())


def drop_db() -> None:
    """Drop all tables (for testing/reset).

    WARNING: This is destructive. Use only in development.
    Refuses to run against Postgres to protect the Supabase project.
    """
    if IS_POSTGRES:
        raise RuntimeError(
            "drop_db() refused: Postgres schema is managed via docs/supabase_schema.sql. "
            "Drop tables manually in the Supabase dashboard if you really mean it."
        )
    from app.models import Base
    Base.metadata.drop_all(bind=_get_engine())