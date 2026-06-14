"""
Repository Pattern — Database-agnostic data access layer.

Provides a unified interface for task/trace/user persistence that works with:
  - SQLite/SQLModel (local development, DATABASE_BACKEND=sqlite)
  - Azure Cosmos DB (cloud deployment, DATABASE_BACKEND=cosmos)

The active backend is selected by the DATABASE_BACKEND environment variable.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from models import AgentTask, ExecutionTrace, SystemUser


@runtime_checkable
class Repository(Protocol):
    """Protocol for database operations."""

    def create_user(self, username: str, role_type: str = "user") -> dict: ...
    def get_user(self, user_id: str) -> dict | None: ...
    def create_task(self, user_id: str, raw_input: str) -> dict: ...
    def get_task(self, task_id: str) -> dict | None: ...
    def update_task(self, task_id: str, **fields) -> dict | None: ...
    def list_tasks(self) -> list[dict]: ...
    def create_trace(self, task_id: str, step: int, category: str, content: str) -> dict: ...
    def get_traces(self, task_id: str) -> list[dict]: ...


class SQLModelRepository:
    """Repository backed by SQLModel (SQLite/PostgreSQL)."""

    def __init__(self, session):
        self._session = session

    def create_user(self, username: str, role_type: str = "user") -> dict:
        user = SystemUser(username=username, role_type=role_type)
        self._session.add(user)
        self._session.commit()
        self._session.refresh(user)
        return {"id": str(user.id), "username": user.username, "role_type": user.role_type}

    def get_user(self, user_id: str) -> dict | None:
        try:
            user = self._session.get(SystemUser, uuid.UUID(user_id))
        except ValueError:
            return None
        if not user:
            return None
        return {"id": str(user.id), "username": user.username, "role_type": user.role_type}

    def create_task(self, user_id: str, raw_input: str) -> dict:
        task = AgentTask(user_id=uuid.UUID(user_id), raw_input=raw_input, execution_status="pending")
        self._session.add(task)
        self._session.commit()
        self._session.refresh(task)
        return {
            "id": str(task.id),
            "user_id": str(task.user_id),
            "raw_input": task.raw_input,
            "execution_status": task.execution_status,
            "final_output": task.final_output,
            "created_at": task.created_at.isoformat(),
        }

    def get_task(self, task_id: str) -> dict | None:
        try:
            task = self._session.get(AgentTask, uuid.UUID(task_id))
        except ValueError:
            return None
        if not task:
            return None
        return {
            "id": str(task.id),
            "user_id": str(task.user_id),
            "raw_input": task.raw_input,
            "execution_status": task.execution_status,
            "final_output": task.final_output,
            "created_at": task.created_at.isoformat(),
        }

    def update_task(self, task_id: str, **fields) -> dict | None:
        try:
            task = self._session.get(AgentTask, uuid.UUID(task_id))
        except ValueError:
            return None
        if not task:
            return None
        for key, value in fields.items():
            setattr(task, key, value)
        self._session.add(task)
        self._session.commit()
        self._session.refresh(task)
        return self.get_task(task_id)

    def list_tasks(self) -> list[dict]:
        from sqlmodel import select
        tasks = self._session.exec(
            select(AgentTask).order_by(AgentTask.created_at.desc())
        ).all()
        return [
            {
                "id": str(t.id),
                "raw_input": t.raw_input,
                "execution_status": t.execution_status,
                "final_output": t.final_output,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]

    def create_trace(self, task_id: str, step: int, category: str, content: str) -> dict:
        trace = ExecutionTrace(
            task_id=uuid.UUID(task_id),
            sequence_step=step,
            action_category=category,
            payload_content=content,
        )
        self._session.add(trace)
        self._session.commit()
        self._session.refresh(trace)
        return {
            "id": str(trace.id),
            "task_id": task_id,
            "step": trace.sequence_step,
            "type": trace.action_category,
            "content": trace.payload_content,
            "timestamp": trace.timestamp.isoformat(),
        }

    def get_traces(self, task_id: str) -> list[dict]:
        from sqlmodel import select
        traces = self._session.exec(
            select(ExecutionTrace)
            .where(ExecutionTrace.task_id == uuid.UUID(task_id))
            .order_by(ExecutionTrace.sequence_step)
        ).all()
        return [
            {
                "step": tr.sequence_step,
                "type": tr.action_category,
                "content": tr.payload_content,
                "timestamp": tr.timestamp.isoformat(),
            }
            for tr in traces
        ]


class CosmosRepository:
    """Repository backed by Azure Cosmos DB (NoSQL API)."""

    def __init__(self):
        from azure.cosmos import CosmosClient
        endpoint = os.environ["COSMOS_ENDPOINT"]
        key = os.environ["COSMOS_KEY"]
        db_name = os.environ.get("COSMOS_DATABASE", "bmo-agent")
        self._client = CosmosClient(endpoint, credential=key)
        self._db = self._client.get_database_client(db_name)
        self._users = self._db.get_container_client("users")
        self._tasks = self._db.get_container_client("tasks")
        self._traces = self._db.get_container_client("traces")

    def create_user(self, username: str, role_type: str = "user") -> dict:
        user_id = str(uuid.uuid4())
        item = {
            "id": user_id,
            "username": username,
            "role_type": role_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._users.create_item(body=item)
        return item

    def get_user(self, user_id: str) -> dict | None:
        try:
            return self._users.read_item(item=user_id, partition_key=user_id)
        except Exception:
            return None

    def create_task(self, user_id: str, raw_input: str) -> dict:
        task_id = str(uuid.uuid4())
        item = {
            "id": task_id,
            "user_id": user_id,
            "raw_input": raw_input,
            "execution_status": "pending",
            "final_output": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._tasks.create_item(body=item)
        return item

    def get_task(self, task_id: str) -> dict | None:
        try:
            results = list(self._tasks.query_items(
                query="SELECT * FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": task_id}],
                enable_cross_partition_query=True,
            ))
            return results[0] if results else None
        except Exception:
            return None

    def update_task(self, task_id: str, **fields) -> dict | None:
        task = self.get_task(task_id)
        if not task:
            return None
        task.update(fields)
        self._tasks.upsert_item(body=task)
        return task

    def list_tasks(self) -> list[dict]:
        results = list(self._tasks.query_items(
            query="SELECT c.id, c.raw_input, c.execution_status, c.final_output, c.created_at FROM c ORDER BY c.created_at DESC",
            enable_cross_partition_query=True,
        ))
        return results

    def create_trace(self, task_id: str, step: int, category: str, content: str) -> dict:
        trace_id = str(uuid.uuid4())
        item = {
            "id": trace_id,
            "task_id": task_id,
            "step": step,
            "type": category,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._traces.create_item(body=item)
        return item

    def get_traces(self, task_id: str) -> list[dict]:
        results = list(self._traces.query_items(
            query="SELECT c.step, c.type, c.content, c.timestamp FROM c WHERE c.task_id = @task_id ORDER BY c.step",
            parameters=[{"name": "@task_id", "value": task_id}],
            enable_cross_partition_query=True,
        ))
        return results


def get_repository(session=None) -> Repository:
    """Factory function returning the configured repository."""
    backend = os.environ.get("DATABASE_BACKEND", "sqlite").lower()
    if backend == "cosmos":
        return CosmosRepository()
    return SQLModelRepository(session)
