# GAAP — Governed Autonomous Agent Platform

[![CI](https://github.com/santhoshnalla88/contract-bound-autonomy/actions/workflows/ci.yml/badge.svg)](https://github.com/santhoshnalla88/contract-bound-autonomy/actions)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://react.dev/)

> **"Reason freely within boundaries. Act only with authorization."**

A production-grade, RAG-augmented, **contract-bound** autonomous operations platform. GAAP reasons over organization-specific knowledge (vector store + knowledge graph), enforces machine-readable operational boundaries before any action, executes through a controlled MCP boundary with a **pluggable driver registry** (Kubernetes, Linux/Windows hosts, batch jobs, cloud/SaaS APIs, or mock), and fronts everything with an authenticated, real-time **Operations Control Plane**.

**Author:** [Santhosh Kumar Nalla](https://linkedin.com/in/techiesanthoshnalla) — Senior Software Engineer & AI Engineering Architect | 14+ years in financial platforms (Mastercard), Java/Python, agentic AI systems

---

## Why This Project

Enterprises want to hand real operational work to AI agents, but cannot accept **unbounded autonomy** in regulated, high-blast-radius environments (payments, infrastructure, fraud). Today's agent stacks optimize for capability, not **governance** — there is no standard way to say *"this agent may do X, never Y, only up to this risk/cost, and must ask a human for Z — and prove it afterwards."*

GAAP solves this with a **layered governance stack** that wraps every LLM decision in deterministic, auditable controls.

---

## Architecture

```
                    ┌────────────────────────────┐
                    │  Operations Control Plane   │  React · JWT · RBAC · SSE
                    │     (Vite + React 19)       │
                    └──────────────┬─────────────┘
                          REST + SSE (Bearer / ?token)
                                   │
        ┌──────────────────────────┴──────────────────────────┐
        │                       FastAPI                        │
        │  Auth · Incidents · Approvals · Contracts · Knowledge│
        │  Rate limiting · CORS · /metrics · /ready            │
        └───────┬───────────────────────────────────┬─────────┘
        enqueue │ (Arq / Redis)               inspect │ state
                ▼                                     ▼
        ┌───────────────┐   Postgres checkpointer   ┌───────────────┐
        │  Arq worker   │◀─────── shared state ─────▶│  LangGraph    │
        │ runs workflow │   Redis Streams events     │ retry + HITL  │
        └──────┬────────┘                            └──────┬────────┘
               │                                            │
       ┌───────┴────────┐   ┌──────────────┐   ┌────────────┴────────┐
       │  RAG (Chroma)  │   │ Planner (LLM)│──▶│  Guardrail Engine   │
       │  + Neo4j Graph │   └──────────────┘   └──────────┬──────────┘
       └────────────────┘                                  ▼
                                              ┌─────────────────────────┐
                                              │   MCP execution boundary │
                                              │ pluggable driver registry│
                                              │ k8s · host · batch · SaaS│
                                              └─────────────────────────┘
  Postgres (state · audit · users)  ·  Redis (events · queue)  ·  Neo4j  ·  LangSmith
```

---

## Key Differentiators

| Feature | Description |
|---------|-------------|
| 🛡️ **Contract-Bound Execution** | Machine-readable operational contracts define what agents can/cannot do — deterministic enforcement the LLM cannot override |
| 🔄 **Adaptive Contracts** | Rules that recompute permissions from runtime context (amount, severity, trust score) |
| 📊 **Numeric Risk Scoring** | 0–100 risk score from complexity, business impact, compliance, and trust — drives allow/approve/block/escalate |
| 🧠 **Hybrid RAG + Knowledge Graph** | ChromaDB vector retrieval + Neo4j service-dependency graph for rich context |
| 👤 **Human-in-the-Loop** | Pause-and-resume approval workflow with audited approver identity |
| 💰 **Execution Budgets** | Per-run token, cost, time, and tool-call limits with automatic escalation on breach |
| 🔒 **Policy Packs** | Pluggable compliance frameworks (PCI, GDPR, SOX) evaluated per action |
| 📋 **Immutable Audit Ledger** | Every decision fully reconstructable — plan → contract → policy → risk → budget → approval → execution → outcome |
| 🚀 **Multi-Domain** | Same core powers Infra Incident Commander and Payments Incident Commander |

---

## Production Capabilities

| Concern | Implementation |
|---------|---------------|
| **Durable state** | LangGraph `AsyncPostgresSaver` checkpointer — workflows survive restarts |
| **Durable queue** | Arq worker on Redis — API enqueues, workers execute (scale horizontally) |
| **Real-time** | Redis Streams event bus → SSE (shared across API + worker replicas) |
| **AuthN** | JWT (PyJWT) login, bcrypt password hashing |
| **AuthZ (RBAC)** | Ordered roles `viewer < operator < approver < admin`, enforced per route |
| **Governed approvals** | Approver identity captured into every audit event |
| **Real execution** | Kubernetes driver (rolling restart / scale / rollback) behind the MCP boundary; mock default |
| **Persistence** | SQLAlchemy (Postgres/SQLite) + Alembic migrations |
| **Hardening** | Real `/ready` (DB+Redis+Neo4j checks), restricted CORS, rate limiting, Prometheus `/metrics` |
| **Auditability** | Full decision trail persisted to Postgres, queryable per incident |
| **React Control Plane** | Glassmorphic dark-mode UI with real-time dashboards, incident viewer, contract editor |

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **AI/LLM** | LangGraph, LangChain, Claude/GPT/Gemini, LangSmith |
| **Knowledge** | ChromaDB (vector), Neo4j (graph), Hybrid RAG |
| **Backend** | Python 3.12, FastAPI, Arq, SQLAlchemy, Alembic |
| **Frontend** | React 19, TypeScript, Vite, Recharts, Lucide Icons, Vanilla CSS |
| **Infrastructure** | Docker Compose, PostgreSQL, Redis, Neo4j |
| **Security** | JWT, RBAC, bcrypt, rate limiting, CORS enforcement |
| **CI/CD** | GitHub Actions (test + build) |

---

## Quick Start

### Local (no Docker)

```bash
pip install -e ".[dev]"
cp .env.example .env            # APP_ENV=local; set OPENAI_API_KEY
uvicorn apps.api.main:app --reload
```

### Production Stack (Docker)

```bash
export JWT_SECRET=$(openssl rand -hex 32)
export BOOTSTRAP_ADMIN_PASSWORD='choose-a-strong-one'
docker compose up --build
```

Brings up **Postgres + Redis + Neo4j + API + Worker**. The API runs on http://localhost:8000.

Start the React UI separately:
```bash
cd apps/ui && npm install && npm run dev
```
Open http://localhost:5173 for the control plane.

---

## RBAC Model

| Role | Capabilities |
|------|-------------|
| `viewer` | Read dashboards, incidents, contracts, knowledge, audit |
| `operator` | + submit incidents |
| `approver` | + approve / reject remediation plans |
| `admin` | + manage users |

---

## API Surface

| Method | Path | Min Role |
|--------|------|----------|
| `POST` | `/api/auth/login` · `GET /api/auth/me` | public / any |
| `GET/POST` | `/api/auth/users` | admin |
| `GET` | `/api/incidents` · `/api/incidents/{id}` · `/…/audit` | viewer |
| `GET` | `/api/incidents/{id}/events` (SSE) | viewer |
| `POST` | `/api/incidents` | operator |
| `GET` | `/api/approvals/pending` · `/api/approvals/{id}` | viewer |
| `POST` | `/api/approvals/{id}` | approver |
| `GET` | `/api/contracts` · `/api/knowledge` | viewer |
| `GET` | `/health` · `/ready` · `/metrics` | public |

---

## Testing

```bash
# All 38 tests — unit + integration + workflow (no external services needed)
pytest

# Real end-to-end in Docker stack (Claude + RAG + Neo4j + workers)
python test.py
```

---

## Repository Structure

```
gaap/
├── core/                     # Reusable, domain-agnostic platform
│   ├── orchestration/        # LangGraph runtime, state machine, routing
│   ├── contracts/            # Contract engine + adaptive contracts
│   ├── guardrails/           # Deterministic enforcement + risk scoring
│   ├── agents/               # Multi-agent roles (Planner, Policy, Investigation, Summary)
│   ├── execution/            # MCP runtime, tool registry, drivers
│   ├── knowledge/            # RAG + Neo4j graph + vector ingestion
│   ├── budget/               # Token/cost/time/call budgets
│   ├── events/               # Redis Streams event bus
│   └── persistence/          # SQLAlchemy + audit ledger
├── apps/
│   ├── api/                  # FastAPI gateway (auth, RBAC, routes)
│   ├── worker/               # Arq worker (runs orchestration)
│   └── ui/                   # React 19 control plane (Vite + TypeScript)
├── examples/                 # Domain showcases + reference drivers
│   ├── incident_commander/   #   Kubernetes driver
│   ├── payments_commander/   #   Payments-domain driver
│   └── host_commander/       #   Linux/Windows/batch/SaaS reference driver
├── knowledge/                # Runbooks, architecture, contracts, topology.json (ingested into RAG)
├── tests/                    # 38 tests (unit + API + workflow)
├── docs/                     # Design documents
├── .github/workflows/        # CI pipeline
└── docker-compose.yml        # Full stack: Postgres + Redis + Neo4j + API + Worker
```

---

## Adopting This Platform

New to the project and want to run it against your own services?
**[📘 Adoption Guide →](docs/ADOPTION.md)** — a friendly, non-code walkthrough:
onboard a service with four config files (contract, runbooks, adaptive rules,
topology), pick your AI models and execution backend, and roll out safely.

## Design Documents

- [01 — Vision & Requirements](docs/01-vision-and-requirements.md)
- [02 — Architecture](docs/02-architecture.md)
- [03 — Domain Model](docs/03-domain-model.md)
- [04 — Roadmap](docs/04-roadmap.md)
- [Adoption Guide](docs/ADOPTION.md)

---

**Built by [Santhosh Kumar Nalla](https://linkedin.com/in/techiesanthoshnalla)** — Demonstrating production-grade AI governance: stateful LangGraph workflows with durable checkpointing, machine-enforced guardrails over LLM output, governed human-in-the-loop with audited approver identity, real MCP→Kubernetes execution boundary, JWT/RBAC security, hybrid RAG + knowledge graph, Redis-backed real-time streaming, and a full React operations control plane.
