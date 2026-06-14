# Implementation Plan: Azure Migration, Microsoft Foundry, Additional Tools & Frontend Redesign

## Table of Contents

1. [Overview](#overview)
2. [Current State](#current-state)
3. [Azure Architecture](#azure-architecture)
4. [Microsoft Foundry Integration](#microsoft-foundry-integration)
5. [Additional MCP Tools](#additional-mcp-tools)
6. [Code Changes](#code-changes)
7. [Infrastructure as Code (Terraform)](#infrastructure-as-code-terraform)
8. [CI/CD Pipeline](#cicd-pipeline)
9. [Frontend Redesign](#frontend-redesign)
10. [Documentation Plan](#documentation-plan)
11. [Implementation Sequence](#implementation-sequence)
12. [Verification & Testing](#verification--testing)

---

## Overview

### Goals

- Deploy the entire stack to Azure using **free-tier resources** ($200 credit)
- Integrate with **Microsoft Foundry** (formerly Azure AI Foundry) for managed LLM + agent service
- Add **5 more MCP tools** (total 8) for robust multi-step reasoning
- Keep **local Docker Compose** working identically (dual-mode: local Ollama + cloud Foundry)
- **Redesign the frontend** for a modern, snappy experience
- Produce **comprehensive documentation** with architecture diagrams (Python `diagrams` library)
- Write **Terraform IaC** for full infrastructure provisioning
- Publish to `https://github.com/nildip2002/vanilla-takehome-project.git`
- Fulfill **all challenge requirements** including every bonus item

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM (cloud) | Microsoft Foundry + GPT-4.1-nano | Cheapest model with full tool calling support (~10x cheaper than GPT-4o-mini) |
| LLM (local) | Ollama (qwen2.5:0.5b) | Fast, no cost, existing code works |
| Database (cloud) | Azure Cosmos DB Free Tier | 1000 RU/s free forever, 25GB |
| Database (local) | SQLite | Zero config, existing code |
| Frontend hosting | Azure Static Web Apps (Free) | Zero cost, global CDN, auto SSL |
| Backend hosting | Azure Container Apps (Consumption) | Free allotment, scale-to-zero |
| Telemetry | Application Insights (5GB free) | Auto-instrumentation, Azure Portal dashboards |
| IaC | Terraform (azurerm provider) | User familiar with AWS/Terraform patterns |
| CI/CD | GitHub Actions | Already partially set up |

---

## Current State

### Existing Tools (3)
1. **TextProcessorTool** — uppercase, lowercase, wordcount, reverse, titlecase
2. **CalculatorTool** — safe AST-based arithmetic evaluation
3. **WeatherMockTool** — deterministic hash-based mock weather

### Current Architecture
```
Browser → nginx (port 3000) → React SPA
                                    ↓ API calls
                              FastAPI (port 8000)
                                    ↓ subprocess stdio
                              MCP Server (tools)
                                    ↓ HTTP
                              Ollama (port 11434)
                                    ↓ SQL
                              SQLite (file-based)
```

### Challenge Compliance (Current)

| Requirement | Status |
|------------|--------|
| Frontend: text input, submit, view result | Done |
| Frontend: history, inspect execution steps | Done |
| Backend: accepts task, agent selects tool | Done |
| Backend: returns final output + execution steps | Done |
| Agent: parse request, choose tool, execute, trace | Done |
| Tools: 3 minimum (text, calc, weather) | Done |
| Persistence: SQLite | Done |
| **Bonus: Tests** | Done (pytest suite) |
| **Bonus: Dockerfile/containerization** | Done (docker-compose) |
| **Bonus: Retry/error-handling** | Done (exponential backoff) |
| **Bonus: Multi-step reasoning** | Done (ReAct loop, multiple tools in one task) |
| **Bonus: Real-time streaming** | Done (SSE) |
| **Bonus: Basic RBAC** | Done (SystemUser with role_type) |

---

## Azure Architecture

### Resource Map

| Service | SKU | Purpose | Est. Cost/mo |
|---------|-----|---------|------|
| Azure Static Web Apps | Free | Frontend React SPA | $0 |
| Azure Container Apps | Consumption | Backend API + MCP server | $0 |
| Azure Cosmos DB | Free Tier | NoSQL database (tasks, traces, users) | $0 |
| Microsoft Foundry Resource | Free (pay-per-token on model calls) | LLM + Agent service + Content Safety | ~$2-5 |
| Azure Container Registry | Basic | Docker images | ~$5 |
| Application Insights + Log Analytics | Free 5GB | Monitoring & telemetry | $0 |
| **Total** | | | **~$7-10/mo** |

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Azure Cloud                                  │
│                                                                           │
│  ┌──────────────────┐         ┌────────────────────────────────────┐    │
│  │ Static Web Apps   │         │  Container Apps Environment         │    │
│  │ (React SPA)       │────────▶│  ┌──────────────────────────────┐  │    │
│  │ CDN + Auto SSL    │  API    │  │ Backend Container             │  │    │
│  └──────────────────┘         │  │ - FastAPI (port 8000)         │  │    │
│                                │  │ - MCP Server (subprocess)     │  │    │
│                                │  │ - Foundry SDK client          │  │    │
│                                │  │ - Cosmos DB SDK               │  │    │
│                                │  │ - App Insights SDK            │  │    │
│                                │  └─────────┬────────┬────────────┘  │    │
│                                └────────────┼────────┼────────────────┘    │
│                                             │        │                     │
│  ┌──────────────────────────────────────────┼────────┼───────────────┐    │
│  │            Microsoft Foundry              │        │                │    │
│  │  ┌─────────────────────────────────┐     │        │                │    │
│  │  │ Foundry Resource + Project       │◀────┘        │                │    │
│  │  │ - GPT-4o-mini deployment         │              │                │    │
│  │  │ - Content Safety filters         │              │                │    │
│  │  │ - Prompt evaluation metrics      │              │                │    │
│  │  │ - Agent tracing & observability  │              │                │    │
│  │  └─────────────────────────────────┘              │                │    │
│  └────────────────────────────────────────────────────┘                │    │
│                                                       │                     │
│                                          ┌────────────▼───────────────┐    │
│                                          │  Azure Cosmos DB            │    │
│                                          │  Free Tier (1000 RU/s)     │    │
│                                          │  - users container          │    │
│                                          │  - tasks container          │    │
│                                          │  - traces container         │    │
│                                          └────────────────────────────┘    │
│                                                                           │
│  ┌───────────────────┐    ┌──────────────────────────┐                   │
│  │ Container Registry │    │ Application Insights      │                   │
│  │ (Docker images)    │    │ - Request metrics         │                   │
│  └───────────────────┘    │ - Dependency tracking     │                   │
│                            │ - Custom events (traces)  │                   │
│                            │ - Live Metrics dashboard  │                   │
│                            └──────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### CI/CD Pipeline Architecture

```
┌──────────────┐     ┌─────────────────────────────────────────────────────┐
│  Developer    │     │          GitHub Actions (on push to main)            │
│  git push     │────▶│                                                     │
└──────────────┘     │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
                      │  │ Backend  │  │ Frontend │  │ Docker Build     │  │
                      │  │ Tests    │  │ Build    │  │ Validation       │  │
                      │  │ (pytest) │  │ (vite)   │  │                  │  │
                      │  └────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
                      │       │             │                  │             │
                      │       ▼             ▼                  ▼             │
                      │  ┌──────────────────────────────────────────────┐   │
                      │  │              Deploy Job                       │   │
                      │  │  ┌─────────────────────────────────────┐    │   │
                      │  │  │ 1. az login (service principal)      │    │   │
                      │  │  │ 2. docker build → push to ACR        │    │   │
                      │  │  │ 3. az containerapp update (backend)  │    │   │
                      │  │  │ 4. Deploy frontend → Static Web Apps │    │   │
                      │  │  └─────────────────────────────────────┘    │   │
                      │  └──────────────────────────────────────────────┘   │
                      └─────────────────────────────────────────────────────┘
```

### Local Development (unchanged)
```
docker compose up
  → frontend:3000 (nginx + React SPA)
  → backend:8000  (FastAPI + Ollama + SQLite + MCP subprocess)
  → Ollama on host machine:11434
```

---

## Microsoft Foundry Integration

### What is Microsoft Foundry?

Microsoft Foundry (previously Azure AI Foundry / Azure AI Studio) is Azure's unified AI platform — comparable to **AWS Bedrock**. It provides:

- **1900+ models** from Microsoft, OpenAI, Anthropic, Meta, Mistral, etc.
- **Built-in content safety** filters (free, auto-applied)
- **Agent Service** with tool calling, memory, and multi-agent orchestration
- **Evaluation & tracing** — monitor prompt quality, latency, token usage
- **Unified SDK** (`azure-ai-projects` 2.x) with single project endpoint
- **Instant models** — call any model by name without explicit deployment

### How We'll Use Foundry

| Capability | Our Usage |
|-----------|-----------|
| **GPT-4o-mini deployment** | Primary LLM for cloud ReAct loop (tool calling) |
| **Content Safety** | Auto-filters harmful inputs/outputs — free, no code needed |
| **Tracing & Evaluation** | Monitor agent reasoning quality, track token costs |
| **Project Endpoint** | Single URL for all model calls: `https://<resource>.ai.azure.com/api/projects/<project>` |

### SDK Integration Pattern

```python
# Cloud mode: Microsoft Foundry SDK
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

project = AIProjectClient(
    endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)
openai_client = project.get_openai_client()

# Use standard OpenAI chat completions with tool calling
response = openai_client.chat.completions.create(
    model="gpt-4.1-nano",
    messages=messages,
    tools=tools,  # Same tool schema format as Ollama
)
```

### Foundry vs Direct Azure OpenAI

| Feature | Direct Azure OpenAI | Microsoft Foundry |
|---------|--------------------|--------------------|
| Model access | OpenAI models only | 1900+ models (OpenAI, Meta, Mistral...) |
| Content Safety | Manual setup | Built-in, auto-applied |
| Eval/Tracing | DIY with App Insights | Built-in evaluation dashboard |
| Cost | Same per-token | Same per-token + free platform |
| SDK | `openai` with Azure config | `azure-ai-projects` (unified) |
| Agent Service | Build your own | Managed agents available (optional) |

### Why Foundry is Better for Us

1. **Content Safety for free** — the challenge is from BMO (bank), showing responsible AI matters
2. **Built-in eval dashboard** — demonstrates production monitoring without extra code
3. **Single endpoint** — cleaner than managing separate OpenAI resource + key
4. **Future-proof** — can swap to GPT-5, Claude, Llama without code changes
5. **Managed Identity** — `DefaultAzureCredential()` instead of API keys in env vars

---

## Additional MCP Tools

Expand from 3 to **8 tools** for a more robust, versatile agent.

### New Tools (5)

| # | Tool | Description | Use Case |
|---|------|-------------|----------|
| 4 | **DateTimeTool** | Current date/time, timezone conversion, date arithmetic | "What day is 100 days from now?" |
| 5 | **UnitConverterTool** | Temperature, length, weight, volume conversions | "Convert 72°F to Celsius" |
| 6 | **JsonFormatterTool** | Validate, pretty-print, minify, extract keys from JSON | "Pretty-print this JSON: {...}" |
| 7 | **HashGeneratorTool** | MD5, SHA-256, SHA-512 hash generation | "What's the SHA-256 of 'hello'?" |
| 8 | **RandomGeneratorTool** | Random numbers, UUIDs, passwords, pick from list | "Generate a secure 16-char password" |

### Implementation

```python
# mcp_server/mcp_server.py — additions

@mcp.tool()
def datetime_tool(operation: str, value: str = "", timezone: str = "UTC", days: int = 0) -> str:
    """
    Date/time operations.
    Operations: now, convert_timezone, days_between, add_days, format
    - now: returns current date/time in specified timezone
    - add_days: add/subtract days from a date (value=YYYY-MM-DD, days=N)
    - days_between: days between two dates (value=YYYY-MM-DD,YYYY-MM-DD)
    - format: reformat a date (value=date_string, timezone=target_format)
    """

@mcp.tool()
def unit_converter(value: float, from_unit: str, to_unit: str) -> str:
    """
    Convert between common units.
    Categories: temperature (C/F/K), length (m/km/mi/ft/in/cm),
    weight (kg/lb/oz/g), volume (l/ml/gal/cup/tbsp)
    Example: unit_converter(100, "F", "C") → "37.78"
    """

@mcp.tool()
def json_formatter(json_string: str, operation: str = "prettify") -> str:
    """
    JSON manipulation.
    Operations: validate, prettify, minify, extract_keys, count_items, get_value
    - validate: returns "valid" or error message
    - prettify: returns indented JSON
    - minify: returns compact JSON
    - extract_keys: returns top-level keys
    - count_items: counts top-level items (object keys or array elements)
    """

@mcp.tool()
def hash_generator(text: str, algorithm: str = "sha256") -> str:
    """
    Generate cryptographic hash of input text.
    Algorithms: md5, sha1, sha256, sha512
    Returns: hex digest string
    Example: hash_generator("hello", "sha256") → "2cf24dba..."
    """

@mcp.tool()
def random_generator(operation: str, min_val: int = 0, max_val: int = 100,
                     length: int = 16, items: str = "", seed: int = -1) -> str:
    """
    Generate random values.
    Operations: number, uuid, password, choice
    - number: random int between min_val and max_val
    - uuid: generate a UUID v4
    - password: random string of given length (letters + digits + symbols)
    - choice: pick random item from comma-separated items string
    Optional: seed for reproducible results in testing (default -1 = truly random)
    """
```

### Multi-Step Reasoning Examples (exercises tool chaining)

| Prompt | Expected Tool Chain |
|--------|-------------------|
| "What's the SHA-256 hash of today's date?" | `datetime_tool(now)` → `hash_generator(result, sha256)` |
| "Convert 98.6°F to Celsius, then tell me if Tokyo is hotter" | `unit_converter(98.6, F, C)` → `weather_mock(Tokyo)` → reasoning |
| "Generate a random number 1-1000, multiply by 3, convert result to uppercase" | `random_generator(number, 1, 1000)` → `calculator(N * 3)` → `text_processor(result, uppercase)` |
| "Pretty-print this JSON and count its keys: {\"a\":1,\"b\":2}" | `json_formatter(json, prettify)` → `json_formatter(json, extract_keys)` |
| "What day is 90 days from today? Is it more or less than 3 months?" | `datetime_tool(now)` → `datetime_tool(add_days, today, 90)` → reasoning |

### Tests for New Tools

Each new tool gets a test class in `backend/tests/test_mcp_tools.py`:

```python
class TestDateTimeTool:
    def test_now_returns_valid_datetime(self): ...
    def test_add_days_positive(self): ...
    def test_add_days_negative(self): ...
    def test_days_between(self): ...
    def test_invalid_operation(self): ...

class TestUnitConverter:
    def test_fahrenheit_to_celsius(self): ...
    def test_celsius_to_kelvin(self): ...
    def test_miles_to_km(self): ...
    def test_kg_to_lb(self): ...
    def test_invalid_unit(self): ...

class TestJsonFormatter:
    def test_validate_valid(self): ...
    def test_validate_invalid(self): ...
    def test_prettify(self): ...
    def test_minify(self): ...
    def test_extract_keys(self): ...

class TestHashGenerator:
    def test_sha256_deterministic(self): ...
    def test_md5(self): ...
    def test_invalid_algorithm(self): ...

class TestRandomGenerator:
    def test_number_in_range(self): ...
    def test_uuid_format(self): ...
    def test_password_length(self): ...
    def test_choice_from_list(self): ...
    def test_seed_reproducible(self): ...
```

---

## Code Changes

### 6.1 New File: `backend/llm_client.py` — LLM Abstraction

```python
"""
LLM Client Abstraction — dual-provider support.

LLM_PROVIDER env var:
  "ollama"        → Local Ollama (default for Docker dev)
  "foundry"       → Microsoft Foundry (Azure cloud deployment)

Both providers expose the same interface for the ReAct loop in agent.py.
"""
import os
from typing import Protocol
from dataclasses import dataclass

@dataclass
class ToolCall:
    name: str
    arguments: dict

@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]

class LLMClient(Protocol):
    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse: ...

class OllamaLLMClient:
    """Wraps ollama.AsyncClient — used in local Docker dev."""
    def __init__(self):
        import ollama
        self.client = ollama.AsyncClient(host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
        self.model = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        response = await self.client.chat(model=self.model, messages=messages, tools=tools)
        message = response.message
        content = getattr(message, "content", "") or ""
        tool_calls = []
        if raw_calls := getattr(message, "tool_calls", None):
            for tc in raw_calls:
                tool_calls.append(ToolCall(name=tc.function.name, arguments=tc.function.arguments))
        return LLMResponse(content=content, tool_calls=tool_calls)

class FoundryLLMClient:
    """
    Wraps Microsoft Foundry SDK — used in Azure cloud deployment.
    Uses azure-ai-projects unified client with OpenAI compatibility.
    Content safety filters are applied automatically by Foundry.
    """
    def __init__(self):
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        self.project = AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=DefaultAzureCredential(),
        )
        self.client = self.project.get_openai_client()
        self.model = os.environ.get("FOUNDRY_MODEL", "gpt-4.1-nano")

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        # Foundry OpenAI client uses standard openai format
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0].message
        content = choice.content or ""
        tool_calls = []
        if choice.tool_calls:
            for tc in choice.tool_calls:
                import json
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments)
                ))
        return LLMResponse(content=content, tool_calls=tool_calls)

def get_llm_client() -> LLMClient:
    """Factory: returns client based on LLM_PROVIDER env var."""
    provider = os.environ.get("LLM_PROVIDER", "ollama")
    if provider == "foundry":
        return FoundryLLMClient()
    return OllamaLLMClient()
```

### 6.2 Modified: `backend/agent.py`

Replace direct `ollama` usage with `get_llm_client()`. The ReAct loop logic stays identical — only the chat call is abstracted.

Key change:
```python
# Before:
client = ollama.AsyncClient(host=OLLAMA_HOST)
response = await client.chat(model=OLLAMA_MODEL, messages=messages, tools=ollama_tools)

# After:
from llm_client import get_llm_client
client = get_llm_client()
response = await client.chat(messages=messages, tools=ollama_tools)
```

### 6.3 New File: `backend/repository.py` — Database Abstraction

```python
"""
Repository pattern — abstracts SQLite (local) vs Cosmos DB (cloud).
Selected via DATABASE_BACKEND environment variable ("sqlite" | "cosmos").
"""
from typing import Protocol

class TaskRepository(Protocol):
    def create_user(self, username: str, role: str) -> dict: ...
    def get_user(self, user_id: str) -> dict | None: ...
    def create_task(self, user_id: str, raw_input: str) -> dict: ...
    def get_task(self, task_id: str) -> dict | None: ...
    def update_task(self, task_id: str, **fields) -> None: ...
    def list_tasks(self) -> list[dict]: ...
    def create_trace(self, task_id: str, step: int, category: str, content: str) -> dict: ...
    def get_traces(self, task_id: str) -> list[dict]: ...

class SQLiteRepository:
    """Wraps existing SQLModel logic. Used in local Docker dev."""
    ...

class CosmosRepository:
    """Uses azure-cosmos SDK. Used in Azure cloud deployment."""
    ...

def get_repository() -> TaskRepository:
    backend = os.environ.get("DATABASE_BACKEND", "sqlite")
    if backend == "cosmos":
        return CosmosRepository()
    return SQLiteRepository()
```

### 6.4 New File: `backend/cosmos_client.py`

```python
"""
Azure Cosmos DB NoSQL client.
Containers: users (pk=/id), tasks (pk=/user_id), traces (pk=/task_id)
"""
from azure.cosmos import CosmosClient, PartitionKey

class CosmosDB:
    def __init__(self):
        self.client = CosmosClient(
            os.environ["COSMOS_ENDPOINT"],
            credential=os.environ["COSMOS_KEY"]
        )
        self.db = self.client.get_database_client(os.environ.get("COSMOS_DATABASE", "bmo-agent-db"))
        self.users = self.db.get_container_client("users")
        self.tasks = self.db.get_container_client("tasks")
        self.traces = self.db.get_container_client("traces")
```

### 6.5 New File: `backend/telemetry.py`

```python
"""
Application Insights — auto-instruments FastAPI.
No-op when APPLICATIONINSIGHTS_CONNECTION_STRING is not set.
"""
import os

def init_telemetry():
    conn_str = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn_str:
        return  # No-op in local dev
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(connection_string=conn_str)
```

### 6.6 Updated: `backend/requirements.txt`

```
# Core
fastapi>=0.104
uvicorn[standard]>=0.24
sqlmodel>=0.0.14
sse-starlette>=1.6
ollama>=0.3
mcp>=1.0
httpx>=0.25

# Azure - Foundry & Cosmos
azure-ai-projects>=2.0
azure-identity>=1.15
azure-cosmos>=4.7
azure-monitor-opentelemetry>=1.4
openai>=1.30

# Testing
pytest>=7.4
pytest-asyncio>=0.23
```

### 6.7 Updated: `backend/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install all Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Bundle MCP server (subprocess needs it in same image)
COPY mcp_server/ ./mcp_server/
RUN pip install --no-cache-dir -r mcp_server/requirements.txt

# Copy backend source
COPY backend/ ./

ENV MCP_SERVER_PATH=/app/mcp_server/mcp_server.py
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Infrastructure as Code (Terraform)

### Directory Structure

```
infra/
├── main.tf                 # Provider, resource group
├── variables.tf            # Input variables with defaults
├── outputs.tf              # Connection strings, URLs, endpoints
├── foundry.tf              # Microsoft Foundry resource + project + model deployment
├── cosmos.tf               # Cosmos DB account + database + containers
├── container_apps.tf       # Container Apps environment + backend app
├── static_web_app.tf       # Static Web Apps for frontend
├── monitoring.tf           # Log Analytics + Application Insights
├── acr.tf                  # Container Registry
├── terraform.tfvars.example # Example values (non-secret)
└── README.md               # Deployment guide
```

### `infra/main.tf`

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }
}

provider "azurerm" {
  features {
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
  }
}

resource "azurerm_resource_group" "main" {
  name     = "rg-bmo-agent-${var.environment}"
  location = var.location
  tags     = var.tags
}
```

### `infra/variables.tf`

```hcl
variable "location" {
  description = "Azure region"
  default     = "eastus2"
}

variable "environment" {
  description = "Environment name"
  default     = "prod"
}

variable "project_name" {
  description = "Project base name"
  default     = "bmo-agent"
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default = {
    project     = "bmo-coding-challenge"
    environment = "production"
    managed_by  = "terraform"
  }
}
```

### `infra/foundry.tf` — Microsoft Foundry

```hcl
# Microsoft Foundry Resource (replaces separate Azure OpenAI + AI Services)
# This is the unified AI platform resource
resource "azurerm_cognitive_account" "foundry" {
  name                = "${var.project_name}-foundry-${var.environment}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "AIServices"  # Unified Foundry resource type
  sku_name            = "S0"

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# GPT-4o-mini model deployment within Foundry
resource "azurerm_cognitive_deployment" "gpt4omini" {
  name                 = "gpt-4.1-nano"
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = "gpt-4.1-nano"
    version = "2024-07-18"
  }

  sku {
    name     = "GlobalStandard"
    capacity = 10  # 10K TPM — low cost, sufficient for demo
  }
}

# Content Safety is auto-enabled on all Foundry deployments — no extra config needed.
# Evaluation metrics are tracked automatically via the Foundry portal.
```

### `infra/cosmos.tf`

```hcl
resource "azurerm_cosmosdb_account" "main" {
  name                = "${var.project_name}-cosmos-${var.environment}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  enable_free_tier    = true  # FREE: 1000 RU/s + 25 GB

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  tags = var.tags
}

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = "${var.project_name}-db"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
}

resource "azurerm_cosmosdb_sql_container" "users" {
  name                = "users"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/id"]
  throughput          = 400
}

resource "azurerm_cosmosdb_sql_container" "tasks" {
  name                = "tasks"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/user_id"]
  throughput          = 400
}

resource "azurerm_cosmosdb_sql_container" "traces" {
  name                = "traces"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/task_id"]
  throughput          = 200
}
```

### `infra/container_apps.tf`

```hcl
resource "azurerm_container_app_environment" "main" {
  name                       = "${var.project_name}-env"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  tags = var.tags
}

resource "azurerm_container_app" "backend" {
  name                         = "${var.project_name}-backend"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  template {
    min_replicas = 0
    max_replicas = 2

    container {
      name   = "backend"
      image  = "${azurerm_container_registry.main.login_server}/backend:latest"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "LLM_PROVIDER"
        value = "foundry"
      }
      env {
        name        = "FOUNDRY_PROJECT_ENDPOINT"
        secret_name = "foundry-endpoint"
      }
      env {
        name  = "FOUNDRY_MODEL"
        value = "gpt-4.1-nano"
      }
      env {
        name  = "DATABASE_BACKEND"
        value = "cosmos"
      }
      env {
        name        = "COSMOS_ENDPOINT"
        secret_name = "cosmos-endpoint"
      }
      env {
        name        = "COSMOS_KEY"
        secret_name = "cosmos-key"
      }
      env {
        name  = "COSMOS_DATABASE"
        value = "${var.project_name}-db"
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-conn"
      }
      env {
        name  = "MCP_SERVER_PATH"
        value = "/app/mcp_server/mcp_server.py"
      }
      env {
        name  = "MAX_REACT_ITERATIONS"
        value = "10"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  secret {
    name  = "foundry-endpoint"
    value = azurerm_cognitive_account.foundry.endpoint
  }
  secret {
    name  = "cosmos-endpoint"
    value = azurerm_cosmosdb_account.main.endpoint
  }
  secret {
    name  = "cosmos-key"
    value = azurerm_cosmosdb_account.main.primary_key
  }
  secret {
    name  = "appinsights-conn"
    value = azurerm_application_insights.main.connection_string
  }

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }

  tags = var.tags
}
```

### `infra/static_web_app.tf`

```hcl
resource "azurerm_static_web_app" "frontend" {
  name                = "${var.project_name}-frontend"
  resource_group_name = azurerm_resource_group.main.name
  location            = "eastus2"  # SWA limited regions
  sku_tier            = "Free"
  sku_size            = "Free"

  tags = var.tags
}
```

### `infra/monitoring.tf`

```hcl
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.project_name}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = var.tags
}

resource "azurerm_application_insights" "main" {
  name                = "${var.project_name}-insights"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"

  tags = var.tags
}
```

### `infra/acr.tf`

```hcl
resource "azurerm_container_registry" "main" {
  name                = replace("${var.project_name}acr${var.environment}", "-", "")
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"  # ~$5/month
  admin_enabled       = true

  tags = var.tags
}
```

### `infra/outputs.tf`

```hcl
output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "backend_url" {
  value = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
}

output "frontend_url" {
  value = "https://${azurerm_static_web_app.frontend.default_host_name}"
}

output "foundry_endpoint" {
  value     = azurerm_cognitive_account.foundry.endpoint
  sensitive = true
}

output "cosmos_endpoint" {
  value     = azurerm_cosmosdb_account.main.endpoint
  sensitive = true
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "appinsights_connection_string" {
  value     = azurerm_application_insights.main.connection_string
  sensitive = true
}

output "swa_deployment_token" {
  value     = azurerm_static_web_app.frontend.api_key
  sensitive = true
}
```

### Deployment Commands

```bash
# One-time setup
cd infra
terraform init

# Plan & apply
terraform plan -out=tfplan
terraform apply tfplan

# Get outputs for CI/CD secrets
terraform output -json

# Verify with az cli
az resource list --resource-group rg-bmo-agent-prod --output table
az containerapp show --name bmo-agent-backend --resource-group rg-bmo-agent-prod
```

---

## CI/CD Pipeline

### `.github/workflows/deploy.yml` (updated)

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: '3.11'
  NODE_VERSION: '20'
  ACR_NAME: bmoagentacrprod

jobs:
  # ─── Backend Tests (pre-deploy) ────────────────────────────────────────
  backend-test:
    name: Backend Unit Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }

      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ runner.os }}-${{ hashFiles('backend/requirements.txt', 'mcp_server/requirements.txt') }}
          restore-keys: pip-${{ runner.os }}-

      - name: Install dependencies
        run: pip install -r backend/requirements.txt -r mcp_server/requirements.txt
      - name: Run unit tests
        run: cd backend && python -m pytest -v --tb=short

  # ─── Frontend Build ─────────────────────────────────────────────────────
  frontend-build:
    name: Frontend Build & Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - run: cd frontend && npm ci && npm run lint && npm run build

      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: frontend-dist
          path: frontend/dist

  # ─── Docker Build (with layer caching) ─────────────────────────────────
  docker-build:
    name: Docker Build Check
    runs-on: ubuntu-latest
    needs: [backend-test, frontend-build]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Cache Docker layers
        uses: actions/cache@v4
        with:
          path: /tmp/.buildx-cache
          key: docker-${{ runner.os }}-${{ hashFiles('backend/Dockerfile', 'backend/requirements.txt') }}
          restore-keys: docker-${{ runner.os }}-

      - name: Build backend image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: backend/Dockerfile
          push: false
          tags: backend:ci
          cache-from: type=local,src=/tmp/.buildx-cache
          cache-to: type=local,dest=/tmp/.buildx-cache-new,mode=max

      - name: Build frontend image
        run: docker build -t frontend:ci ./frontend

      - name: Move cache
        run: |
          rm -rf /tmp/.buildx-cache
          mv /tmp/.buildx-cache-new /tmp/.buildx-cache

  # ─── Deploy to Azure ────────────────────────────────────────────────────
  deploy:
    name: Deploy to Azure
    runs-on: ubuntu-latest
    needs: [docker-build]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Cache Docker layers (deploy)
        uses: actions/cache@v4
        with:
          path: /tmp/.buildx-cache
          key: docker-${{ runner.os }}-${{ hashFiles('backend/Dockerfile', 'backend/requirements.txt') }}
          restore-keys: docker-${{ runner.os }}-

      - name: Build & push backend image to ACR
        run: |
          az acr login --name ${{ env.ACR_NAME }}
          docker buildx build \
            --cache-from type=local,src=/tmp/.buildx-cache \
            --tag ${{ env.ACR_NAME }}.azurecr.io/backend:${{ github.sha }} \
            --tag ${{ env.ACR_NAME }}.azurecr.io/backend:latest \
            --file backend/Dockerfile \
            --push .

      - name: Deploy backend to Container Apps
        run: |
          az containerapp update \
            --name bmo-agent-backend \
            --resource-group rg-bmo-agent-prod \
            --image ${{ env.ACR_NAME }}.azurecr.io/backend:${{ github.sha }}

      - name: Download frontend artifact
        uses: actions/download-artifact@v4
        with:
          name: frontend-dist
          path: frontend/dist

      - name: Deploy frontend to Static Web Apps
        uses: Azure/static-web-apps-deploy@v1
        with:
          azure_static_web_apps_api_token: ${{ secrets.SWA_DEPLOYMENT_TOKEN }}
          repo_token: ${{ secrets.GITHUB_TOKEN }}
          action: "upload"
          app_location: "/frontend"
          output_location: "dist"
        env:
          VITE_API_URL: ${{ secrets.BACKEND_URL }}

  # ─── Post-Deploy Smoke Tests ───────────────────────────────────────────
  post-deploy-test:
    name: Post-Deploy Verification
    runs-on: ubuntu-latest
    needs: [deploy]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }

      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ runner.os }}-${{ hashFiles('backend/requirements.txt') }}
          restore-keys: pip-${{ runner.os }}-

      - name: Install test dependencies
        run: pip install httpx pytest

      - name: Wait for deployment to stabilize
        run: sleep 30

      - name: Run smoke tests against live backend
        env:
          BACKEND_URL: ${{ secrets.BACKEND_URL }}
        run: |
          python -c "
          import httpx, sys
          url = '${{ secrets.BACKEND_URL }}'
          # Health check
          r = httpx.get(f'{url}/api/health', timeout=30)
          assert r.status_code == 200, f'Health check failed: {r.status_code}'
          print('✓ Health endpoint OK')
          # Task creation
          r = httpx.post(f'{url}/api/task', json={'description': 'CI smoke test: calculate 2+2'}, timeout=60)
          assert r.status_code in (200, 201), f'Task creation failed: {r.status_code}'
          print(f'✓ Task created: {r.json().get(\"id\", \"ok\")}')
          # List tasks
          r = httpx.get(f'{url}/api/tasks', timeout=30)
          assert r.status_code == 200, f'List tasks failed: {r.status_code}'
          print(f'✓ Tasks list OK ({len(r.json())} tasks)')
          print('All smoke tests passed')
          "
```

### Caching Strategy

| What | Cache Key | Saves |
|------|-----------|-------|
| Python pip packages | `pip-{os}-{hash(requirements.txt)}` | ~30s install time |
| Node modules | Built-in `actions/setup-node` with `cache: 'npm'` | ~20s install time |
| Docker layers | `docker-{os}-{hash(Dockerfile, requirements.txt)}` | ~60-90s rebuild time |
| Frontend build artifact | Uploaded between jobs via `actions/upload-artifact` | Avoids rebuilding in deploy |

Caches invalidate automatically when `requirements.txt`, `package-lock.json`, or `Dockerfile` change.

### GitHub Secrets Required

| Secret | How to Get |
|--------|-----------|
| `AZURE_CREDENTIALS` | `az ad sp create-for-rbac --name bmo-deploy --role Contributor --scopes /subscriptions/<sub-id>` |
| `SWA_DEPLOYMENT_TOKEN` | `terraform output swa_deployment_token` |
| `BACKEND_URL` | `terraform output backend_url` |

---

## Frontend Redesign

### Design Direction: "Terminal Luxe"

A refined dark terminal aesthetic — monospace where it matters, generous whitespace, kinetic micro-interactions, and a distinctive command-bar input.

### Visual Changes

| Element | Current | New |
|---------|---------|-----|
| Font | Inter + Fira Code | **Geist Mono** (code/display) + **Geist Sans** (body) |
| Input style | Standard text field | CMD+K style command bar with glow border |
| Trace display | Plain list | Animated vertical timeline with connectors |
| Color scheme | Blue/violet gradient | Electric cyan (#06b6d4) + warm amber (#f59e0b) on deep navy |
| Layout | Fixed sidebar | Collapsible sidebar, keyboard shortcut (Cmd+B) |
| Animations | Basic slideIn | Staggered entry reveals, pulse indicators, typing effect |
| Cards | Flat dark | Subtle noise texture + glassmorphism edge glow |
| Status | Static dot | Animated pulse ring when streaming |

### Key UI Components

1. **Command Bar** — Full-width, centered, with animated placeholder cycling through example prompts
2. **Execution Timeline** — Vertical connector line with animated dots, each step fades/slides in with staggered delay
3. **Streaming Indicator** — Pulsing ring + "Agent thinking..." with animated ellipsis
4. **History Grid** — Cards with hover-lift effect, color-coded status badges
5. **Mobile** — Bottom sheet input, horizontal swipe between Agent/History views

### Implementation

- Update `frontend/src/index.css` with new design tokens and component styles
- Minor `App.tsx` adjustments for timeline layout and animation classes
- Add Geist font via Google Fonts or self-host
- Use Playwright to verify the design renders correctly

---

## Documentation Plan

### Files to Create/Update

| File | Purpose |
|------|---------|
| `README.md` | Complete rewrite: local setup + Azure deploy + architecture + challenge checklist |
| `docs/architecture.md` | Updated with Azure + Foundry components |
| `docs/azure-deployment.md` | Step-by-step Azure setup from scratch |
| `docs/tools.md` | All 8 MCP tools with descriptions, parameters, examples |
| `docs/api-reference.md` | All API endpoints with request/response schemas |
| `docs/foundry-integration.md` | How the Foundry integration works, content safety, eval |
| `docs/diagrams/system_architecture.png` | Generated with Python `diagrams` library |
| `docs/diagrams/cicd_pipeline.png` | Generated with Python `diagrams` library |
| `docs/diagrams/agent_flow.png` | ReAct loop sequence diagram |
| `infra/README.md` | Terraform usage: init, plan, apply, destroy |

### Architecture Diagrams Script (`docs/generate_diagrams.py`)

```python
from diagrams import Diagram, Cluster, Edge
from diagrams.azure.compute import ContainerApps
from diagrams.azure.database import CosmosDb
from diagrams.azure.web import StaticApps
from diagrams.azure.ai import CognitiveServices
from diagrams.azure.analytics import ApplicationInsights
from diagrams.azure.devops import Repos
from diagrams.azure.integration import LogicApps
from diagrams.onprem.client import Users
from diagrams.onprem.container import Docker
from diagrams.programming.framework import React, FastAPI

# Diagram 1: System Architecture
# Diagram 2: CI/CD Pipeline
# Diagram 3: Agent ReAct Flow
```

---

## Implementation Sequence

| Phase | Step | Task | Est. Time |
|-------|------|------|-----------|
| **A: Tools** | 1 | Add 5 new MCP tools (`mcp_server/mcp_server.py`) | 30 min |
| **A: Tools** | 2 | Add tests for all new tools | 20 min |
| **B: Abstractions** | 3 | Create `backend/llm_client.py` (Ollama + Foundry) | 25 min |
| **B: Abstractions** | 4 | Create `backend/repository.py` + `cosmos_client.py` | 30 min |
| **B: Abstractions** | 5 | Create `backend/telemetry.py` | 10 min |
| **B: Abstractions** | 6 | Modify `agent.py`, `router.py`, `main.py` to use abstractions | 25 min |
| **C: Frontend** | 7 | Redesign CSS (Terminal Luxe theme) | 40 min |
| **C: Frontend** | 8 | Update App.tsx for timeline layout | 15 min |
| **C: Frontend** | 9 | Test with Playwright | 15 min |
| **D: Infra** | 10 | Write all Terraform configs (`infra/`) | 30 min |
| **D: Infra** | 11 | Update Dockerfile for production | 10 min |
| **D: Infra** | 12 | Update CI/CD pipeline (`.github/workflows/deploy.yml`) | 15 min |
| **E: Docs** | 13 | Generate architecture diagrams | 15 min |
| **E: Docs** | 14 | Write all documentation | 30 min |
| **E: Docs** | 15 | Update README.md (comprehensive) | 20 min |
| **F: Deploy** | 16 | `terraform init && terraform apply` | 10 min |
| **F: Deploy** | 17 | Configure GitHub secrets, push to repo | 10 min |
| **F: Deploy** | 18 | End-to-end test (local Docker + Azure cloud) | 15 min |
| **F: Deploy** | 19 | Verify Foundry portal (content safety, eval metrics) | 10 min |

**Total estimated: ~6 hours**

---

## Verification & Testing

### Local Verification
```bash
# 1. Docker Compose still works (unchanged local experience)
docker compose up --build
curl http://localhost:8000/api/health
# Submit task at http://localhost:3000

# 2. All tests pass (old + new tool tests)
cd backend && python -m pytest -v

# 3. Multi-step reasoning works
# Submit: "What's the SHA-256 of today's date?"
# Expected: datetime_tool → hash_generator → final answer
```

### Azure Verification
```bash
# 4. Terraform deploys
cd infra && terraform plan && terraform apply

# 5. Backend health check
curl https://$(terraform output -raw backend_url)/api/health

# 6. End-to-end
# Visit frontend URL, submit task → Foundry GPT-4o-mini responds
# Verify SSE streaming, tool calls, Cosmos DB persistence

# 7. Foundry content safety
# Submit harmful prompt → should be blocked by content filter
# Check Foundry portal → evaluation metrics visible

# 8. Application Insights
# Azure Portal → App Insights → Live Metrics → see requests

# 9. CI/CD
# git push to main → GitHub Actions green → deployed
```

### Challenge Final Checklist

| Requirement | How Verified |
|------------|--------------|
| Frontend: text input, submit, view result | Playwright test |
| Frontend: history, inspect traces | Playwright test |
| Backend: task → agent → tool → result | pytest + manual |
| 3+ tools (we have 8) | pytest for each tool |
| Persistence (SQLite local, Cosmos cloud) | pytest + Azure test |
| Execution trace (real-time SSE) | Manual test |
| **Bonus: Tests** | `pytest -v` (full coverage) |
| **Bonus: Docker** | `docker compose up` |
| **Bonus: Retry/error-handling** | Exponential backoff in agent.py |
| **Bonus: Multi-step reasoning** | Multi-tool prompts tested |
| **Bonus: Real-time streaming** | SSE verified |
| **Bonus: RBAC** | SystemUser with role_type |

---

## Environment Variables Reference

| Variable | Local (Docker) | Azure (Container Apps) |
|----------|---------------|------------------------|
| `LLM_PROVIDER` | `ollama` | `foundry` |
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | *(not set)* |
| `OLLAMA_MODEL` | `qwen2.5:0.5b` | *(not set)* |
| `FOUNDRY_PROJECT_ENDPOINT` | *(not set)* | `https://<resource>.ai.azure.com/api/projects/<project>` |
| `FOUNDRY_MODEL` | *(not set)* | `gpt-4.1-nano` |
| `DATABASE_BACKEND` | `sqlite` | `cosmos` |
| `DATABASE_URL` | `sqlite:///./data/app.db` | *(not set)* |
| `COSMOS_ENDPOINT` | *(not set)* | `https://bmo-agent-cosmos-prod.documents.azure.com:443/` |
| `COSMOS_KEY` | *(not set)* | *(from Terraform output / secret)* |
| `COSMOS_DATABASE` | *(not set)* | `bmo-agent-db` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | *(not set)* | *(from Terraform output / secret)* |
| `MCP_SERVER_PATH` | `/app/mcp_server/mcp_server.py` | `/app/mcp_server/mcp_server.py` |
| `MAX_REACT_ITERATIONS` | `10` | `10` |

---

## Cost Summary

| Resource | Monthly Cost |
|----------|------|
| Static Web Apps (Free) | $0 |
| Container Apps (Free allotment) | $0 |
| Cosmos DB (Free tier) | $0 |
| Microsoft Foundry (platform) | $0 |
| GPT-4.1-nano tokens (~100 requests/day) | ~$0.20-0.50 |
| Container Registry (Basic) | ~$5 |
| Application Insights (< 5GB) | $0 |
| Log Analytics (< 5GB) | $0 |
| **Total** | **~$5-6/mo** |

Well within the $200 credit for months of operation.

---

## Cleanup: .gitignore Strategy

Keep all files locally for reference but exclude non-essential artifacts from the published repo via `.gitignore`:

```gitignore
# ─── Development artifacts ────────────────────────────────────────────────
graphify-out/
temp/
*.pdf

# ─── Conda env files (Docker uses requirements.txt) ──────────────────────
environment.yml
environment-full.yml

# ─── Nginx (Container Apps handles routing in cloud) ─────────────────────
nginx/

# ─── Python ──────────────────────────────────────────────────────────────
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/

# ─── Node ────────────────────────────────────────────────────────────────
node_modules/
dist/

# ─── IDE ─────────────────────────────────────────────────────────────────
.vscode/
.idea/
*.swp

# ─── Secrets ─────────────────────────────────────────────────────────────
.env
.env.*
```

This keeps conda files and challenge PDFs available locally while the CI/CD pipeline only operates on `requirements.txt` and the actual source code.
