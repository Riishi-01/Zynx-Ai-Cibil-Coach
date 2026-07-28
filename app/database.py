"""Database engine and session management for CIBIL Credit Coach."""

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

# Create engine based on database type
if DATABASE_URL.startswith("sqlite"):
    # SQLite: use StaticPool for in-memory or file-based, disable check_same_thread for testing
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False} if "memory" in DATABASE_URL else {},
        poolclass=StaticPool if "memory" in DATABASE_URL else None,
    )
else:
    # PostgreSQL or other: use default pooling
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Track if migrations have been run this session
_migrations_run = False


def get_db_session() -> Session:
    """Get a new database session.
    
    Automatically runs pending migrations on first call.
    
    Usage:
      session = get_db_session()
      try:
          customer = session.query(CustomerModel).filter_by(pan_card="ABCPS1234A").first()
      finally:
          session.close()
    """
    global _migrations_run

    # Auto-run migrations on first session creation
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

    return SessionLocal()


def init_db() -> None:
    """Initialize the database schema (create all tables).
    
    Called on application startup or manually before seeding.
    """
    Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """Drop all tables (for testing/reset).
    
    WARNING: This is destructive. Use only in development.
    """
    Base.metadata.drop_all(bind=engine)
