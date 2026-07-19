# 01 — Vision & Requirements

> **Author:** Santhosh Kumar Nalla | [LinkedIn](https://linkedin.com/in/techiesanthoshnalla)

## 1. Problem statement
Enterprises want to hand real operational work to AI agents, but cannot accept **unbounded autonomy** in regulated, high-blast-radius environments (payments, infra, fraud). Today's agent stacks optimize for capability, not **governance**: there is no standard way to say *"this agent may do X, never Y, only up to this risk/cost, and must ask a human for Z — and prove it afterwards."*

## 2. Vision
**GAAP** is a domain-agnostic platform for **governed autonomous agents**. Every agent action passes through a runtime **contract** (permissions, limits, compliance, budgets, approval rules) enforced deterministically *before* execution, with everything traced in an immutable audit ledger. Teams get autonomy where it's safe and control where it isn't — configurable per context.

## 3. Market need (why now)
- Agentic AI is moving from demos to operations; **AI governance/safety** is the gating concern for regulated adoption.
- Buyers (fintech, cloud, enterprise platform teams) evaluate **AI system design** — safety, observability, governability — not prompt engineering.
- No dominant open standard for **policy-bound agent execution** yet exists.

## 4. Product goals
1. **Governed by default** — no action executes without passing contract + policy + risk + budget checks.
2. **Domain-agnostic core, pluggable showcases** — same runtime powers payments, infra, fraud, release management.
3. **Adaptive** — contracts tighten/loosen with runtime context (amount, severity, trust).
4. **Explainable & auditable** — every decision reconstructable end-to-end.
5. **Production-grade** — durable, secure, observable, horizontally scalable.
6. **Extensible** — add an agent/domain without changing the platform.

## 5. Functional requirements
| # | Requirement |
|---|---|
| FR-1 | Define, version, and dynamically load **contracts** per agent/context |
| FR-2 | **Adaptive contracts**: rules that recompute permissions/limits from runtime context |
| FR-3 | **Deterministic guardrail** enforcement (allow/forbid/limits/availability) that the LLM cannot override |
| FR-4 | **Policy engine**: pluggable compliance packs (PCI, GDPR, SOX, custom) evaluated per action |
| FR-5 | **Risk engine**: numeric risk score → allow / approve / block / escalate |
| FR-6 | **Execution budgets**: per-run limits on tokens, cost, wall-clock, API/tool calls |
| FR-7 | **Multi-agent orchestration**: Manager, Planner, Investigation, Knowledge, Risk, Policy, Execution, Audit, Summary roles |
| FR-8 | **Plan → Execute → Observe → Replan** loop with retries and escalation |
| FR-9 | **Human-in-the-loop** approval that pauses execution until a decision is recorded (with approver identity) |
| FR-10 | **MCP execution boundary** with pluggable drivers (mock, Kubernetes, payments-sim, …) |
| FR-11 | **RAG** knowledge retrieval + **agent memory** (short- and long-term) |
| FR-12 | **Audit ledger**: immutable, queryable record of every decision and action |
| FR-13 | **Trust/reputation**: adjust an agent's autonomy from historical performance |
| FR-14 | **Recovery/compensation**: deterministic rollback/compensating actions on failure |
| FR-15 | **AuthN/AuthZ (RBAC)** on every operation; approvals gated by role |
| FR-16 | **Observability**: traces, metrics, decision timeline, cost/latency |
| FR-17 | **Notifications** to operators on approval-required / escalation |
| FR-18 | **Showcase apps**: Payments Incident Commander (flagship) + Infra Incident Commander |

## 6. Non-functional requirements / quality attributes
| Attribute | Target |
|---|---|
| Safety | No side effect without passing all governance gates; deterministic rules always win over the LLM |
| Durability | Workflow + audit survive process restarts (Postgres checkpointer + ledger) |
| Scalability | Stateless API + horizontally scalable workers; events fan out across replicas |
| Security | JWT + RBAC, least privilege, secrets from env/secret-manager, no PII in logs |
| Observability | Every decision traceable (LangSmith + OpenTelemetry); RED metrics; audit query |
| Extensibility | New agent/domain/policy/driver added via interfaces, no core changes |
| Testability | Deterministic engines unit-tested; governance decisions reproducible |
| Compliance | Synthetic data only; PCI/GDPR/SOX modelled as policy packs, not real systems |

## 7. Success criteria
- A new domain showcase can be added **without modifying `core/`**.
- A single incident produces a **complete, queryable decision trace** (plan → contract → policy → risk → budget → approval → execution → postconditions → outcome).
- **Adaptive** behavior demonstrable: same agent, different context → different autonomy (e.g. $50 refund auto-recommend vs $10k refund requires approval).
- Full stack runs via `docker compose up` and passes CI (tests + lint + type-check).
- Reads as a **platform** to a senior reviewer, with design docs, diagrams, and a deployed demo.

## 8. Explicit non-goals
- Not a general chatbot / RAG Q&A.
- No proprietary or real production data — **synthetic data and public standards only**.
- Not tied to any employer's internal systems or APIs.
