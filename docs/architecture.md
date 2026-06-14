# System Architecture

This document provides a detailed architectural overview of the Agentic Execution Framework, including data flow diagrams, component responsibilities, and design rationale.

---

## High-Level Architecture

```mermaid
graph TB
    subgraph "Frontend (React + Vite)"
        UI[React SPA]
        ES[EventSource SSE Client]
    end

    subgraph "Backend (FastAPI)"
        API[REST API Router]
        AGENT[ReAct Agent Controller]
        DB_LAYER[SQLModel ORM]
    end

    subgraph "Tool Layer (MCP)"
        MCP_CLIENT[MCP Client]
        MCP_SERVER[FastMCP Server]
        T1[TextProcessorTool]
        T2[CalculatorTool]
        T3[WeatherMockTool]
    end

    subgraph "Inference Engine"
        OLLAMA[Ollama Server]
        MODEL[qwen2.5:0.5b]
    end

    subgraph "Persistence"
        SQLITE[(SQLite Database)]
    end

    UI -->|POST /api/task| API
    UI -->|GET /api/tasks| API
    ES -->|GET /api/task/id/stream| API
    API --> AGENT
    AGENT --> MCP_CLIENT
    AGENT -->|ollama.chat| OLLAMA
    OLLAMA --> MODEL
    MCP_CLIENT -->|stdio| MCP_SERVER
    MCP_SERVER --> T1
    MCP_SERVER --> T2
    MCP_SERVER --> T3
    AGENT --> DB_LAYER
    DB_LAYER --> SQLITE
    API --> DB_LAYER
```

---

## ReAct Loop Sequence

The agent uses a Reasoning + Acting (ReAct) pattern to solve tasks. Here is the sequence for a typical task:

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API as FastAPI
    participant Agent as ReAct Agent
    participant LLM as Ollama LLM
    participant MCP as MCP Server
    participant DB as SQLite

    User->>Frontend: Enter task + click "Run Task"
    Frontend->>API: POST /api/task {prompt}
    API->>DB: Create AgentTask (status: pending)
    API-->>Frontend: {task_id, status: pending}

    Frontend->>API: GET /api/task/{id}/stream (SSE)
    API->>Agent: execute_task(task, session)

    Agent->>DB: Update status → running
    Agent-->>Frontend: SSE: thought "Received task..."

    Agent->>MCP: list_tools()
    MCP-->>Agent: [text_processor, calculator, weather_mock]
    Agent-->>Frontend: SSE: thought "Discovered tools..."

    loop ReAct Loop (max 10 iterations)
        Agent->>LLM: chat(messages, tools)
        LLM-->>Agent: response (thought + tool_calls?)

        alt Has tool_calls
            Agent-->>Frontend: SSE: tool_call "Calling calculator(...)"
            Agent->>MCP: call_tool(name, args)
            MCP-->>Agent: tool result
            Agent-->>Frontend: SSE: tool_result "calculator → 2132"
            Agent->>Agent: Append result to messages
        else No tool_calls (final answer)
            Agent->>DB: Update task (status: completed, output)
            Agent-->>Frontend: SSE: final_result "The answer is..."
        end
    end
```

---

## Database Entity Relationship

```mermaid
erDiagram
    SystemUser ||--o{ AgentTask : "submits"
    AgentTask ||--o{ ExecutionTrace : "produces"

    SystemUser {
        uuid id PK
        string username
        string role_type
        datetime created_at
    }

    AgentTask {
        uuid id PK
        uuid user_id FK
        string raw_input
        string execution_status
        string final_output
        datetime created_at
    }

    ExecutionTrace {
        uuid id PK
        uuid task_id FK
        int sequence_step
        string action_category
        string payload_content
        datetime timestamp
    }
```

### Entity Descriptions

| Entity | Purpose |
|---|---|
| **SystemUser** | Represents an authenticated user. Supports RBAC with `role_type` (admin/user). Auto-created when tasks are submitted without a user_id. |
| **AgentTask** | A single user-submitted task. Tracks the raw prompt, current status (`pending` → `running` → `completed`/`failed`), and the final output. |
| **ExecutionTrace** | One step in the agent's reasoning chain. Categories: `thought`, `tool_call`, `tool_result`, `tool_error`, `final_result`. Ordered by `sequence_step`. |

---

## Component Responsibilities

### Frontend (React SPA)
- **Task submission**: Sends `POST /api/task` and immediately connects to the SSE stream
- **Real-time rendering**: Parses SSE events and renders trace steps with color-coded badges
- **History browsing**: Fetches `GET /api/tasks` and `GET /api/task/{id}` for drill-down inspection
- **Error handling**: Displays error banners when backend is unreachable

### Backend (FastAPI)
- **API layer** (`router.py`): RESTful endpoints with Pydantic validation, UUID parsing, HTTP error codes
- **Agent controller** (`agent.py`): ReAct loop with bounded iterations, retry/backoff, SSE event emission
- **Persistence** (`database.py`, `models.py`): SQLModel ORM with engine override for testing
- **Startup** (`main.py`): Lifespan-managed table creation, CORS, structured logging

### MCP Tool Server (FastMCP)
- **Isolated subprocess**: Runs as a child process via stdio transport — completely decoupled
- **Tool registration**: Each tool is a decorated Python function with typed parameters
- **Schema generation**: FastMCP auto-generates JSON Schema for tool parameters

### Ollama (Local LLM)
- **Inference engine**: Runs `qwen2.5:0.5b` (or any compatible model) locally
- **Function calling**: Supports the Ollama tool-calling protocol for structured tool selection
- **Zero-cost**: No API keys, no external network calls, full data privacy

---

## Design Decisions

| Decision | Why | Tradeoff |
|---|---|---|
| **MCP over direct calls** | Genuine tool isolation; add new tools without touching agent code | Adds subprocess overhead (~50ms per call) |
| **SSE over WebSockets** | Unidirectional, lightweight, works through corporate proxies | No bidirectional communication |
| **SQLite over PostgreSQL** | Zero setup for local dev; SQLModel makes migration trivial | No concurrent write scaling |
| **Bounded ReAct loop** | Prevents runaway LLM loops consuming resources | May truncate genuinely complex tasks |
| **Retry with backoff** | Handles transient Ollama/CUDA/network failures | Adds latency on failures (up to ~7s for 3 retries) |
