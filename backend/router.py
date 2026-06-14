"""
API Router — Exposes RESTful + SSE endpoints for the Agent Controller.

Endpoints:
  POST   /api/task              — Submit a new task for agent processing
  GET    /api/task/{id}/stream   — Stream execution traces via SSE
  GET    /api/tasks             — List all historical tasks
  GET    /api/task/{id}         — Get a single task with its traces
  DELETE /api/task/{id}         — Delete a task and its traces
  GET    /api/health            — Health check
  GET    /api/llm/status        — LLM provider health check
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session
from sse_starlette.sse import EventSourceResponse

from agent import check_llm_health, execute_task
from auth import ALLOWED_EMAILS, auth_required, init_default_tokens, verify_token
from database import get_session
from repository import SQLModelRepository, get_repository

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    """Schema for login."""
    email: str = Field(..., description="User email address")
    token: str = Field(..., description="Access token")


class LoginResponse(BaseModel):
    """Schema returned on successful login."""
    authenticated: bool
    email: str
    session_token: str


class TaskRequest(BaseModel):
    """Schema for submitting a new task."""
    prompt: str = Field(..., min_length=1, max_length=2000, description="Natural language task to execute")
    user_id: Optional[str] = Field(default=None, description="UUID of the submitting user (auto-created if absent)")


class TaskResponse(BaseModel):
    """Schema returned after task creation."""
    task_id: str
    status: str


def _get_repo(session: Session = Depends(get_session)):
    """Dependency that provides the repository for the current request."""
    backend = os.environ.get("DATABASE_BACKEND", "sqlite").lower()
    if backend == "cosmos":
        from repository import CosmosRepository
        return CosmosRepository()
    return SQLModelRepository(session)


@router.get("/health")
def health_check():
    """Simple health probe for Docker / load balancer readiness checks."""
    return {"status": "healthy"}


@router.get("/llm/status")
async def llm_status():
    """Check LLM provider connectivity and model availability."""
    return await check_llm_health()


@router.post("/task", response_model=TaskResponse)
def create_task(req: TaskRequest, repo=Depends(_get_repo)):
    """Submit a new task for the agent to process."""
    user = None
    if req.user_id:
        import uuid
        try:
            uuid.UUID(req.user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user_id format")
        user = repo.get_user(req.user_id)

    if not user:
        user = repo.create_user(username="default", role_type="user")

    task = repo.create_task(user_id=user["id"], raw_input=req.prompt)
    logger.info("Created task %s for user %s", task["id"], user["id"])
    return TaskResponse(task_id=task["id"], status=task["execution_status"])


@router.get("/task/{task_id}/stream")
async def stream_task(task_id: str, request: Request, repo=Depends(_get_repo)):
    """Stream execution traces for a task via Server-Sent Events (SSE)."""
    import uuid
    try:
        uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    task = repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return EventSourceResponse(
        execute_task(task["id"], task["raw_input"], repo),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tasks")
def list_tasks(repo=Depends(_get_repo)):
    """Return all tasks ordered by creation time (most recent first)."""
    return repo.list_tasks()


@router.get("/task/{task_id}")
def get_task_detail(task_id: str, repo=Depends(_get_repo)):
    """Return a single task with its full execution trace."""
    import uuid
    try:
        uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    task = repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    traces = repo.get_traces(task_id)
    task["traces"] = traces
    return task


@router.delete("/task/{task_id}")
def delete_task(task_id: str, repo=Depends(_get_repo)):
    """Delete a task and all its associated execution traces."""
    import uuid
    try:
        uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    if not repo.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")

    logger.info("Deleted task %s", task_id)
    return {"deleted": True, "task_id": task_id}


# ─── Authentication Endpoints ─────────────────────────────────────────────────

@router.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """Authenticate with email + access token."""
    email = req.email.lower().strip()
    if email not in ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="Email not authorized")

    if not verify_token(email, req.token):
        raise HTTPException(status_code=401, detail="Invalid token")

    session_token = f"{email}:{req.token}"
    return LoginResponse(authenticated=True, email=email, session_token=session_token)


@router.get("/auth/me")
def auth_me(email: str = Depends(auth_required)):
    """Return the authenticated user's identity."""
    return {"email": email, "authenticated": True}


@router.post("/auth/init")
def auth_init():
    """Initialize tokens for all allowed users (first-time setup only)."""
    tokens = init_default_tokens()
    if not tokens:
        return {"message": "All tokens already initialized", "users": ALLOWED_EMAILS}
    return {
        "message": "Tokens generated for new users",
        "tokens": tokens,
        "note": "Save these tokens securely — they cannot be retrieved again from Key Vault",
    }
