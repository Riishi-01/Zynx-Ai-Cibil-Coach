"""Shared pytest fixtures for the CIBIL Coach test suite.

Tests run against a temporary copy of the database so the developer's
cibil_coach.db is never mutated by a test run.

IMPORTANT: app/database.py reads DATABASE_URL at module import time and binds
its engine immediately. So DATABASE_URL is set here at conftest import time —
before any `app.*` module is imported — rather than inside a fixture. conftest
is always imported before test modules, which makes the ordering reliable.
"""

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- Bind the test database before any app import ---------------------------
_TMP_DIR = Path(tempfile.mkdtemp(prefix="cibil_coach_tests_"))
_TEST_DB = _TMP_DIR / "cibil_coach.db"
_SRC_DB = PROJECT_ROOT / "cibil_coach.db"

if _SRC_DB.exists():
    shutil.copy2(_SRC_DB, _TEST_DB)

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

# Keep the LLM out of every test run unless a test opts in explicitly.
os.environ.pop("OPENAI_API_KEY", None)

atexit.register(lambda: shutil.rmtree(_TMP_DIR, ignore_errors=True))


def _assert_not_real_db(url: str) -> None:
    """Fail loudly if anything points at the developer's real database.

    A previous version of alembic/env.py ignored DATABASE_URL and always used
    the URL hardcoded in alembic.ini, which meant a test run could mutate the
    real cibil_coach.db. This guard makes any regression of that behaviour an
    immediate, obvious failure instead of silent data loss.
    """
    resolved = url.replace("sqlite:///", "")
    if resolved and Path(resolved).resolve() == _SRC_DB.resolve():
        raise RuntimeError(
            f"Refusing to run: a test is pointed at the real database ({_SRC_DB}). "
            "Check that DATABASE_URL is honoured by alembic/env.py and app/database.py."
        )


@pytest.fixture(scope="session", autouse=True)
def guard_real_database():
    """Assert the engine is bound to the throwaway database, before any test."""
    from app.database import DATABASE_URL, engine

    _assert_not_real_db(DATABASE_URL)
    _assert_not_real_db(str(engine.url))
    yield
    # And confirm nothing repointed it mid-run.
    _assert_not_real_db(str(engine.url))


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def test_db_path() -> Path:
    return _TEST_DB


@pytest.fixture(scope="session")
def kb_json_path(project_root: Path) -> Path:
    """Path to the authored KB fixture."""
    return project_root / "Frontend_docs" / "label_kb.json"


@pytest.fixture(scope="session")
def kb_json(kb_json_path: Path) -> dict:
    """The KB fixture parsed straight from JSON, for comparison against the DB."""
    import json

    return json.loads(kb_json_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def seeded_db() -> str:
    """Migrate the throwaway database and seed the knowledge base once."""
    from app.database import init_db

    init_db()

    from scripts.seed_kb import seed_kb

    seed_kb(reset=True, quiet=True)

    return os.environ["DATABASE_URL"]


@pytest.fixture
def db_session(seeded_db):
    """A session against the throwaway seeded database."""
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
