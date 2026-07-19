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

## Interview preparation (learn the stack from this repo)
| Guide | Covers |
|---|---|
| [Interview — AI Stack](interview-ai-stack.md) | LangGraph, reducers/checkpointers, multi-agent, RAG, MCP, the governance pipeline (adaptive contracts, policy, risk-v2, budgets, guardrails), trust, saga compensation, production concerns — each with code references + Q&A |
| [Interview — React & Frontend](interview-react.md) | React 19, Vite, TS, react-router, Recharts, CSS design tokens, hooks — plus **how to wire the UI to the backend** (fetch, SSE, JWT) with Q&A |

## Where we are today (honest baseline)
A **production-grade vertical slice** already exists and runs: contract engine + deterministic guardrails, risk evaluation, human-in-the-loop, MCP execution boundary (mock **+ real Kubernetes**), Postgres-durable state, JWT+RBAC auth, Arq/Redis queue + worker, Redis-Streams real-time events, audit ledger, control-plane UI, Docker Compose stack, tests.

It is currently **one domain** (infrastructure Incident Commander). The program generalizes it into the reusable **core** and adds the missing platform engines and a **Payments** flagship. See [04 — Roadmap](04-roadmap.md) for the exact gap-to-plan mapping.
