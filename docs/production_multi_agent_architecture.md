# Production Multi-Agent System Architecture

> **Context**: This document describes how BMO Agent would evolve from its current coding-challenge scope into a fully productionized **Multi-Agent System (MAS)** with autonomous CI/CD, QA validation, DevOps automation, Human-in-the-Loop (HITL) guardrails, and enterprise-grade cloud infrastructure — mapped to both **Azure** and **AWS** equivalents.

---

## Table of Contents

1. [Current State vs Production Vision](#current-state-vs-production-vision)
2. [Multi-Agent System Architecture](#multi-agent-system-architecture)
3. [Agent Taxonomy](#agent-taxonomy)
4. [Orchestration Patterns](#orchestration-patterns)
5. [HITL Guardrails Framework](#hitl-guardrails-framework)
6. [Cloud Infrastructure — Azure vs AWS](#cloud-infrastructure--azure-vs-aws)
7. [CI/CD with Autonomous Agents](#cicd-with-autonomous-agents)
8. [Data & Observability Stack](#data--observability-stack)
9. [Security & Compliance](#security--compliance)
10. [Implementation Roadmap](#implementation-roadmap)

---

## Current State vs Production Vision

| Dimension | Current (Challenge) | Production MAS |
|-----------|-------------------|----------------|
| Agent count | 1 (ReAct loop) | 10+ specialized agents |
| Orchestration | Single sequential loop | Planner → child agents (sync + async) |
| Tools | 8 MCP tools | 50+ tools + external API integrations |
| LLM | Single model (Ollama/GPT-4.1-nano) | Model routing (GPT-4o for planning, GPT-4.1-nano for tools, Claude for code) |
| CI/CD | GitHub Actions (static YAML) | Self-healing pipeline with QA + DevOps agents |
| Auth | Token-based | Azure AD / AWS Cognito with Security Groups |
| Guardrails | Content Safety filter only | Multi-layer HITL with approval workflows |
| Observability | App Insights | Full distributed tracing + agent-level metrics |
| State | SQLite/Cosmos (simple) | Event-sourced with saga pattern |

---

## Multi-Agent System Architecture

### High-Level Topology

```
                          ┌─────────────────────┐
                          │     Human User       │
                          │  (HITL Approver)      │
                          └──────────┬────────────┘
                                     │ Approval / Override
                          ┌──────────▼────────────┐
                          │   API Gateway          │
                          │   (Auth + Rate Limit)  │
                          └──────────┬────────────┘
                                     │
                          ┌──────────▼────────────┐
                          │   PLANNER AGENT        │
                          │   (Orchestrator)       │
                          │   ┌────────────────┐   │
                          │   │ Task Decomposer│   │
                          │   │ DAG Builder     │   │
                          │   │ Priority Queue  │   │
                          │   └────────────────┘   │
                          └──┬───┬───┬───┬───┬────┘
                             │   │   │   │   │
              ┌──────────────┘   │   │   │   └──────────────┐
              ▼                  ▼   │   ▼                  ▼
     ┌────────────┐    ┌──────────┐ │ ┌──────────┐  ┌────────────┐
     │ Research   │    │ Code     │ │ │ Data     │  │ DevOps     │
     │ Agent      │    │ Agent    │ │ │ Agent    │  │ Agent      │
     │ (async)    │    │ (sync)   │ │ │ (async)  │  │ (async)    │
     └────────────┘    └──────────┘ │ └──────────┘  └────────────┘
                                    │
                           ┌────────▼────────┐
                           │   QA Agent       │
                           │   (validates     │
                           │    all outputs)  │
                           └─────────────────┘
```

### Core Principle: DAG-Based Execution

The Planner Agent decomposes every task into a **Directed Acyclic Graph (DAG)** of subtasks. Each node is assigned to a specialized child agent. Edges define dependencies.

```python
# Pseudocode: Planner Agent task decomposition
class TaskDAG:
    """DAG of subtasks produced by the Planner Agent."""
    nodes: list[SubTask]       # Each assigned to a child agent
    edges: list[Dependency]    # (parent_id, child_id) — child waits for parent
    execution_mode: dict[str, Literal["sync", "async"]]  # Per-node

class SubTask:
    id: str
    agent_type: AgentType      # research, code, data, devops, qa
    prompt: str                # Instruction for the child agent
    requires_hitl: bool        # If True, pause for human approval before executing
    timeout_seconds: int
    retry_policy: RetryPolicy
```

---

## Agent Taxonomy

### 1. Planner Agent (Orchestrator)

| Property | Value |
|----------|-------|
| **Role** | Decomposes complex tasks into subtask DAGs, assigns to child agents |
| **LLM** | GPT-4o / Claude Opus (strongest reasoning) |
| **Invocation** | Synchronous — always the entry point |
| **HITL** | Presents execution plan for approval before dispatching |

**Capabilities:**
- Parse ambiguous natural language into structured plans
- Identify parallelizable subtasks (async fan-out)
- Estimate cost/time budgets per subtask
- Re-plan on child agent failure (self-healing)

### 2. Research Agent

| Property | Value |
|----------|-------|
| **Role** | Web search, document retrieval, knowledge synthesis |
| **LLM** | GPT-4o-mini (fast, cost-effective) |
| **Invocation** | Async — results don't block other agents |
| **Tools** | Web search API, RAG over internal docs, PDF parser |

### 3. Code Agent

| Property | Value |
|----------|-------|
| **Role** | Generate, review, refactor, and test code |
| **LLM** | Claude Sonnet / GPT-4o (strong code generation) |
| **Invocation** | Sync — downstream agents depend on output |
| **Tools** | Code interpreter, linter, test runner, git operations |
| **HITL** | Required for production code changes |

### 4. Data Agent

| Property | Value |
|----------|-------|
| **Role** | Query databases, transform data, generate reports |
| **LLM** | GPT-4.1-nano (structured output, low cost) |
| **Invocation** | Async — can run in parallel with research |
| **Tools** | SQL executor, pandas operations, chart generator |

### 5. QA Agent

| Property | Value |
|----------|-------|
| **Role** | Validates outputs from ALL other agents before delivery |
| **LLM** | GPT-4o (high accuracy for validation) |
| **Invocation** | Sync — final gate before user delivery |
| **HITL** | Auto-escalates to human when confidence < 85% |

**Validation checks:**
- Factual accuracy (cross-reference with sources)
- Code correctness (run tests, static analysis)
- Security scan (secrets, injection vulnerabilities)
- Compliance (PII detection, content policy)

### 6. DevOps Agent

| Property | Value |
|----------|-------|
| **Role** | Infrastructure management, deployment, monitoring |
| **LLM** | GPT-4.1-nano (structured IaC generation) |
| **Invocation** | Async — operates on infrastructure independently |
| **Tools** | Terraform executor, kubectl, cloud CLI, log analyzer |
| **HITL** | **Always required** — no autonomous infra changes |

### 7. CI/CD Agent

| Property | Value |
|----------|-------|
| **Role** | Manages build pipelines, test orchestration, release gates |
| **LLM** | GPT-4.1-nano |
| **Invocation** | Event-driven (triggered by git push, PR, schedule) |
| **Tools** | GitHub API, test runners, artifact registries |

---

## Orchestration Patterns

### Pattern 1: Synchronous Chain

```
Planner → Code Agent → QA Agent → User
```

Used when each step strictly depends on the previous output.

### Pattern 2: Async Fan-Out / Fan-In

```
                ┌→ Research Agent (async) ──┐
Planner ────────┤                           ├──→ QA Agent → User
                └→ Data Agent (async)   ────┘
```

Used when independent subtasks can run in parallel. The Planner fans out, collects results, then fans in for QA.

### Pattern 3: Event-Driven Pipeline (CI/CD)

```
git push → CI/CD Agent → Code Agent (review) → QA Agent (test)
    → DevOps Agent (deploy) → HITL Gate → Production
```

### Implementation: Message Queue Architecture

```python
# Azure: Azure Service Bus / AWS: Amazon SQS + SNS
class AgentMessage:
    task_id: str
    parent_task_id: str | None
    agent_type: AgentType
    payload: dict
    execution_mode: Literal["sync", "async"]
    priority: int              # 0=critical, 10=background
    created_at: datetime
    deadline: datetime | None  # Timeout
    hitl_required: bool

# Sync: Agent publishes result directly, caller awaits
# Async: Agent publishes to completion topic, Planner subscribes
```

| Component | Azure | AWS |
|-----------|-------|-----|
| Task Queue | Azure Service Bus | Amazon SQS |
| Event Bus | Event Grid | Amazon EventBridge |
| Async Fan-Out | Service Bus Topics | SNS Topics → SQS |
| Workflow Engine | Durable Functions | AWS Step Functions |
| Agent Compute | Container Apps (per-agent) | ECS Fargate (per-agent) |

---

## HITL Guardrails Framework

### Three-Tier Approval Model

```
┌─────────────────────────────────────────────────────────┐
│                   TIER 1: AUTOMATIC                      │
│  Low-risk operations execute without human approval      │
│  Examples: text processing, calculations, data queries   │
│  Confidence threshold: > 95%                             │
└───────────────────────────┬─────────────────────────────┘
                            │ Confidence 85-95%
┌───────────────────────────▼─────────────────────────────┐
│                   TIER 2: NOTIFY & PROCEED               │
│  Medium-risk: executes but notifies human for review     │
│  Examples: research synthesis, report generation         │
│  Human can retroactively reject within SLA               │
└───────────────────────────┬─────────────────────────────┘
                            │ Confidence < 85% OR high-risk
┌───────────────────────────▼─────────────────────────────┐
│                   TIER 3: APPROVAL REQUIRED              │
│  High-risk: paused until human explicitly approves       │
│  Examples: code deployment, infra changes, external API  │
│  Timeout: auto-reject after 4 hours                      │
└─────────────────────────────────────────────────────────┘
```

### HITL Integration Points

| Agent | Auto (Tier 1) | Notify (Tier 2) | Approve (Tier 3) |
|-------|--------------|-----------------|------------------|
| Research | Factual lookups | Synthesis/summaries | External API calls |
| Code | Read-only analysis | Code suggestions | Production commits |
| Data | SELECT queries | Data transformations | Schema migrations |
| DevOps | Log viewing | Scaling decisions | **All infra changes** |
| QA | Test execution | Flaky test overrides | Release gate bypass |

### Approval Workflow (Azure / AWS)

| Component | Azure | AWS |
|-----------|-------|-----|
| Approval Queue | Azure Service Bus + Logic Apps | SQS + Step Functions wait state |
| Notification | Microsoft Teams webhook | Slack via SNS + Lambda |
| Approval UI | Power Apps / custom React page | Custom React page |
| Audit Log | Cosmos DB + Immutable Blobs | DynamoDB + S3 (WORM) |
| Timeout | Durable Functions timer | Step Functions timeout |

---

## Cloud Infrastructure — Azure vs AWS

### Compute & Networking

| Component | Azure | AWS |
|-----------|-------|-----|
| **API Gateway** | Azure API Management | Amazon API Gateway |
| **Agent Compute** | Container Apps (per-agent scaling) | ECS Fargate tasks |
| **Background Workers** | Azure Functions (Durable) | AWS Lambda + Step Functions |
| **Service Mesh** | Container Apps internal DNS | App Mesh / ECS Service Connect |
| **Load Balancer** | Application Gateway | ALB |
| **CDN / Frontend** | Static Web Apps | CloudFront + S3 |
| **DNS** | Azure DNS | Route 53 |

### AI / LLM Stack

| Component | Azure | AWS |
|-----------|-------|-----|
| **LLM Gateway** | Azure AI Foundry | Amazon Bedrock |
| **Model Routing** | Foundry model catalog (1900+ models) | Bedrock model access |
| **Content Safety** | Azure Content Safety (built-in) | Bedrock Guardrails |
| **Prompt Mgmt** | Foundry Prompt Flow | Bedrock Prompt Management |
| **Fine-Tuning** | Foundry fine-tuning jobs | Bedrock Custom Models |
| **Embeddings / RAG** | Azure AI Search + Foundry | Bedrock Knowledge Bases + OpenSearch |
| **Agent Framework** | Foundry Agent Service / Semantic Kernel | Bedrock Agents / LangGraph |
| **Eval & Tracing** | Foundry Evaluation | Bedrock Invocation Logging + CloudWatch |

### Data & State

| Component | Azure | AWS |
|-----------|-------|-----|
| **Primary DB** | Cosmos DB (NoSQL) | DynamoDB |
| **Event Store** | Event Hubs + Cosmos Change Feed | Kinesis + DynamoDB Streams |
| **Cache** | Azure Cache for Redis | ElastiCache (Redis) |
| **Blob Storage** | Azure Blob Storage | S3 |
| **Search** | Azure AI Search | OpenSearch Serverless |
| **Message Queue** | Service Bus | SQS / SNS |
| **Workflow State** | Durable Functions storage | Step Functions state |

### Security & Identity

| Component | Azure | AWS |
|-----------|-------|-----|
| **Identity Provider** | Microsoft Entra ID (Azure AD) | AWS IAM Identity Center (SSO) |
| **App Auth** | Entra ID App Registration | Cognito User Pools |
| **Secrets** | Azure Key Vault | AWS Secrets Manager |
| **Managed Identity** | System-Assigned Managed Identity | IAM Roles for Tasks |
| **Network Security** | NSG + Private Endpoints | Security Groups + VPC Endpoints |
| **WAF** | Azure WAF on App Gateway | AWS WAF on CloudFront/ALB |
| **Compliance** | Microsoft Defender for Cloud | AWS Security Hub |

### Observability

| Component | Azure | AWS |
|-----------|-------|-----|
| **Metrics** | Azure Monitor + App Insights | CloudWatch Metrics |
| **Logs** | Log Analytics Workspace | CloudWatch Logs |
| **Traces** | App Insights Distributed Tracing | X-Ray |
| **Dashboards** | Azure Workbooks / Grafana | CloudWatch Dashboards / Grafana |
| **Alerting** | Azure Monitor Alerts | CloudWatch Alarms + SNS |
| **Agent-Level Metrics** | Custom App Insights events | Custom CloudWatch metrics |

---

## CI/CD with Autonomous Agents

### Self-Healing Pipeline Architecture

```
Developer pushes code
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│                CI/CD Agent (Event-Driven)                  │
│                                                           │
│  1. ANALYZE: Parse diff, identify affected components     │
│  2. PLAN: Generate test strategy based on changes         │
│  3. DISPATCH:                                             │
│     ├─→ Code Agent: automated code review (async)         │
│     ├─→ QA Agent: generate + run tests (async)            │
│     └─→ Security scan (async)                             │
│  4. GATE: Collect results, make go/no-go decision         │
│  5. DEPLOY (if approved):                                 │
│     └─→ DevOps Agent: progressive rollout (HITL Tier 3)   │
│  6. MONITOR:                                              │
│     └─→ Watch error rates post-deploy, auto-rollback      │
└───────────────────────────────────────────────────────────┘
```

### Pipeline Stages with Agent Integration

| Stage | Traditional CI/CD | Agent-Enhanced CI/CD |
|-------|------------------|---------------------|
| **Code Review** | Manual PR review | Code Agent generates review, human approves |
| **Test Generation** | Static test suite | QA Agent generates tests for new code paths |
| **Test Execution** | Run all tests | QA Agent prioritizes tests by risk, runs subset |
| **Security Scan** | SAST/DAST tools | Code Agent interprets findings, suggests fixes |
| **Deploy Decision** | Human approves | CI/CD Agent recommends, HITL gate for prod |
| **Rollout** | All-at-once | DevOps Agent does canary (1% → 10% → 100%) |
| **Post-Deploy** | Manual monitoring | DevOps Agent watches metrics, auto-rollbacks |
| **Incident Response** | PagerDuty → human | DevOps Agent triages, proposes fix, HITL approves |

### Progressive Deployment (Canary)

```
DevOps Agent Canary Rollout:

  Step 1: Deploy to 1% traffic     ──→ Monitor 15 min
  Step 2: Promote to 10% traffic   ──→ Monitor 15 min
  Step 3: Promote to 50% traffic   ──→ Monitor 30 min
  Step 4: Promote to 100%          ──→ HITL notification

  Auto-Rollback Triggers:
  - Error rate > 1% (p99)
  - Latency > 2x baseline
  - Any 5xx from new revision
  - QA Agent flags regression in synthetic tests
```

---

## Data & Observability Stack

### Agent-Level Metrics

Each agent emits standardized telemetry:

```python
class AgentMetrics:
    agent_type: str
    task_id: str
    # Performance
    latency_ms: float
    token_input: int
    token_output: int
    llm_model_used: str
    # Quality
    confidence_score: float        # 0.0 - 1.0
    hitl_escalated: bool
    hitl_outcome: str | None       # "approved" | "rejected" | "modified"
    # Cost
    estimated_cost_usd: float
    # Reliability
    retry_count: int
    error_type: str | None
```

### Event-Sourced Architecture

All agent actions are stored as immutable events for full auditability:

```
Event Store Schema:
┌──────────────────────────────────────────────────────┐
│ event_id │ task_id │ agent │ type        │ timestamp │
│──────────┼─────────┼───────┼─────────────┼───────────│
│ evt-001  │ tsk-42  │ plan  │ task_created│ 10:00:01  │
│ evt-002  │ tsk-42  │ plan  │ dag_built   │ 10:00:03  │
│ evt-003  │ tsk-42  │ code  │ assigned    │ 10:00:03  │
│ evt-004  │ tsk-42  │ data  │ assigned    │ 10:00:03  │
│ evt-005  │ tsk-42  │ data  │ completed   │ 10:00:08  │
│ evt-006  │ tsk-42  │ code  │ hitl_needed │ 10:00:10  │
│ evt-007  │ tsk-42  │ code  │ hitl_approve│ 10:02:30  │
│ evt-008  │ tsk-42  │ qa    │ validated   │ 10:02:35  │
│ evt-009  │ tsk-42  │ plan  │ completed   │ 10:02:36  │
└──────────────────────────────────────────────────────┘
```

---

## Security & Compliance

### Zero-Trust Agent Security Model

```
┌─────────────────────────────────────────────────────────┐
│                  Security Layers                         │
│                                                         │
│  Layer 1: NETWORK                                       │
│    - All agents in private VNet / VPC                    │
│    - No public internet access for agents                │
│    - API Gateway is the only ingress point               │
│                                                         │
│  Layer 2: IDENTITY                                      │
│    - Each agent has its own Managed Identity / IAM Role  │
│    - Least-privilege: Code Agent can't touch infra       │
│    - Scoped secrets: agents only see their own keys      │
│                                                         │
│  Layer 3: DATA                                          │
│    - All data encrypted at rest (AES-256)                │
│    - All inter-agent communication over mTLS             │
│    - PII detection and masking before LLM calls          │
│                                                         │
│  Layer 4: LLM                                           │
│    - Content Safety filters on all LLM calls             │
│    - Prompt injection detection middleware               │
│    - Output validation before delivery to user           │
│    - Token budget enforcement per-agent                  │
│                                                         │
│  Layer 5: AUDIT                                         │
│    - Immutable event log (append-only)                   │
│    - All HITL decisions recorded with approver identity   │
│    - Compliance reports auto-generated weekly             │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-4)
- [ ] Implement message queue architecture (Service Bus / SQS)
- [ ] Build Planner Agent with DAG decomposition
- [ ] Add HITL Tier 3 approval workflow for all agents
- [ ] Migrate auth to Entra ID / Cognito

### Phase 2: Core Agents (Weeks 5-8)
- [ ] Implement Code Agent with git integration
- [ ] Implement QA Agent with test generation
- [ ] Implement Data Agent with SQL/pandas tools
- [ ] Add async fan-out/fan-in orchestration

### Phase 3: DevOps & CI/CD Agents (Weeks 9-12)
- [ ] Implement DevOps Agent with Terraform/kubectl tools
- [ ] Build CI/CD Agent triggered by GitHub webhooks
- [ ] Implement canary deployment with auto-rollback
- [ ] Add self-healing pipeline (auto-fix failing tests)

### Phase 4: Polish & Scale (Weeks 13-16)
- [ ] Implement HITL Tier 1 and Tier 2 (auto + notify)
- [ ] Add model routing (cost-optimized LLM selection)
- [ ] Build observability dashboards (agent-level metrics)
- [ ] Load testing and horizontal scaling validation
- [ ] Compliance audit and penetration testing

---

> **Note**: This document represents the target architecture for a production enterprise deployment. The current BMO Agent implementation demonstrates the core patterns (ReAct loop, tool calling, streaming, persistence) that serve as the foundation for this vision. The architecture is designed to scale incrementally — each phase builds on the previous without requiring rewrites.
