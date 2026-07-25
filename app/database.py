"""Database engine and session management for CIBIL Credit Coach."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.models import Base


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
            alembic_cfg = alembic.config.Config("alembic.ini")
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
