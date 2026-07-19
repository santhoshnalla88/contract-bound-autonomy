# 02 — Architecture

> **Author:** Santhosh Kumar Nalla | [LinkedIn](https://linkedin.com/in/techiesanthoshnalla)

Diagrams use Mermaid (renders on GitHub). Legend: **[✓ built]** exists today, **[~ partial]**, **[▢ planned]**.

## 1. C4 — Level 1: System Context

```mermaid
graph TB
    operator([Operator / Approver])
    admin([Platform Admin])
    extsys[/"Managed systems<br/>(K8s, payments sim, logs)"/]
    llm[/"LLM provider"/]

    subgraph GAAP["GAAP — Governed Autonomous AI Platform"]
      platform["Governed agent runtime<br/>+ domain showcases"]
    end

    operator -->|submits cases, approves| platform
    admin -->|manages contracts, users, policies| platform
    platform -->|governed actions| extsys
    platform -->|reasoning / planning| llm
```

## 2. C4 — Level 2: Containers

```mermaid
graph TB
    ui["Control Plane UI<br/>(React SPA) [~]"]
    api["API Gateway<br/>FastAPI · auth · RBAC · rate limit [✓]"]
    worker["Agent Worker(s)<br/>Arq · runs orchestration [✓]"]
    pg[("Postgres<br/>state · audit · users [✓]")]
    redis[("Redis<br/>queue · events · cache [✓]")]
    vec[("Vector store<br/>Chroma→pgvector [~]")]
    obs["Observability<br/>LangSmith · OTel · Prometheus [~]"]

    ui -->|REST + SSE| api
    api -->|enqueue| redis
    worker -->|consume| redis
    api -->|read state/audit| pg
    worker -->|checkpoint + audit| pg
    worker -->|retrieve| vec
    worker -->|actions via MCP| ext[/"Execution drivers"/]
    api & worker --> obs
```

## 3. C4 — Level 3: Components of the Agent Worker (the platform core)

```mermaid
graph TB
    orch["Orchestration Runtime<br/>LangGraph state machine [✓]"]

    subgraph gov["Governance"]
      contract["Contract Engine [✓]"]
      adaptive["Adaptive Contract Engine [▢]"]
      policy["Policy / Compliance Engine [▢]"]
      risk["Risk Engine [~]"]
      budget["Execution Budget Engine [▢]"]
      guard["Guardrail Enforcer [✓]"]
    end

    subgraph agents["Multi-Agent Layer"]
      mgr["Manager [▢]"]; plan["Planner [✓]"]; invest["Investigation [▢]"]
      know["Knowledge [~]"]; riskA["Risk [~]"]; polA["Policy [▢]"]
      exe["Execution [✓]"]; auditA["Audit [✓]"]; summ["Summary [▢]"]
    end

    subgraph exec["Execution & Recovery"]
      mcp["MCP Runtime + Tool Registry [~]"]
      drivers["Drivers: mock · k8s · payments-sim [~]"]
      comp["Recovery / Compensation [▢]"]
    end

    subgraph knowledge["Knowledge"]
      rag["RAG Service [~]"]; mem["Memory (short/long) [▢]"]
    end

    approval["Approval Workflow (HITL) [✓]"]
    audit["Audit Ledger [✓]"]
    trust["Trust / Reputation [▢]"]

    orch --> agents
    plan --> contract --> adaptive --> policy --> risk --> budget --> guard
    guard -->|approved| approval --> mcp --> drivers
    mcp --> comp
    agents --> rag & mem
    orch --> audit
    risk --> trust
```

## 4. Key sequence — governed action lifecycle

```mermaid
sequenceDiagram
    participant U as Operator
    participant API
    participant W as Worker (LangGraph)
    participant K as Knowledge (RAG/Mem)
    participant G as Governance (contract→policy→risk→budget)
    participant H as Human Approval
    participant X as MCP Driver
    participant A as Audit Ledger

    U->>API: submit case
    API->>W: enqueue
    W->>K: retrieve context
    W->>W: Planner proposes plan (structured)
    W->>G: evaluate plan
    G-->>W: allow / approve / block / escalate (+ reasons)
    alt requires approval
        W->>H: pause (interrupt) + context
        H-->>W: APPROVED/REJECTED (+identity)
    end
    W->>X: execute permitted actions
    X-->>W: results
    W->>W: validate postconditions (Observe→Replan)
    W->>A: persist full decision trace
    W-->>API: final outcome (SUCCESS/ESCALATED/DENIED)
```

## 5. Bounded contexts (DDD)

```mermaid
graph LR
    subgraph Governance
      C[Contracts]; AP[Adaptive]; PO[Policy]; RI[Risk]; BU[Budget]
    end
    subgraph Orchestration
      AG[Agents]; PL[Planning]; EX[Execution]; RC[Recovery]
    end
    subgraph Knowledge
      RG[RAG]; ME[Memory]
    end
    Approval; Audit[Audit & Observability]; Identity[Identity & Access]
    Orchestration --> Governance
    Orchestration --> Knowledge
    Orchestration --> Approval
    Orchestration --> Audit
    Identity --> Approval
```

Each context owns its models and exposes an interface; the **Orchestration** context composes them. Domains (payments, infra) live **outside** core and depend only on interfaces.

## 6. Target repository structure

```
gaap/
├── core/                     # reusable, domain-agnostic platform
│   ├── orchestration/        # LangGraph runtime, state, routing [✓ from current app]
│   ├── contracts/            # contract engine + loader [✓]  + adaptive engine [▢]
│   ├── policy/               # policy/compliance packs (PCI/GDPR/SOX) [▢]
│   ├── risk/                 # scoring model + decision matrix [~]
│   ├── budget/               # token/cost/time/call budgets [▢]
│   ├── guardrails/           # deterministic enforcement [✓]
│   ├── agents/               # agent runtime + multi-agent roles [~]
│   ├── execution/            # MCP runtime, tool registry, drivers, compensation [~]
│   ├── knowledge/            # RAG + memory [~]
│   ├── approval/             # HITL workflow [✓]
│   ├── audit/                # audit ledger [✓]
│   ├── trust/                # reputation model [▢]
│   ├── observability/        # LangSmith + OTel + metrics [~]
│   ├── events/               # event bus (Redis Streams) [✓]
│   └── identity/             # auth + RBAC [✓]
├── examples/
│   ├── incident-commander/   # infra/K8s showcase [✓ exists today]
│   └── payments-ops/         # FLAGSHIP: Payment Incident Commander [▢]
├── apps/
│   ├── api/                  # FastAPI gateway [✓]
│   ├── worker/               # Arq worker [✓]
│   └── ui/                   # control plane [~]
├── deploy/                   # docker-compose [✓], Terraform [▢], k8s manifests [▢], CI [▢]
└── docs/                     # these design docs [✓]
```

## 7. Technology decisions (and deviations from the vision doc)
| Area | Choice | Note |
|---|---|---|
| Orchestration | LangGraph | matches doc |
| Queue | **Arq** (Redis) | doc said Celery; Arq is async-native, lighter — equivalent role |
| Events | **Redis Streams** | doc said Kafka; Streams fits current scale, Kafka is a later swap behind the `events` interface |
| Vector store | Chroma → **pgvector** | migrate to pgvector to consolidate on Postgres (doc's choice) |
| Tracing | LangSmith + **OpenTelemetry** | OTel to be added (currently Prometheus only) |
| Frontend | **React/TS/Vanilla CSS** target | SPA served by FastAPI today; React Vite is the production target |
| Deploy | docker-compose → **Terraform + k8s + GitHub Actions** | local now; IaC + CI planned |

All deviations sit behind interfaces so they can be swapped without touching domain code.
