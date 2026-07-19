# What Is This Platform For? — A Detailed Use Case

> **In one line:** GAAP lets an AI agent *resolve production incidents on its own*
> — but only ever inside hard, machine-enforced boundaries you control, with a
> human pulled in exactly when (and only when) it matters, and a complete audit
> trail for everything.

This document walks through **one real incident, end to end**, so you can see
what the platform actually *does* and why each moving part exists. We use the
scenario that ships with the repo: connection-pool exhaustion in an
`inventory-service` during a flash sale. Everything below is grounded in the
files in `knowledge/` — the same runbook, contract, and topology the running
system reads.

---

## 1. The problem it solves

It's **2:47 AM**. A marketing flash sale just went live. The `inventory-service`
starts failing:

- Pods flip to `NotReady`, Kubernetes pulls them from rotation.
- HTTP 503s cross **5%** — an SLO breach.
- Logs fill with `HikariPool-1 - Connection is not available, request timed out`.
- **Checkout starts timing out** — because checkout depends on inventory. Every
  minute of this is lost revenue.

An alert fires. Now what? Historically you have three bad options:

| Option | What goes wrong |
|--------|-----------------|
| **Wake a human** | A sleepy on-call engineer reads a runbook at 3 AM under pressure. Mean-time-to-repair is 15–45 min. Mistakes happen. It doesn't scale to hundreds of services. |
| **A rigid automation script** | Fast, but brittle. It does *exactly* one thing. It can't tell "connection leak" from "traffic spike" (which need *different* fixes), and it has no judgment about blast radius or when to stop. |
| **An unconstrained AI agent** | Adaptable, but terrifying. What stops it from deleting a database, scaling to 500 pods, or taking down checkout while "fixing" inventory? Nothing. You can't put that in production. |

**GAAP is the fourth option:** an AI agent that reasons like the human *and* is
constrained like the script — with the adaptability of the model and the
guarantees of code. That combination is the entire point.

---

## 2. The scenario, step by step

Here's what happens the moment the incident is submitted (via an alert webhook,
the API, or the control-plane UI).

```
Incident ──▶ Investigate ──▶ Plan ──▶ ┌─ Contract ─ Adaptive ─ Policy ─ Risk ─ Budget ─┐──▶ Approve? ──▶ Execute ──▶ Verify ──▶ Done
  (symptoms)   (RAG+graph)   (LLM)    └──────────  deterministic governance  ──────────┘   (human)      (MCP)     (postconditions)
```

### Step 1 — Investigate: gather grounded context (not guesses)

Before the model proposes anything, the platform assembles the facts:

- **RAG (vector search over your runbooks).** It retrieves the actual
  *[Inventory Service — Connection Pool Exhaustion runbook](../knowledge/runbooks/inventory-service-connection-pool-runbook.md)* —
  the same document your SREs wrote. So the agent reasons from **your**
  operational knowledge, not the internet's average opinion.
- **GraphRAG (Neo4j dependency graph).** It queries the **blast radius** of
  `inventory-service` and learns that `checkout-service` (**CRITICAL**) and
  `api-gateway` depend on it. This is a question vector search *cannot* answer —
  "what else breaks if I touch this?"

The agent now knows: *this is a HikariCP exhaustion, the runbook says a rolling
restart clears leaked connections (and scaling helps if it's traffic), and a
critical checkout path is downstream, so I must preserve availability.*

### Step 2 — Plan: the AI proposes a remediation

The **Planner** (Claude Opus 4.8) drafts an ordered plan, grounded in the runbook
and the blast radius. For this incident it proposes, roughly:

1. `get_metrics` on inventory-service (confirm the diagnosis).
2. `restart_pods` — a **rolling** restart of unhealthy pods, with connection
   draining, to clear leaked connections.
3. If error rate stays high, `scale_deployment` to absorb traffic.

Crucially, the model can propose *anything*. What it proposes is just a
candidate. Nothing has touched production yet.

### Step 3 — Govern: the plan runs a gauntlet of deterministic gates

This is the heart of the platform. Every gate is **code, not a prompt** — the
model cannot talk its way past them.

**🛡️ Contract check** — the [operational contract](../knowledge/contracts/inventory-service-contract.json)
for `inventory-service` says:
- `allowed_actions`: `restart_pods`, `scale_deployment`, `rollback_deployment` ✅
- `forbidden_actions`: `delete_persistent_volume`, `drop_database`, `modify_production_secrets` ❌
- `limits`: max **2** pod restarts per incident, max **10** replicas
- `availability_constraints`: keep at least **2** replicas available
- `approval_requirements`: `rollback_deployment` → **always** needs a human

If the model had proposed `drop_database` (LLMs hallucinate), the contract
**rejects it deterministically** — it can never execute, full stop.

**🎚️ Adaptive rules** — context tightens the contract further. This incident is
trending **CRITICAL**, and the contract's adaptive rule
`restrict_scale_on_critical` says: *under CRITICAL severity, disable scaling and
lower max restarts to 1.* So the effective contract for *this* incident is
**stricter** than the baseline — exactly when you want less aggressive autonomy.

**📜 Policy check** — a second model (Claude Haiku 4.5) checks the plan against
policy-as-code (e.g. "restarts must drain active connections," compliance rules
like PCI/GDPR/SOX in regulated domains). In the shipped demo it correctly
*rejects* a restart that omits draining, and *passes* it on retry once draining
is added — a real governance loop, not a rubber stamp.

**📊 Risk score** — a numeric score based on action type, environment, and blast
radius. Restarting a service with a **CRITICAL** downstream dependent
(`checkout-service`) scores **HIGH**.

**💰 Budget** — has this incident already consumed too many actions / too much
token cost / too much time? If so, stop and escalate rather than thrash.

### Step 4 — Human-in-the-loop: approval, only when it matters

Because risk came back **HIGH**, the workflow **pauses** (LangGraph `interrupt()`)
and waits for a human **approver** to click approve/reject in the control plane.
Their identity is captured. A `restart_pods` on a low-risk dev service would have
sailed through with **no human** needed — the platform escalates *by exception*,
not for everything. This is the dial between "fully autonomous" and "supervised."

### Step 5 — Execute: through a controlled boundary, never directly

On approval, the action goes through the **MCP execution boundary** to a
**driver**. The LLM never touches infrastructure — it only ever emitted an
abstract `action + target + parameters`. The Kubernetes driver performs the real
rolling restart. (Swap the driver and the *same governed flow* drives a Linux
host, a batch job, or a SaaS API — see the [Adoption Guide](ADOPTION.md).)

### Step 6 — Verify: prove it actually worked

After execution, the platform checks the contract's **postconditions**:
- `healthy_pod_count >= 3` ✅
- `error_rate < 5` ✅

If the postconditions fail, the incident is **not** marked resolved — it retries
within the contract's retry budget or escalates. "The action ran" is not the same
as "the problem is fixed," and the platform knows the difference.

### Outcome

`SUCCESS` — with a complete **audit ledger**: the symptoms, the retrieved
runbook, the blast radius, the exact plan, every gate's verdict, who approved,
what executed, and the verified result. If an auditor asks "why did an AI restart
production at 2:47 AM?", the answer is one immutable record.

---

## 3. Why each part earns its place

| Component | The question it answers | Remove it and… |
|-----------|------------------------|----------------|
| **RAG (runbooks)** | "What do *our* experts say to do?" | the agent guesses from generic knowledge |
| **GraphRAG (topology)** | "What else breaks if I act?" | it fixes inventory and takes down checkout |
| **Planner LLM** | "What's the right sequence here?" | you're back to rigid scripts |
| **Contract** | "What is this agent *allowed* to do?" | an LLM hallucination can drop a database |
| **Adaptive rules** | "Should autonomy tighten right now?" | full autonomy applies even in a crisis |
| **Policy check** | "Does this violate our rules/compliance?" | unsafe or non-compliant actions slip through |
| **Risk + Budget** | "How dangerous? When do we stop/ask?" | runaway actions, no human safety net |
| **Human approval** | "Should a person sign off on this one?" | either everything needs a human, or nothing does |
| **MCP boundary + driver** | "How do we act, safely and swappably?" | the model touches prod directly |
| **Postconditions** | "Did it actually work?" | "ran" gets mistaken for "fixed" |
| **Audit ledger** | "Can we prove what happened and why?" | no accountability, no compliance story |

---

## 4. The value, in plain terms

| Stakeholder | What they get |
|-------------|---------------|
| **On-call engineers** | Routine incidents resolve themselves; humans are woken only for genuinely risky decisions. MTTR drops from tens of minutes to seconds for common cases. |
| **SRE / Platform leads** | Autonomy they can actually trust in production — hard limits, blast-radius awareness, and a kill-switch (approval) exactly where they want it. |
| **Security / Compliance** | Every autonomous action is bounded by policy-as-code and captured in an immutable audit trail — an answer to "prove the AI can't go rogue." |
| **The business** | Faster recovery = less downtime = less lost revenue, and the model scales to *hundreds* of services without hiring hundreds of on-call engineers. |

**The one-sentence pitch:** *the adaptability of an AI agent with the safety
guarantees of hand-written automation — because the agent reasons freely but can
only act inside contracts you enforce in code.*

---

## 5. This generalizes far beyond one incident

The same governed loop drives many use cases — you change the *knowledge and
contracts*, not the platform:

- **Payments operations** — block a fraudulent merchant, reroute a failing
  payment gateway, issue a refund — under PCI-aware policy and approval gates.
  (Shipped as the `payments_commander` example.)
- **Server / VM operations** — restart a stuck service on a Linux or Windows host,
  run an allowlisted remediation command (via the `HostCommandDriver`).
- **Batch / data pipelines** — re-trigger a failed ETL job, within limits, with
  verification.
- **Cloud / SaaS remediation** — call a provider API to cycle a resource, gated
  by the same contracts.

Any place where you'd want an expert to *act* — but can't hand a machine
unlimited power — is a fit. See the [Adoption Guide](ADOPTION.md) to point it at
your own services.
