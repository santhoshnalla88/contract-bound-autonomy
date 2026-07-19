# Interview Guide — AI Stack (grounded in this codebase)

A deep, interview-ready walkthrough of the AI engineering in GAAP. Every concept is tied to a **real file** you can open and explain. Structure per topic: **What it is → How we use it → Why it's designed this way → Interview Q&A**.

---

## 0. The 60-second pitch (memorize this)
> "GAAP is a **governed autonomous agent platform**. An LLM *plans*, but it can never *act* directly — every proposed action is normalized and passed through a deterministic **governance pipeline** (contract → semantic policy → risk → budget → guardrails) before a controlled **MCP execution boundary** touches infrastructure. The whole thing is a **LangGraph state machine** with retries, human-in-the-loop approval via `interrupt()`, saga compensation on failure, and a full audit trail. Deterministic rules always beat the LLM."

The one sentence that impresses: **"The LLM proposes; deterministic code disposes."**

---

## 1. LangGraph — stateful agent orchestration
**Files:** `core/orchestration/{builder,nodes,routing,state}.py`

### What it is
LangGraph models an agent workflow as a **directed graph of nodes** over a shared, typed **state**. Unlike a linear chain, it supports branching, loops (retries), and **durable pause/resume** (human-in-the-loop) via checkpointers.

### How we use it
- **State** (`state.py`) is a `TypedDict(total=False)` with **reducer annotations**:
  ```python
  retrieved_documents: Annotated[list, operator.add]   # append across nodes
  audit_trail:        Annotated[list, operator.add]    # append-only ledger
  risk_level:         str                               # last-write-wins (scalar)
  ```
  **Why this matters (key interview point):** each node returns a *partial dict*. For a plain key, the new value *overwrites*; for an `Annotated[list, operator.add]` key, LangGraph **reduces** (concatenates) the returned list into the channel. This is how the audit trail accumulates across 14 nodes without any node mutating shared state. **Nodes never mutate state in place** — they return updates. Returning a key that isn't a declared channel is silently dropped (a bug we fixed: `executive_summary`/`compensation_history` were missing from the schema).
- **Graph assembly** (`builder.py`): `StateGraph(OrchestratorState)`, `add_node`, `add_edge`, `add_conditional_edges`. The graph is a **process-level singleton** compiled once with a **checkpointer** (`build_graph(checkpointer=...)`) — critical so all callers share one state store.
- **Conditional routing** (`routing.py`): pure functions `state -> Literal[...]` decide the next node, e.g. `route_after_guardrail → "approved" | "rejected"`.
- **The loop:** `plan → guardrails → (rejected) → increment_retry → (retry) → plan` up to a max, then `escalate`. This is the **Plan → Execute → Observe → Replan** pattern.

### Why designed this way
- **Determinism & auditability:** the control flow is explicit graph edges, not the LLM deciding what to do next. You can prove which path executed.
- **Durability:** the checkpointer persists state after every node, so an `interrupt()` (approval) can pause for hours/days and resume in a *different process* (our Arq worker).

### Interview Q&A
- **Q: Chain vs. graph — why LangGraph over a LangChain chain?**
  A: Chains are linear/DAG and stateless between runs; we need cycles (retry), conditional branching, and **interruptible, checkpointed** execution for human approval. LangGraph gives durable state + resumability.
- **Q: How does human-in-the-loop actually pause?**
  A: `interrupt(payload)` in `request_human_approval` raises a special signal; LangGraph checkpoints the state and returns control. The API later calls `graph.ainvoke(Command(resume={"decision","actor"}), config)`; execution resumes *inside the same node* right after `interrupt()`, receiving the resume value. (`nodes.py:request_human_approval`)
- **Q: What are reducers and why annotate `operator.add`?**
  A: A reducer merges a node's partial update into a channel. `operator.add` on a list = append semantics so parallel/sequential updates accumulate instead of overwrite. Essential for append-only logs (audit, execution history).
- **Q: Why a singleton graph + shared checkpointer?**
  A: HITL resume and state inspection (`aget_state`) must hit the *same* state store the run wrote to. Different checkpointer instances = lost state. In prod the checkpointer is Postgres (`AsyncPostgresSaver`) so API and worker processes share it.

---

## 2. Multi-agent design
**Files:** `core/agents/{planner,investigation,policy,summary}.py`

### What it is
Specialized LLM "roles," each with a narrow responsibility and a typed I/O contract, composed by the orchestration graph (the graph is the "manager").

### How we use it
| Agent | Node | Job | Output |
|---|---|---|---|
| **InvestigationAgent** | `retrieve_knowledge` | RAG over runbooks/incidents | list of docs |
| **PlannerAgent** | `plan_remediation` | propose a structured plan | `RemediationPlan` (Pydantic) |
| **PolicyAgent** | `evaluate_semantics` | LLM compliance check | `(is_compliant, reasoning)` |
| **SummaryAgent** | `finalize` | post-incident exec summary | text |

**Key safety rule (say this):** the PolicyAgent can only *ADD* restrictions — it can reject, but it can **never override** a deterministic approval. Deterministic guardrails run first and always win.

### Interview Q&A
- **Q: How do you get structured output from an LLM?**
  A: `ChatOpenAI(...).with_structured_output(RemediationPlan)` — LangChain binds the Pydantic schema as a tool/JSON-schema so the model returns validated structured data, not free text. If it returns garbage, Pydantic validation fails and we fall into the retry/escalate path. (`agents/planner.py`)
- **Q: Manager/orchestrator pattern?**
  A: We use a *graph-as-manager* rather than an LLM manager — cheaper, deterministic, auditable. The graph routes between role agents based on governance results.

---

## 3. RAG (Retrieval-Augmented Generation)
**Files:** `core/knowledge/{retriever,ingestion,metadata}.py`, `core/agents/investigation.py`

### What it is
Retrieve relevant org knowledge (runbooks, past incidents, architecture) from a vector DB and inject it into the planner's context so plans are grounded in institutional knowledge, not just the model's priors.

### How we use it
- **Ingestion:** markdown → `RecursiveCharacterTextSplitter` chunks → embed → ChromaDB, with **content-hash IDs** for idempotency (re-ingest doesn't duplicate). Metadata (service, doc type, **trust level**) is inferred from the directory path.
- **Retrieval:** semantic query + **metadata filtering** (`where` clause on service/environment), cosine distance → relevance score.
- **Trust levels** (`organization-approved` / `team-contributed` / `auto-generated`) are attached to each doc and shown to the planner — but are **advisory only**: retrieved text is **untrusted data** and can never override a contract. (This is your answer to prompt-injection questions.)

### Interview Q&A
- **Q: Why not put contracts in the vector store too?**
  A: Contracts are **authority**, not context. They're loaded **deterministically** by exact `(service, environment)` match (`ContractLoader`) to avoid *semantic drift* — you never want fuzzy retrieval deciding what an agent is allowed to do.
- **Q: How do you handle prompt injection from retrieved docs?**
  A: Separation of powers: retrieved text only influences the *proposed plan*; the plan is then normalized to enum actions and passed through deterministic guardrails + contract. A malicious runbook saying "delete the database" can't do anything because `drop_database` isn't in the contract's `allowed_actions`.
- **Q: Chunking strategy?**
  A: Recursive splitter on markdown separators (`\n## `, `\n\n`, …), ~1000 chars with 200 overlap to preserve context across boundaries.

---

## 4. MCP execution boundary + pluggable drivers
**Files:** `core/execution/{client,server,tools}.py`, `core/execution/drivers/{base,mock}.py`, `examples/*/drivers/*.py`

### What it is
**MCP (Model Context Protocol)** = a controlled boundary between the agent and real systems. The LLM never calls infra APIs; it emits a plan, and a client dispatches *allowlisted* actions to a **driver**.

### How we use it
- `ExecutionDriver` is a **Protocol** (`drivers/base.py`): `restart_pods`, `scale_deployment`, `rollback_deployment`, `get_metrics`, … Implementations: `MockDriver` (simulated cluster), `KubernetesDriver` (real k8s rolling restart/scale/rollout-undo), `PaymentsDriver` (synthetic payments). **Same core, swappable backend** — the definition of a platform.
- `MCPClient` enforces an **allowlist** (defense in depth on top of contract), wraps results in `ExecutionResult`, and is **per-incident** (`get_mcp_client(incident_id)`) so execute + postcondition observe the same simulated cluster.

### Interview Q&A
- **Q: Why a driver Protocol?**
  A: Dependency inversion (the "D" in SOLID). Core depends on the *interface*, domains provide implementations. Adding a domain = new driver, **zero core changes**.
- **Q: Two layers of allowlist (contract + client) — redundant?**
  A: Defense in depth. Contract is policy (per-service, versioned); the client allowlist is a hard code-level backstop so even a bug upstream can't execute an unlisted action.

---

## 5. The governance pipeline (the "beyond the paper" part)
This is the differentiator. Walk it as a **pipeline**, in order:

### 5a. Contract Engine + **Adaptive Contracts**
**Files:** `core/contracts/{contracts,adaptive}.py`
- A **contract** = machine-readable authority: `allowed_actions`, `forbidden_actions`, `limits`, `availability_constraints`, `approval_requirements`, `postconditions`. Versioned, loaded deterministically.
- **Adaptive** (`AdaptiveContractResolver`): rules `when(context) → mutate(contract)` produce an **EffectiveContract** per incident. **Safety invariant:** mutations may only **narrow** (never elevate above the base ceiling) — `min(override, base_limit)`. *We proved this live:* a CRITICAL incident dropped `scale_deployment` and lowered `max_pod_restarts` 2→1.
- **Interview line:** "Static contracts are one-size-fits-all; adaptive contracts make autonomy *context-sensitive* — tighter under CRITICAL severity or low agent trust — while a hard ceiling guarantees they can only ever restrict, never expand, permissions."

### 5b. **Semantic Policy / Compliance**
**Files:** `core/agents/policy.py` (LLM), `core/compliance/{evaluator,models.py}` (deterministic packs)
- Deterministic `PolicyPack`s (PCI/GDPR/SOX-style rules) + an LLM `PolicyAgent` for nuanced checks. Can only add rejections.

### 5c. **Risk Engine v2 (numeric score)**
**Files:** `core/guardrails/risk.py`
- Produces a **0–100 score** from severity, action types, blast radius, and **agent trust** → band (LOW/…/CRITICAL) → decision (auto-execute / require approval / escalate). Signature: `evaluate(plan, incident, contract, trust_score) -> (score, level, needs_approval)`.
- **Interview line:** "Risk is scored, not guessed — and trust feeds it, so a historically unreliable agent needs approval for actions a trusted one could auto-execute."

### 5d. **Execution Budget Engine**
**Files:** `core/budget/{accountant,models.py}`
- Per-run ledger for token/cost/time/tool-call budgets; `record_consumption` raises `BudgetExceededError` when a limit would be breached → block + escalate. Prevents runaway agents (cost & blast-radius control).

### 5e. **Deterministic Guardrails** (the final hard gate)
**Files:** `core/guardrails/{engine,validators.py}`
- Strict priority order: **forbidden → allowlist → limits → availability**. First failure rejects. Pure functions, fully unit-tested, no LLM. *This* is what makes the system safe.

### Interview Q&A
- **Q: Order of the pipeline — why?**
  A: Cheapest/hardest-fail first isn't the rule here; *authority* first. Contract (what's allowed) → policy (compliance) → risk (how dangerous) → budget (can we afford it) → guardrails (final deterministic veto). Deterministic checks bookend the LLM so it can never bypass them.
- **Q: What stops the LLM from just... doing the bad thing?**
  A: It has no execution capability. It only produces a `RemediationPlan`; that's normalized to enum `ActionType`s and must survive all five gates before the MCP client will dispatch it.

---

## 6. Trust / Reputation & Memory
**Files:** `core/trust/{manager,models.py}`, `core/memory/{store,models.py}`
- **Trust:** rolling per-agent scorecard (successes, failures, escalations, guardrail rejections) → a score that feeds Risk + Adaptive. Updated in `finalize`/`increment_retry`.
- **Memory:** short-term (per case) + long-term (per agent/domain) store; MVP is in-memory with naive recall, designed to swap to **pgvector** behind the same interface.
- **Interview line:** "Trust closes the loop — the platform *learns* which agents to grant more autonomy, governed by data, not vibes."

---

## 7. Saga compensation (deterministic recovery)
**File:** `core/orchestration/nodes.py:execute_actions`
- Actions execute sequentially; on a failure it **stops and compensates in reverse order** using each action's declared `compensation` (a rollback `NormalizedAction`). This is the **Saga pattern** for distributed side effects.
- **Interview line:** "Because real remediation has side effects, a failed step triggers compensating actions in LIFO order — like a database transaction rollback, but for infrastructure."

---

## 8. Production concerns (the senior-level signal)
**Files:** `apps/api/*`, `apps/worker/*`, `core/persistence/*`, `core/events/*`, `core/identity/*`
- **Durable state:** `AsyncPostgresSaver` checkpointer — workflows survive restarts.
- **Distributed execution:** API enqueues to **Arq/Redis**; a separate **worker** runs the graph; **Redis Streams** fan out real-time events → SSE. API and worker share Postgres state — verified cross-process.
- **AuthN/Z:** JWT + bcrypt + **RBAC** (`viewer < operator < approver < admin`); approver identity captured into every audit event.
- **Hardening:** real `/ready` (checks DB+Redis), rate limiting, Prometheus `/metrics`, restricted CORS.

### Interview Q&A
- **Q: How does approval survive a deploy/restart?**
  A: State is checkpointed to Postgres at the `interrupt`. Any worker can resume from `Command(resume=...)` — nothing is held in memory.
- **Q: How do you scale?**
  A: Stateless API + N stateless workers behind one Postgres (state/audit) and Redis (queue/events). Workers pull jobs; events fan out to all API replicas via Redis Streams.

---

## 9. Likely "gotcha" questions — crisp answers
- **"Is the LLM in the trust boundary?"** No. LLM output is untrusted; it only proposes. Deterministic governance is the trust boundary.
- **"What if the model hallucinates an action?"** Normalization maps to a fixed `ActionType` enum; unknown actions fail normalization → rejected. Even valid-but-disallowed actions die at the contract/guardrail gate.
- **"Cost control?"** Budget engine (tokens/cost/time/calls) + temperature 0.1 + structured output (fewer retries).
- **"How is it observable?"** Every decision is an `AuditEvent` (actor, contract version, outcome) persisted to Postgres; LangSmith traces LLM calls; Prometheus for RED metrics; SSE streams a live timeline.
- **"Weakest part today?"** Honest answer: RAG isn't auto-ingested in the default run (falls back gracefully); memory/trust are in-memory MVPs (designed for pgvector/DB); the React UI is a visual shell not yet wired to the API. All are behind interfaces, so they're swap-ins, not rewrites.

---

## 10. Glossary (rapid fire)
**LangGraph** stateful agent graph · **Reducer** channel merge fn · **Checkpointer** durable state store · **interrupt()** HITL pause · **MCP** controlled execution boundary · **Structured output** Pydantic-validated LLM response · **Guardrail** deterministic veto · **Adaptive contract** context-mutated permissions · **Saga** compensating rollback · **RAG** retrieval-grounded generation · **Trust score** learned autonomy modifier.
