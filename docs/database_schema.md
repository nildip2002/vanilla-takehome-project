# Database Schema & Data Storage Reference

This document describes the complete data model of the BMO Agentic Execution Framework — every table, field, UUID strategy, relationship, and how execution traces (stack traces) are stored and queried.

---

## Overview

The system uses a **dual-backend repository pattern**:

| Environment | Backend | Driver |
|---|---|---|
| Local development | SQLite (file: `backend/app.db`) | SQLModel (SQLAlchemy) |
| Cloud (Azure) | Azure Cosmos DB (NoSQL API) | `azure-cosmos` SDK |

Both backends share the same repository interface (`Repository` protocol in `repository.py`), so the business logic in `agent.py` and `router.py` is completely decoupled from storage.

```
agent.py / router.py
        │
        ▼
  Repository (Protocol)
  ┌──────────────────────────┬──────────────────────────┐
  │  SQLModelRepository      │  CosmosRepository         │
  │  (SQLite / PostgreSQL)   │  (Azure Cosmos DB)        │
  └──────────────────────────┴──────────────────────────┘
```

---

## Entity Relationship Diagram

```
┌──────────────────────────────┐
│         SystemUser           │
│──────────────────────────────│
│  id           UUID  PK       │
│  username     TEXT           │
│  role_type    TEXT           │  "user" | "admin"
│  created_at   DATETIME       │
└──────────┬───────────────────┘
           │ 1
           │
           │ N
┌──────────▼───────────────────┐
│          AgentTask            │
│──────────────────────────────│
│  id               UUID  PK   │
│  user_id          UUID  FK ──┼──► SystemUser.id
│  raw_input        TEXT       │  original user prompt
│  execution_status TEXT       │  pending|running|completed|failed
│  final_output     TEXT?      │  synthesized LLM answer (null until done)
│  created_at       DATETIME   │
└──────────┬───────────────────┘
           │ 1
           │
           │ N
┌──────────▼───────────────────┐
│       ExecutionTrace          │
│──────────────────────────────│
│  id               UUID  PK   │
│  task_id          UUID  FK ──┼──► AgentTask.id
│  sequence_step    INT        │  0-indexed ordering
│  action_category  TEXT       │  see categories below
│  payload_content  TEXT       │  full content of this step
│  timestamp        DATETIME   │
└──────────────────────────────┘
```

---

## Table: `SystemUser`

**Purpose:** Represents an authenticated user of the system.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `UUID` | `PRIMARY KEY` | Auto-generated v4 UUID (`uuid.uuid4()`) |
| `username` | `TEXT` | `INDEX` | Display name / email identifier |
| `role_type` | `TEXT` | `DEFAULT "user"` | Either `"user"` or `"admin"` |
| `created_at` | `DATETIME` | `DEFAULT now()` | UTC timestamp of account creation |

**UUID Strategy:** All `id` values are generated server-side using Python's `uuid.uuid4()` (random, version 4). They are stored as native UUID columns in PostgreSQL or as `TEXT` in SQLite.

**Current users (cloud):**

| username | role_type | Notes |
|----------|-----------|-------|
| `nildip2002@outlook.com` | `user` | Primary user |
| `betty.lau@bmo.com` | `user` | Secondary user |
| `roxana.sarea@bmo.com` | `user` | Secondary user |

> **Note:** In this coding challenge, users are auto-created on each task submission if no `user_id` is provided. In production with Entra ID, this table would map to an Azure AD Object ID.

---

## Table: `AgentTask`

**Purpose:** Tracks every task submitted to the agent, from submission through completion.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `UUID` | `PRIMARY KEY` | Auto-generated v4 UUID |
| `user_id` | `UUID` | `FOREIGN KEY → SystemUser.id` | The user who submitted the task |
| `raw_input` | `TEXT` | `NOT NULL` | The original natural language prompt (max 2000 chars enforced at API layer) |
| `execution_status` | `TEXT` | `DEFAULT "pending"` | Lifecycle state — see status machine below |
| `final_output` | `TEXT` | `NULLABLE` | The agent's final synthesized answer. `NULL` until execution completes |
| `created_at` | `DATETIME` | `DEFAULT now()` | UTC timestamp of task submission |

### Task Status Machine

```
              ┌─────────┐
              │ pending │  ← created by POST /api/task
              └────┬────┘
                   │  SSE stream opened → agent starts
                   ▼
              ┌─────────┐
              │ running │  ← LLM loop active
              └────┬────┘
            ┌──────┴──────┐
            ▼             ▼
       ┌──────────┐  ┌────────┐
       │completed │  │ failed │  ← LLM error, max iterations exceeded
       └──────────┘  └────────┘
```

**Status transitions are performed by `repository.update_task(task_id, execution_status=...)`** inside `agent.py`.

> **Important:** A task only starts executing when a client opens the `GET /api/task/{id}/stream` SSE endpoint. The task stays `pending` if no SSE connection is established.

---

## Table: `ExecutionTrace`

**Purpose:** Records every step of the agent's reasoning chain. This is the "stack trace" of the agent's thought process — not a Python exception trace, but a structured log of reasoning + tool invocations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `UUID` | `PRIMARY KEY` | Auto-generated v4 UUID |
| `task_id` | `UUID` | `FOREIGN KEY → AgentTask.id`, `INDEX` | The parent task |
| `sequence_step` | `INT` | `NOT NULL` | 0-indexed step number within this task's execution |
| `action_category` | `TEXT` | `NOT NULL` | Type of reasoning step — see categories below |
| `payload_content` | `TEXT` | `NOT NULL` | Full text content of this step |
| `timestamp` | `DATETIME` | `DEFAULT now()` | UTC timestamp when this step was recorded |

### Action Categories

Each execution trace belongs to one of five categories:

| Category | Label in UI | Description | Example `payload_content` |
|----------|-------------|-------------|---------------------------|
| `thought` | `REASONING` | The LLM's reasoning / internal monologue | `"Received task: 'What is 12 * 8?'"` |
| `tool_call` | `TOOL INVOKE` | A function call dispatched to the MCP server | `"Calling calculator({\"expression\": \"12 * 8\"})"` |
| `tool_result` | `RESULT` | The response returned by the MCP tool | `"calculator → 96"` |
| `tool_error` | `ERROR` | A tool invocation that raised an exception | `"Tool execution error: Division by zero"` |
| `final_result` | `COMPLETE` | The agent's final synthesized response | `"12 multiplied by 8 is 96."` |

### Typical Trace Sequence

For a simple calculation task:

```
step 0  thought      "Received task: 'What is 12 * 8?'"
step 1  thought      "Discovered tools: calculator, hash_generator, ..."
step 2  tool_call    "Calling calculator({"expression": "12 * 8"})"
step 3  tool_result  "calculator → 96"
step 4  thought      "12 multiplied by 8 equals 96."
step 5  final_result "12 multiplied by 8 equals 96."
```

For a multi-tool recovery task (tool fails, agent retries):

```
step 0  thought      "Received task: 'Convert 100 USD to CAD at 1.35'"
step 1  thought      "Discovered tools: ..."
step 2  tool_call    "Calling unit_converter({...})"
step 3  tool_result  "unit_converter → Error: Cannot convert from 'USD' to 'CAD'"
step 4  tool_call    "Calling calculator({"expression": "100 * 1.35"})"
step 5  tool_result  "calculator → 135"
step 6  thought      "100 USD = 135 CAD at rate 1.35"
step 7  final_result "100 USD is equal to 135 CAD."
```

---

## Cascade Deletion

When a task is deleted via `DELETE /api/task/{id}`:

1. All `ExecutionTrace` rows where `task_id = {id}` are deleted first
2. The `AgentTask` row is then deleted
3. The `SystemUser` is **not** deleted (users persist across tasks)

```python
# SQLModelRepository.delete_task() — cascade in Python (SQLite lacks CASCADE FK)
traces = session.exec(
    select(ExecutionTrace).where(ExecutionTrace.task_id == uuid.UUID(task_id))
).all()
for trace in traces:
    session.delete(trace)
session.delete(task)
session.commit()
```

---

## Azure Cosmos DB Schema (Cloud)

In the cloud deployment, the same logical entities are stored as **JSON documents** in three Cosmos DB containers:

### Container: `users`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "nildip2002@outlook.com",
  "role_type": "user",
  "created_at": "2026-06-14T02:00:00Z"
}
```

- **Partition key:** `/id`

### Container: `tasks`

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "raw_input": "What is 12 multiplied by 8?",
  "execution_status": "completed",
  "final_output": "12 multiplied by 8 equals 96.",
  "created_at": "2026-06-14T04:55:00Z"
}
```

- **Partition key:** `/user_id`

### Container: `traces`

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "task_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "step": 2,
  "type": "tool_call",
  "content": "Calling calculator({\"expression\": \"12 * 8\"})",
  "timestamp": "2026-06-14T04:55:02Z"
}
```

- **Partition key:** `/task_id`

---

## Querying Examples

### Get all tasks for a user (SQLite)
```sql
SELECT * FROM agenttask
WHERE user_id = '550e8400-e29b-41d4-a716-446655440000'
ORDER BY created_at DESC;
```

### Get full execution trace for a task (SQLite)
```sql
SELECT sequence_step, action_category, payload_content, timestamp
FROM executiontrace
WHERE task_id = '3fa85f64-5717-4562-b3fc-2c963f66afa6'
ORDER BY sequence_step ASC;
```

### Count steps by category (SQLite)
```sql
SELECT action_category, COUNT(*) as count
FROM executiontrace
WHERE task_id = '3fa85f64-5717-4562-b3fc-2c963f66afa6'
GROUP BY action_category;
```

### Cosmos DB — get traces for a task
```python
traces = container.query_items(
    query="SELECT * FROM c WHERE c.task_id = @task_id ORDER BY c.step",
    parameters=[{"name": "@task_id", "value": task_id}],
    enable_cross_partition_query=True,
)
```

---

## Index Strategy

| Table | Column | Index Type | Purpose |
|-------|--------|------------|---------|
| `SystemUser` | `username` | B-tree | Fast lookup by email |
| `AgentTask` | `id` | Primary Key | O(1) task retrieval |
| `AgentTask` | `user_id` | (via FK) | Task-by-user queries |
| `ExecutionTrace` | `task_id` | B-tree | Fast trace retrieval per task |
| `ExecutionTrace` | `sequence_step` | (sort) | Ordered trace reconstruction |

---

## Data Retention & Lifecycle

| Event | SQLite | Cosmos DB |
|-------|--------|-----------|
| Task created | Row inserted | Document created |
| Agent starts | `execution_status → running` | `upsert_item()` |
| Each trace step | `ExecutionTrace` row inserted | Document created in `traces` |
| Task completes | `execution_status → completed`, `final_output` set | `upsert_item()` |
| Task deleted | Cascades to traces → task removed | Traces queried & deleted, task deleted |

> **Cosmos DB Free Tier Limits:** 1,000 RU/s, 25 GB storage. Each trace write costs ~1–2 RU. A 10-step task = ~20 RU total.

---

## Related Files

| File | Purpose |
|------|---------|
| `backend/models.py` | SQLModel table definitions (source of truth for SQLite schema) |
| `backend/repository.py` | `SQLModelRepository` + `CosmosRepository` implementations |
| `backend/database.py` | SQLite engine setup + `get_session` dependency |
| `backend/router.py` | API endpoints that call the repository |
| `infra/main.tf` | Terraform: provisions Cosmos DB account, database, and containers |
