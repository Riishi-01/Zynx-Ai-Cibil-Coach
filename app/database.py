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
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.models import Base

# Resolve alembic config relative to this file, not the process CWD, so that
# migrations work regardless of where the app is launched from.
_PROJECT_ROOT = Path(__file__).parent.parent
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"
_ALEMBIC_DIR = _PROJECT_ROOT / "alembic"


# Determine database URL from environment or use default SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cibil_coach.db")

# Detect dialect. Postgres connects via psycopg2 (driver bundled by Supabase's
# direct-connection string; Vercel installs it via api/requirements.txt).
IS_POSTGRES = DATABASE_URL.startswith(("postgresql://", "postgres://"))
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# Create engine based on database type
if IS_SQLITE:
    # SQLite: use StaticPool for in-memory or file-based, disable check_same_thread for testing
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False} if "memory" in DATABASE_URL else {},
        poolclass=StaticPool if "memory" in DATABASE_URL else None,
    )
else:
    # PostgreSQL or other: use default pooling with pre-ping so stale
    # connections from serverless invocations are recycled.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Track if migrations have been run this session. Not relevant on Postgres —
# schema is created via the SQL Editor, never auto-migrated by the app.
_migrations_run = False


def get_db_session() -> Session:
    """Get a new database session.

    On SQLite, automatically runs pending Alembic migrations on first call
    so a fresh checkout is ready to use. On Postgres this is a no-op — the
    schema is expected to exist already (see docs/supabase_schema.sql).

    Usage:
      session = get_db_session()
      try:
          customer = session.query(CustomerModel).filter_by(pan_card="ABCPS1234A").first()
      finally:
          session.close()
    """
    global _migrations_run

    # Auto-run migrations only on SQLite. Serverless invocations against
    # Postgres must not try to apply SQLite-flavoured revisions.
    if not _migrations_run and IS_SQLITE:
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

    return SessionLocal()


def init_db() -> None:
    """Initialize the database schema (create all tables).

    Called on application startup or manually before seeding.
    On Postgres this is a defensive no-op since the schema is owned by
    docs/supabase_schema.sql.
    """
    if IS_POSTGRES:
        return  # schema managed via SQL Editor
    Base.metadata.create_all(bind=engine)


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
    Base.metadata.drop_all(bind=engine)
