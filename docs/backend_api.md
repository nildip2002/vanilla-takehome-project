# Backend API Reference

This document provides a complete reference for the FastAPI backend, including all endpoints, request/response schemas, and error codes.

---

## Base URL

- **Local development**: `http://localhost:8000`
- **Docker**: `http://localhost:8000` (or via nginx proxy at `http://localhost:3000/api/`)

---

## Endpoints

### `GET /`

Root health check confirming the API is operational.

**Response** `200 OK`
```json
{
  "message": "Agentic Execution Framework API is running",
  "version": "1.0.0"
}
```

---

### `GET /api/health`

Service readiness probe for Docker health checks and load balancers.

**Response** `200 OK`
```json
{
  "status": "healthy"
}
```

---

### `GET /api/ollama/status`

Check Ollama LLM connectivity and model availability.

**Response** `200 OK`
```json
{
  "status": "connected",
  "host": "http://localhost:11434",
  "configured_model": "qwen2.5:0.5b",
  "model_available": true,
  "available_models": ["qwen2.5:0.5b", "qwen3:8b"]
}
```

---

### `POST /api/task`

Submit a new task for the agent to process.

**Request Body**
```json
{
  "prompt": "What is 52 * 41?",
  "user_id": "optional-uuid-string"
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `prompt` | string | ✅ | 1–2000 characters |
| `user_id` | string | ❌ | Valid UUID; auto-created if absent |

**Response** `200 OK`
```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending"
}
```

**Error Responses**

| Status | Cause |
|---|---|
| `400` | Invalid `user_id` format |
| `422` | Missing or empty `prompt` |

---

### `GET /api/task/{task_id}/stream`

Stream execution traces via Server-Sent Events (SSE). Connect to this endpoint after creating a task to receive real-time updates.

**SSE Event Types**

| Event | Description | Data Format |
|---|---|---|
| `trace_update` | Intermediate step (thought, tool call, result) | `{"step": 0, "type": "thought", "content": "..."}` |
| `final_result` | Agent has completed | `{"step": 5, "type": "final_result", "content": "..."}` |

**Trace Types** (`type` field):

| Type | Description | Color |
|---|---|---|
| `thought` | LLM reasoning step | 🔵 Blue |
| `tool_call` | Tool invocation | 🟡 Amber |
| `tool_result` | Tool response | 🟢 Green |
| `tool_error` | Tool failure | 🔴 Red |
| `final_result` | Synthesized answer | 🟣 Violet |

**Example SSE Stream**
```
event: trace_update
data: {"step": 0, "type": "thought", "content": "Received task: \"What is 52 * 41?\""}

event: trace_update
data: {"step": 1, "type": "thought", "content": "Discovered tools: text_processor, calculator, weather_mock"}

event: trace_update
data: {"step": 2, "type": "tool_call", "content": "Calling calculator({\"expression\": \"52 * 41\"})"}

event: trace_update
data: {"step": 3, "type": "tool_result", "content": "calculator → 2132"}

event: final_result
data: {"step": 5, "type": "final_result", "content": "The result of 52 multiplied by 41 is 2132."}
```

**Error Responses**

| Status | Cause |
|---|---|
| `400` | Invalid `task_id` format |
| `404` | Task not found |

---

### `GET /api/tasks`

List all historical tasks ordered by creation time (most recent first).

**Response** `200 OK`
```json
[
  {
    "id": "a1b2c3d4-...",
    "raw_input": "Calculate 52 * 41",
    "execution_status": "completed",
    "final_output": "The result is 2132.",
    "created_at": "2026-06-13T22:29:00.123456"
  }
]
```

---

### `GET /api/task/{task_id}`

Get a single task with its full execution trace.

**Response** `200 OK`
```json
{
  "id": "a1b2c3d4-...",
  "raw_input": "Calculate 52 * 41",
  "execution_status": "completed",
  "final_output": "The result is 2132.",
  "created_at": "2026-06-13T22:29:00.123456",
  "traces": [
    {
      "step": 0,
      "type": "thought",
      "content": "Received task: \"Calculate 52 * 41\"",
      "timestamp": "2026-06-13T22:29:00.456789"
    },
    {
      "step": 1,
      "type": "tool_call",
      "content": "Calling calculator({\"expression\": \"52 * 41\"})",
      "timestamp": "2026-06-13T22:29:01.234567"
    }
  ]
}
```

**Error Responses**

| Status | Cause |
|---|---|
| `400` | Invalid `task_id` format |
| `404` | Task not found |

---

## Data Models

### AgentTask States

```mermaid
stateDiagram-v2
    [*] --> pending: Task created
    pending --> running: SSE stream connected
    running --> completed: LLM produces final answer
    running --> failed: Error or max iterations
```

### Execution Status Values

| Status | Description |
|---|---|
| `pending` | Task created, waiting for SSE connection |
| `running` | Agent is actively reasoning |
| `completed` | Final answer produced successfully |
| `failed` | Error occurred or max iterations exceeded |

---

## CORS Configuration

The API allows all origins in development (`allow_origins=["*"]`). For production, restrict to your frontend domain.

## OpenAPI Documentation

FastAPI auto-generates interactive API docs:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## Authentication — Current Implementation & Production Roadmap

### Current Implementation (Challenge Scope)

The current auth system uses a lightweight **email + access token** approach appropriate for a coding challenge:

| Component | Implementation |
|-----------|---------------|
| Token generation | `secrets.token_urlsafe(32)` — cryptographically secure random tokens |
| Token storage | **Local dev**: In-memory dict; **Cloud**: Azure Key Vault secrets |
| Token verification | `secrets.compare_digest()` — timing-safe comparison |
| Session | Token stored in `localStorage`, sent as `Bearer email:token` header |
| User allowlist | Hardcoded `ALLOWED_EMAILS` list in `auth.py` |
| Initialization | `POST /api/auth/init` — one-time setup generating tokens for all users |

This provides a meaningful security layer for a demo system while keeping the implementation reviewable.

### Production Recommendation — Azure AD / Entra ID with Security Groups

In a fully productionized system, this custom token auth would be replaced with **Microsoft Entra ID (formerly Azure Active Directory)** integration. This is the standard enterprise pattern at institutions like BMO:

```
Current (Challenge):         Production (Enterprise):
─────────────────────        ──────────────────────────────────────────────
Email + static token    →    OAuth 2.0 / OIDC via Entra ID
Hardcoded allowlist     →    Azure AD Security Groups (e.g. "BMO-Agent-Users")
Manual token init       →    SSO — no credentials to manage
localStorage token      →    Short-lived JWT (15 min) + refresh token rotation
No MFA                  →    Conditional Access Policies + MFA enforced by AAD
Manual user management  →    Group membership managed in Azure AD by IT admins
```

**How it would work with Entra ID:**

1. **App Registration** — Register the app in Azure AD, define scopes (`agent.read`, `agent.write`).
2. **Security Groups** — Create `BMO-Agent-Users` group in Azure AD. IT admins add/remove members.
3. **MSAL Authentication** — Frontend uses `@azure/msal-react` to handle OAuth 2.0 login flows (redirect or popup). Zero custom auth code.
4. **Backend Validation** — FastAPI validates the incoming JWT using `azure-identity` or `python-jose`, checking the `groups` claim to enforce role-based access.
5. **Conditional Access** — Azure AD policies enforce MFA, device compliance, and IP restrictions — no backend code changes needed.

```python
# Production pattern (not implemented — challenge scope):
from fastapi_azure_auth import SingleTenantAzureAuthorizationCodeBearer

azure_scheme = SingleTenantAzureAuthorizationCodeBearer(
    app_client_id=os.environ["AZURE_CLIENT_ID"],
    tenant_id=os.environ["AZURE_TENANT_ID"],
    scopes={"api://bmo-agent/agent.read": "Read access"},
)

@router.post("/task")
def create_task(req: TaskRequest, token=Security(azure_scheme)):
    # token.groups contains the user's AD group memberships
    if "BMO-Agent-Users" not in token.groups:
        raise HTTPException(status_code=403, detail="Not authorized")
    ...
```

> **Note**: The current implementation is intentionally scoped for a coding challenge. The architecture is designed so that `auth.py` is the only file that would need to change to adopt Entra ID — the rest of the backend is auth-provider agnostic.
