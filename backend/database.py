"""
Database engine configuration and session management.

Supports SQLite for local development and PostgreSQL for production.
The connection string is configurable via the DATABASE_URL environment variable.
"""

import os
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine

from models import AgentTask, ExecutionTrace, SystemUser  # noqa: F401 — ensure tables are registered

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")

# SQLite requires check_same_thread=False for FastAPI's async threading model.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

# Allow tests to inject a different engine
_engine_override: Optional[object] = None


def set_engine_override(eng):
    """Override the engine used by get_session (for testing)."""
    global _engine_override
    _engine_override = eng


def get_active_engine():
    """Return the currently active engine (override or default)."""
    return _engine_override or engine


def create_db_and_tables() -> None:
    """Create all tables defined by SQLModel metadata."""
    SQLModel.metadata.create_all(get_active_engine())


def get_session():
    """FastAPI dependency that yields a database session per request."""
    with Session(get_active_engine()) as session:
        yield session
