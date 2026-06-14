"""
Database models for the Agentic Execution Framework.

Defines the relational schema using SQLModel for type-safe ORM interactions.
Three core entities: SystemUser, AgentTask, and ExecutionTrace form a
one-to-many chain that captures the full lifecycle of every agent execution.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class SystemUser(SQLModel, table=True):
    """Represents an authenticated system user with role-based access."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    username: str = Field(index=True)
    role_type: str = Field(default="user")  # "admin" or "user"
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    tasks: List["AgentTask"] = Relationship(back_populates="user")


class AgentTask(SQLModel, table=True):
    """
    Represents a single user-submitted task that the agent processes.

    Tracks the raw input, current execution status, and final output.
    Related execution traces provide step-by-step transparency.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="systemuser.id")
    raw_input: str
    execution_status: str = Field(default="pending")  # pending | running | completed | failed
    final_output: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    user: Optional[SystemUser] = Relationship(back_populates="tasks")
    traces: List["ExecutionTrace"] = Relationship(back_populates="task")


class ExecutionTrace(SQLModel, table=True):
    """
    A single step in the agent's reasoning chain.

    Each trace records what the agent thought, which tool it called,
    what the tool returned, or the final synthesized answer.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    task_id: uuid.UUID = Field(foreign_key="agenttask.id", index=True)
    sequence_step: int
    action_category: str  # thought | tool_call | tool_result | tool_error | final_result
    payload_content: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    task: Optional[AgentTask] = Relationship(back_populates="traces")
