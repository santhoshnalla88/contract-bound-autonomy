# 04 — Roadmap

> **Author:** Santhosh Kumar Nalla | [LinkedIn](https://linkedin.com/in/techiesanthoshnalla)

Design-first, then **one module at a time**. Each module ships with tests, docs, and a demo. `[✓] done · [~] partial · [▢] not started`.

## Baseline — what already exists (the first vertical slice)
Contract engine + guardrails `[✓]`, risk (level-based) `[~]`, HITL approval `[✓]`, MCP boundary + **real k8s driver** `[✓]`, Postgres-durable state `[✓]`, JWT+RBAC `[✓]`, Arq/Redis queue + worker `[✓]`, Redis-Streams events + SSE `[✓]`, audit ledger `[✓]`, control-plane SPA `[~]`, docker-compose `[✓]`, 22 tests `[✓]`. Domain: **Infra Incident Commander** `[✓]`.

## Program phases

### Phase A — Platform foundation (design + restructure)
- A1 `[✓]` Design docs (this set).
- A2 `[▢]` Restructure repo into `core/` + `examples/` + `apps/` (move current app into `core/` and `examples/incident-commander/` behind interfaces). *No behavior change; tests stay green.*
- A3 `[▢]` Define the core interfaces (ports): `ContractResolver`, `PolicyEvaluator`, `RiskScorer`, `BudgetAccountant`, `ExecutionDriver`, `MemoryStore`, `AgentRole`.

### Phase B — Governance depth (the differentiators)
- B1 `[▢]` **Adaptive Contract Engine** — `AdaptiveRule` model + resolver → `EffectiveContract`; context predicates (amount, severity, trust). Demo: same agent, different context → different autonomy.
- B2 `[▢]` **Execution Budget Engine** — per-run token/cost/time/tool-call budgets; `BudgetAccountant` + ledger; block + escalate on breach.
- B3 `[▢]` **Policy/Compliance Engine** — pluggable `PolicyPack`s (PCI, GDPR, SOX, custom) as Policy-as-Code; evaluated per action; wire the existing `semantic_validator` in as the LLM-assisted policy checker (deterministic packs win).
- B4 `[▢]` **Risk Engine v2** — numeric score (0–100) from complexity/confidence/business-impact/cost/compliance/history; decision matrix → allow/approve/block/escalate.

### Phase C — Agent depth
- C1 `[▢]` **Multi-agent runtime** — Manager, Investigation, Knowledge, Policy, Summary roles as first-class agents with defined I/O contracts; wire into LangGraph.
- C2 `[▢]` **Memory** — short-term (per case) + long-term (per agent/domain) store (pgvector), with recall scope.
- C3 `[▢]` **Trust/Reputation** — rolling agent scorecard feeding Risk + Adaptive.
- C4 `[▢]` **Recovery/Compensation** — saga-style rollback via `RollbackStrategy` on failed executions.

### Phase D — Payments flagship
- D1 `[▢]` **Payments domain model** — synthetic transaction/merchant/settlement services; anomaly generator.
- D2 `[▢]` **Payment Incident Commander** example — detect anomaly → RAG runbooks → investigate → recommend → adaptive approval (e.g. refund>$500) → execute permitted → audit. Uses **only synthetic data**.
- D3 `[▢]` Second payments flow (chargeback or fraud investigation) to prove reuse of `core/`.

### Phase E — Observability & delivery
- E1 `[▢]` **OpenTelemetry** traces + decision timeline; keep LangSmith; Prometheus + Grafana dashboards.
- E2 `[?]` **React control plane** (replace SPA) - dashboards, contract editor (with approval + audit), decision-trace viewer, budgets, trust.
- E3 `[▢]` **Delivery** — GitHub Actions CI (test/lint/type/build), Terraform + k8s manifests, deployed demo.

## Prioritization (recommended order)
1. **A2–A3** (restructure + ports) — everything else plugs into these.
2. **B1 Adaptive Contracts** + **B2 Budgets** — the headline "beyond the paper" innovations; build on the existing contract engine.
3. **B4 Risk v2** + **B3 Policy packs** — completes the governance story.
4. **D1–D2 Payments flagship** — the resume differentiator; proves multi-domain.
5. **C1 Multi-agent** — depth once the vertical is generalized.
6. **E** observability/UI/deploy — polish for the deployed demo.

## Definition of done (per module)
Interface + implementation · unit tests · wired into a graph/demo · doc updated · runs in `docker compose` · no `core/` → domain imports.

## Milestones
- **M1**: Platform restructured; incident-commander runs on `core/` unchanged. (A)
- **M2**: Adaptive contracts + budgets live, demoed on incident-commander. (B1–B2)
- **M3**: Full governance (risk v2 + policy packs). (B3–B4)
- **M4**: Payments Incident Commander running on the same core. (D) `[✓]`
- **M5**: Multi-agent + memory + trust + compensation. (C) `[✓]`
- **M6**: OTel + Next.js UI + CI/IaC + deployed demo. (E) `[✓]`
