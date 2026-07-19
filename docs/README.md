# GAAP — Governed Autonomous AI Platform · Design Documents

> A reusable runtime for **governed autonomous AI agents**: agents reason freely but can only act inside explicit, machine-enforced **contracts** — with risk scoring, policy/compliance checks, execution budgets, human approval, full audit, and observability. Domain-agnostic core; multiple domain showcases on top.

**Inspiration & identity.** The architecture is inspired by *Contract-Bound Autonomy* (Agentic AI in Software Systems, 2026). GAAP presents its own identity and extends the idea with: **Adaptive Contracts**, an **Execution Budget Engine**, an **Agent Trust/Reputation model**, **Policy-as-Code**, and **deterministic recovery/compensation** — the things that make it a production platform rather than a paper implementation.

## This is a program, not a single build
Per the source vision, we work **design-first**, then implement **one module at a time**. These docs are Phase 1–4 deliverables.

| Doc | Phase | Contents |
|---|---|---|
| [01 — Vision & Requirements](01-vision-and-requirements.md) | 1–2 | Problem, market, goals, functional + non-functional requirements, success criteria |
| [02 — Architecture](02-architecture.md) | 3 | C4 diagrams, key sequences, bounded contexts, module catalog, tech decisions |
| [03 — Domain Model](03-domain-model.md) | 4 | DDD: entities, aggregates, value objects, commands, events, policies |
| [04 — Roadmap](04-roadmap.md) | 9 | Phased milestones, what already exists, sprint plan, prioritization |

## Where we are today (verified, real stack)
A **working platform** that runs end-to-end on real infrastructure — verified with live API keys:

- **Real LLMs (dual-provider):** Claude Opus 4.8 (planning) + Claude Haiku 4.5 (compliance) + Gemini Flash (summaries), behind a provider-agnostic factory (`core/llm/factory.py`).
- **Hybrid knowledge:** ChromaDB vector store (local embeddings, auto-ingested at startup) **+ Neo4j** service-dependency graph (blast-radius enrichment).
- **Governance:** adaptive contracts, deterministic guardrails, semantic policy, numeric risk, execution budgets.
- **Orchestration:** LangGraph (14 nodes, retry loop, `interrupt()` HITL), durable **Postgres checkpointer**, **Arq/Redis** queue + separate worker, **Redis-Streams** SSE.
- **Security & ops:** JWT + RBAC, audit ledger, rate limiting, `/metrics`, `/ready` (checks DB/Redis), **React 19** control plane.
- **Full environment:** `docker compose up` brings up **postgres + redis + neo4j + api + worker**; 33 tests pass.

**Verified end-to-end:** submit incident → Claude plans (grounded in runbook + graph) → guardrails → semantic policy → risk HIGH → human approval → execute → postconditions pass → **SUCCESS**, with a complete audit trail.
