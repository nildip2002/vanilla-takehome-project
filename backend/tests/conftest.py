"""
conftest.py — Shared pytest fixtures for the backend test suite.

Manages a single isolated SQLite test engine for the entire test session.
All test modules (test_main.py, test_extended.py) share this engine so that
the FastAPI app consistently reads/writes the same in-memory test database.
"""
import os
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, text

# ─── Path Setup ───────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# ─── Shared test engine (set BEFORE any test module imports app/database) ─────
_SHARED_TEST_DB = os.path.join(BACKEND_DIR, ".test_shared.db")
shared_engine = create_engine(
    f"sqlite:///{_SHARED_TEST_DB}",
    connect_args={"check_same_thread": False},
)

# Override the database engine BEFORE importing the app
from database import set_engine_override  # noqa: E402
set_engine_override(shared_engine)
SQLModel.metadata.create_all(shared_engine)


@pytest.fixture(autouse=True, scope="function")
def _reset_tables():
    """Wipe all rows before each test — works across both test files."""
    SQLModel.metadata.create_all(shared_engine)
    yield
    with Session(shared_engine) as session:
        session.exec(text("DELETE FROM executiontrace"))
        session.exec(text("DELETE FROM agenttask"))
        session.exec(text("DELETE FROM systemuser"))
        session.commit()


def pytest_sessionfinish(session, exitstatus):
    """Remove the shared test DB file after the full test session."""
    if os.path.exists(_SHARED_TEST_DB):
        os.unlink(_SHARED_TEST_DB)
