# BMO Agent - Agentic Execution Framework

A production-grade AI agent system with dual-mode deployment: local (Ollama + SQLite) and cloud (Azure Foundry + Cosmos DB). Interprets natural language tasks, reasons using a ReAct loop, executes 8 deterministic tools via MCP, and streams results in real-time.

![System Architecture](docs/diagrams/system_architecture.png)

---

## Quick Start

### Local Development (Docker)

```bash
# Ensure Ollama is running
ollama serve &
ollama pull qwen2.5:0.5b

# Start all services
docker compose up --build

# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
# Swagger:  http://localhost:8000/docs
```

### Local Development (Manual)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install && npm run dev
```

---

## Architecture

### Dual-Mode Design

| Component | Local | Cloud (Azure) |
|-----------|-------|---------------|
| LLM | Ollama (qwen2.5:0.5b) | Azure Foundry (GPT-4.1-nano) |
| Database | SQLite | Cosmos DB (Free Tier) |
| Frontend | Vite dev server | Azure Static Web Apps |
| Backend | Uvicorn | Azure Container Apps |
| Telemetry | Console logs | Application Insights |
| Auth | None (local dev) | Azure Key Vault tokens |

Controlled by environment variables — same codebase, different providers.

### System Architecture

```
User Browser
    │
    ▼
┌─────────────────────┐         ┌─────────────────────────┐
│ Static Web App      │  API    │ Container Apps           │
│ (React + Vite)      │────────▶│ (FastAPI Backend)        │
└─────────────────────┘         │  ├── LLM Client          │
                                │  ├── Repository Layer     │
                                │  └── Telemetry Module     │
                                └────┬──────────┬──────────┘
                                     │          │
                            ┌────────┘          └────────┐
                            ▼                            ▼
                    ┌──────────────┐            ┌──────────────┐
                    │ MCP Server   │            │ Azure Foundry│
                    │ (8 tools)    │            │ GPT-4.1-nano │
                    └──────────────┘            └──────────────┘
                                                       │
                                               ┌───────┴───────┐
                                               │  Cosmos DB    │
                                               │  (Free Tier)  │
                                               └───────────────┘
```

![CI/CD Pipeline](docs/diagrams/cicd_pipeline.png)

---

## MCP Tools (8)

| # | Tool | Description | Example |
|---|------|-------------|---------|
| 1 | `text_processor` | String ops (upper, lower, wordcount, reverse, title) | `text_processor("hello", "uppercase")` → `"HELLO"` |
| 2 | `calculator` | Safe AST-based arithmetic | `calculator("(3+5)*2")` → `"16"` |
| 3 | `weather_mock` | Deterministic synthetic weather | `weather_mock("Tokyo")` → `{"temp": 31}` |
| 4 | `datetime_tool` | Current time, date math, formatting | `datetime_tool("add_days", "2024-01-01", days=90)` |
| 5 | `unit_converter` | Temp/length/weight/volume conversion | `unit_converter(100, "F", "C")` → `37.78` |
| 6 | `json_formatter` | Validate, prettify, minify, extract keys | `json_formatter('{"a":1}', "prettify")` |
| 7 | `hash_generator` | MD5, SHA-1, SHA-256, SHA-512 | `hash_generator("hello", "sha256")` |
| 8 | `random_generator` | Random numbers, UUIDs, passwords | `random_generator("password", length=16)` |

### Multi-Step Reasoning Examples

| Prompt | Tool Chain |
|--------|-----------|
| "What's the SHA-256 of today's date?" | datetime_tool → hash_generator |
| "Convert 98.6°F to Celsius" | unit_converter |
| "Generate a random number 1-1000 and multiply by 3" | random_generator → calculator |

---

## Azure Deployment

### Prerequisites

- Azure CLI (`az login`)
- Terraform >= 1.5
- GitHub repo with secrets configured

### Deploy with Terraform

```bash
cd infra
terraform init
terraform plan
terraform apply
```

### Resources Provisioned

| Service | SKU | Monthly Cost |
|---------|-----|-------------|
| Static Web Apps | Free | $0 |
| Container Apps | Consumption | $0 (free allotment) |
| Cosmos DB | Free Tier (1000 RU/s) | $0 |
| AI Foundry (GPT-4.1-nano) | Pay-per-token | ~$0.20-0.50 |
| Container Registry | Basic | ~$5 |
| Application Insights | Free (5GB) | $0 |
| **Total** | | **~$5-6/mo** |

### GitHub Secrets Required

| Secret | Source |
|--------|--------|
| `AZURE_CREDENTIALS` | `az ad sp create-for-rbac` |
| `SWA_DEPLOYMENT_TOKEN` | `terraform output swa_deployment_token` |
| `BACKEND_URL` | `terraform output backend_url` |

---

## CI/CD Pipeline

Push to `main` triggers:

1. **Backend Tests** — pytest with pip caching
2. **Frontend Build** — npm ci + lint + build with npm caching
3. **Docker Build** — Buildx with layer caching
4. **Deploy** — Push to ACR, update Container Apps, deploy Static Web App
5. **Post-Deploy Smoke Tests** — Health check + task creation on live endpoint

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Readiness probe |
| `GET` | `/api/llm/status` | LLM provider health |
| `POST` | `/api/task` | Submit task `{"prompt": "..."}` |
| `GET` | `/api/task/{id}/stream` | SSE execution stream |
| `GET` | `/api/task/{id}` | Task detail with traces |
| `GET` | `/api/tasks` | List all tasks |
| `POST` | `/api/auth/login` | Authenticate with email + token |

---

## Environment Variables

| Variable | Default | Cloud Value |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `azure_foundry` |
| `DATABASE_BACKEND` | `sqlite` | `cosmos` |
| `OLLAMA_HOST` | `http://localhost:11434` | — |
| `OLLAMA_MODEL` | `qwen2.5:0.5b` | — |
| `FOUNDRY_ENDPOINT` | — | AI Foundry URL |
| `FOUNDRY_API_KEY` | — | From Key Vault |
| `FOUNDRY_MODEL` | `gpt-4.1-nano` | `gpt-4.1-nano` |
| `COSMOS_ENDPOINT` | — | Cosmos DB URL |
| `COSMOS_KEY` | — | From Key Vault |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | — | App Insights CS |
| `KEY_VAULT_URL` | — | Azure Key Vault URL |

---

## Running Tests

```bash
cd backend && python -m pytest -v
# 47 tests pass in ~5s
```

---

## Project Structure

```
BMO/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── router.py            # API endpoints
│   ├── agent.py             # ReAct loop (provider-agnostic)
│   ├── llm_client.py        # LLM abstraction (Ollama/Foundry)
│   ├── repository.py        # DB abstraction (SQLite/Cosmos)
│   ├── telemetry.py         # Azure Monitor integration
│   ├── models.py            # SQLModel entities
│   ├── database.py          # Engine config
│   ├── auth.py              # Authentication middleware
│   └── tests/
├── frontend/
│   └── src/
│       ├── App.tsx           # Main app (Terminal Luxe design)
│       └── index.css         # Design system
├── mcp_server/
│   └── mcp_server.py        # 8 MCP tools
├── infra/
│   ├── main.tf              # All Azure resources
│   └── outputs.tf           # Deployment URLs
├── docs/
│   ├── generate_diagrams.py  # Architecture diagram generator
│   └── diagrams/            # PNG architecture diagrams
├── .github/workflows/
│   └── deploy.yml           # CI/CD with caching
├── docker-compose.yml
└── IMPLEMENTATION_PLAN.md
```

---

## Authentication

The cloud deployment includes token-based authentication:

- **Allowed users**: Pre-registered email addresses stored in Azure Key Vault
- **Login**: Email + generated access token
- **Tokens**: Stored securely in Azure Key Vault (equivalent to AWS Secrets Manager)
- **Local dev**: Auth disabled by default (no KEY_VAULT_URL set)

---

## Challenge Requirements Checklist

| Requirement | Status |
|-------------|--------|
| Working agent with tool calling | Done (8 tools) |
| ReAct reasoning loop | Done (bounded, 10 iterations) |
| Real-time execution streaming | Done (SSE) |
| Persistent execution traces | Done (SQLite/Cosmos) |
| Unit tests | Done (47 tests) |
| Docker containerization | Done (Compose + production) |
| Retry/error handling | Done (exponential backoff) |
| Multi-step reasoning | Done (tool chaining) |
| RBAC | Done (auth + roles) |
| Cloud deployment | Done (Azure, Terraform) |
| CI/CD pipeline | Done (GitHub Actions) |
| Architecture documentation | Done (diagrams + docs) |

---

## License

Built as a coding challenge submission for BMO.
