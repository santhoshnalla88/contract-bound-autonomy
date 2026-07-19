# Plugging GAAP into Your Organization — A Friendly Adoption Guide

Welcome! This guide shows you how to take this platform — **GAAP, the Governed
Autonomous AI Platform** — and point it at *your* services, *your* runbooks, and
*your* safety rules, without editing a single line of Python.

You don't need to understand the whole codebase to adopt it. You mostly edit a
handful of **JSON and Markdown files** in the `knowledge/` folder and set a few
environment variables. That's the whole idea: **the code is the engine, your
config is the steering wheel.**

---

## 1. The one-paragraph mental model

An AI agent looks at an incident, reads your runbooks, and proposes a fix. But it
is **never trusted blindly**. Before anything executes, the proposed plan must
pass through a chain of deterministic gates you control:

```
Incident ──▶ 🤖 Agent proposes a plan (grounded in YOUR runbooks + dependency graph)
                    │
                    ▼
         🛡️  Contract      → "Is this action even allowed for this service?"
         🎚️  Adaptive rules → "Given this is CRITICAL, tighten the limits"
         📜  Policy check    → "Does it violate PCI/GDPR/SOX-style rules?"
         📊  Risk score      → "How dangerous is this? Do we need a human?"
         💰  Budget          → "Have we spent too many actions on this incident?"
                    │
                    ▼
         🙋  Human approval (only when risk/contract demands it)
                    │
                    ▼
         ⚙️  Execute (mock, or real Kubernetes) → verify postconditions → done
```

**Agents reason freely; they act only inside contracts you write.** Everything
below is about writing those contracts and feeding the agent your knowledge.

---

## 2. What you plug in (the 5 things that make it "yours")

Everything organization-specific lives in **config and content files** — no code
changes required. Here's the whole surface area:

| # | What | Where | Format |
|---|------|-------|--------|
| 1 | **Contracts** — what each service is allowed/forbidden to do | `knowledge/contracts/<service>-contract.json` | JSON |
| 2 | **Runbooks & knowledge** — what the agent reads to plan | `knowledge/runbooks/`, `knowledge/architecture/`, `knowledge/incidents/` | Markdown |
| 3 | **Adaptive rules** — how autonomy tightens under pressure | inside each contract's `adaptive_rules` array | JSON |
| 4 | **Service topology** — the dependency/blast-radius graph | `knowledge/topology.json` | JSON |
| 5 | **Wiring** — LLM keys, execution backend, DBs | `.env` / environment variables | key=value |

If you only change these five things, you have adapted the entire platform to
your organization. Let's walk through each.

---

## 3. Quickstart: see it work in 5 minutes (with the demo service)

Before customizing, run it as-is to build intuition.

```bash
# 1. Copy the env template and add your keys
cp .env.example .env         # then edit .env (see section 7)

# 2. Bring up the whole stack: postgres + redis + neo4j + api + worker
docker compose up

# 3. Open the control plane
#    → http://localhost:8000
#    Log in with the bootstrap admin (BOOTSTRAP_ADMIN_EMAIL / _PASSWORD from .env)
#    → Submit the demo incident and watch the agent plan → gates → approve → execute
```

No API keys handy? The platform still runs — it **fail-safe escalates** (the agent
can't plan, so guardrails reject and the incident is handed to a human). That's
the safe default, not a bug.

---

## 4. Onboard your first real service (the 4 files)

Say you want to protect a service called `orders-api`. Here's the full checklist.

### 4a. Write its contract → `knowledge/contracts/orders-api-contract.json`

Copy the demo contract and change the names. This is the **hard boundary** —
the agent can propose anything, but only what's listed here can execute.

```json
{
  "contract_id": "orders-api-production-v1",
  "service": "orders-api",
  "environment": "production",
  "version": "1.0.0",

  "allowed_actions":   ["restart_pods", "scale_deployment", "rollback_deployment"],
  "forbidden_actions": ["delete_persistent_volume", "drop_database", "modify_production_secrets"],

  "limits": {
    "max_pod_restarts_per_incident": 2,
    "max_replicas": 10,
    "max_scale_up_percentage": 200
  },
  "availability_constraints": {
    "minimum_available_replicas": 2,
    "preserve_active_connections": true,
    "max_unavailability_percentage": 25
  },
  "approval_requirements": {
    "restart_pods": false,
    "scale_deployment": false,
    "rollback_deployment": true
  },
  "retry_policy": { "max_plan_retries": 3 },
  "postconditions": ["healthy_pod_count >= 3", "error_rate < 5"],

  "adaptive_rules": []
}
```

**Field cheat-sheet:**
- `allowed_actions` / `forbidden_actions` — the allowlist/blocklist. Forbidden always wins.
- `limits` — numeric ceilings the agent can never exceed.
- `approval_requirements` — set an action to `true` to *always* require a human.
- `postconditions` — checked *after* execution; if they fail, the fix is treated as unsuccessful.

> The loader finds this file automatically by name: `<service>-contract.json`.
> No registration step, no code.

### 4b. Give it runbooks → `knowledge/runbooks/orders-api-*.md`

Drop in plain-English Markdown runbooks — the same docs your on-call engineers
read. At startup the platform **chunks and embeds** them into the vector store
(ChromaDB) so the agent retrieves the *relevant* runbook when planning. The more
specific and actionable your runbooks, the better the plans.

You can also add `knowledge/architecture/` (how the service is built) and
`knowledge/incidents/` (past postmortems) — all Markdown, all auto-ingested.

### 4c. Tune its autonomy under pressure → `adaptive_rules`

This is the "governed" part of governed autonomy. A contract sets a *fixed*
ceiling; **adaptive rules narrow that ceiling based on context** — severity,
agent trust score, or a feature flag. Add them to the `adaptive_rules` array in
the contract:

```json
"adaptive_rules": [
  {
    "rule_id": "restrict_scale_on_critical",
    "description": "For CRITICAL incidents, disable scaling and lower max restarts to 1.",
    "min_severity_level": "CRITICAL",
    "mutation": {
      "override_max_pod_restarts": 1,
      "remove_allowed_actions": ["scale_deployment"]
    }
  }
]
```

Read it as: *"When the incident is CRITICAL, the agent may only restart one pod
and may no longer scale."* You can layer several rules — each one that matches
tightens the effective contract further. Available mutations:

| Mutation | Effect |
|----------|--------|
| `override_max_replicas` | Lower the replica ceiling |
| `override_max_pod_restarts` | Lower the restart ceiling |
| `remove_allowed_actions` | Take actions off the allowlist |
| `add_forbidden_actions` | Add hard blocks |
| `require_approval_for` | Force human approval for listed actions |

Match conditions: `min_severity_level`, `max_trust_score` (only apply to
low-trust agents), and `requires_flag` (gate on a runtime flag).

Leave `adaptive_rules: []` if you want a purely static contract.

### 4d. Place it in the dependency graph → `knowledge/topology.json`

So the agent understands **blast radius** ("if I restart `orders-api`, what else
breaks?"), add your service to the topology graph. This is seeded into Neo4j at
startup and queried during investigation.

```json
{
  "dependencies": [
    { "service": "checkout-service", "depends_on": "orders-api" },
    { "service": "orders-api",       "depends_on": "orders-db" },
    { "service": "orders-api",       "depends_on": "cache-redis" }
  ],
  "criticality": {
    "checkout-service": "CRITICAL",
    "orders-api": "HIGH"
  }
}
```

Read each edge as *"`service` **depends on** `depends_on`"* — so if `depends_on`
degrades, `service` is in the blast radius. The agent will factor "critical
dependent `checkout-service`" into its reasoning and risk. (Set
`GRAPH_ENABLED=false` to skip Neo4j entirely — the platform runs on runbooks
alone; the graph *enriches*, it never blocks.)

**That's it.** Four files, zero code, and `orders-api` is fully onboarded.

---

## 5. Choosing how actions actually execute

By default, execution is a **mock driver** — perfect for demos and dry runs; it
simulates restarts/scales/rollbacks and reports success. When you're ready for
real infrastructure, flip one environment variable:

```bash
EXECUTION_BACKEND=kubernetes    # default: mock
```

The Kubernetes driver performs real rolling restarts, scales, and rollbacks.
Because execution sits behind a **pluggable driver registry**, you (or your
platform team) can add a driver for *any* target — a Linux/Windows host, a batch
scheduler, Terraform, a CI system, a cloud/SaaS API — and select it by name via
`EXECUTION_BACKEND`, without touching the governance logic. The gates stay
identical; only the "hands" change. See **§5b** for the full recipe.

---

## 5b. Integrating *any* kind of target (not just Kubernetes)

The governance brain — planning, contracts, policy, risk, approval, audit — is
**completely target-agnostic**. It emits an abstract `action` + `target` +
`parameters` and never touches infrastructure itself. The only piece that knows
*how* to act on a specific system is the **execution driver**. So supporting a
new class of workload is: **add the verbs → write one driver → register it →
add a contract.** No changes to the core.

### What kinds of targets are supported?

| Target type | How the driver acts | Action verbs to use |
|-------------|--------------------|---------------------|
| **Kubernetes microservices** | Kubernetes API | `restart_pods`, `scale_deployment`, `rollback_deployment` |
| **Linux servers / VMs / bare metal / on-prem hosts** | SSH (`paramiko`) or local subprocess | `run_command`, `restart_service`, `start_service`, `stop_service` |
| **Windows servers** | WinRM / PowerShell Remoting (`pywinrm`) | `run_command`, `restart_service`, `start_service`, `stop_service` |
| **Batch / ETL / cron / scheduler jobs** | scheduler API or a trigger command | `run_batch_job`, `run_command` |
| **Cloud / SaaS apps & APIs** | REST call (`http_request`) | `http_request` |
| **On-prem apps (custom)** | whatever your app exposes (CLI, API, queue) | any of the above, or your own verb |

All of the target-neutral verbs (`run_command`, `restart_service`,
`start_service`, `stop_service`, `run_batch_job`, `http_request`) ship in the
platform today, and the **mock backend simulates them** — so you can write and
test a contract for a Linux host or a batch job *before* wiring real execution.

### The 4-step recipe

**1. Put the verbs in the service's contract** (`allowed_actions`). Example for a
Linux app host:

```json
{
  "contract_id": "billing-host-production-v1",
  "service": "billing-host",
  "environment": "production",
  "allowed_actions": ["restart_service", "run_command", "run_batch_job"],
  "forbidden_actions": ["delete_persistent_volume", "drop_database"],
  "approval_requirements": { "run_command": true },
  "postconditions": ["error_rate < 5"]
}
```

**2. Use the built-in reference driver, or write your own.** A ready-made
`HostCommandDriver` ([examples/host_commander/drivers/host_command.py](../examples/host_commander/drivers/host_command.py))
runs **allowlisted** commands over `local` / `ssh` / `winrm`, plus `http_request`
for cloud/SaaS. Writing a custom driver means implementing three methods:

```python
from core.execution.drivers.base import ExecutionDriver

class MyDriver(ExecutionDriver):
    def execute(self, action, target, parameters): ...      # do the action, return {"success": bool, ...}
    def get_service_status(self, service): ...
    def get_metrics(self, service): ...
```

**3. Register it under a name** — at your app/worker startup:

```python
from core.execution.drivers import register_driver
from examples.host_commander.drivers.host_command import HostCommandDriver

register_driver("host", lambda s: HostCommandDriver(
    commands={                          # the ONLY commands that can run
        "restart_svc": "systemctl restart {service}",
        "run_job":     "/opt/jobs/run.sh {job}",
        "flush_cache": "systemctl restart myapp-cache",
    },
    transport="ssh", host="billing01.internal", user="deploy",
))
```

**4. Select it** with one environment variable:

```bash
EXECUTION_BACKEND=host
```

That's the whole integration. The same incident → plan → **gates** → approval →
audit flow now governs a Linux host, a batch job, or a SaaS API exactly as it
governs a Kubernetes deployment.

### Why this is safe (not "let the AI run shell")

The driver **never executes free-form model text.** It runs only commands from
the `commands` allowlist *you* define, every parameter is shell-quoted, and the
whole thing sits *behind* the contract allowlist, policy checks, risk scoring,
human approval, and the audit ledger. It's the same posture as Ansible or AWS
SSM runbooks — the model chooses an *approved action*, never an arbitrary command.

---

## 6. Choose your AI models (bring your own keys)

The platform is **provider-agnostic** via a small LLM factory. Each role (planner,
policy checker, summarizer) can point at a different provider/model. Set these in
`.env`:

```bash
# Planner — the heavy reasoning. Claude Opus by default.
PLANNER_PROVIDER=anthropic
PLANNER_MODEL=claude-opus-4-8

# Policy/compliance check — fast + cheap.
POLICY_PROVIDER=anthropic
POLICY_MODEL=claude-haiku-4-5

# Summaries — best-effort, degrades gracefully.
SUMMARY_PROVIDER=google
SUMMARY_MODEL=gemini-2.0-flash

# Embeddings for RAG — "local" needs no key or quota (recommended to start).
EMBEDDING_PROVIDER=local
```

Supported providers: `anthropic`, `google`, `openai`. Want everything on one
vendor? Set all three roles to the same provider/model. Embeddings default to
**local ONNX** so retrieval works with no external key and no rate limits.

---

## 7. Environment reference (the `.env` you'll create)

| Variable | What it does | Sensible default |
|----------|--------------|------------------|
| `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `OPENAI_API_KEY` | LLM credentials | (yours) |
| `PLANNER_PROVIDER` / `PLANNER_MODEL` | Planning model | `anthropic` / `claude-opus-4-8` |
| `POLICY_PROVIDER` / `POLICY_MODEL` | Compliance model | `anthropic` / `claude-haiku-4-5` |
| `SUMMARY_PROVIDER` / `SUMMARY_MODEL` | Summary model | `google` / `gemini-2.0-flash` |
| `EMBEDDING_PROVIDER` | RAG embeddings | `local` |
| `INGEST_ON_STARTUP` | Auto-load `knowledge/` into the vector store | `true` |
| `GRAPH_ENABLED` | Turn Neo4j blast-radius on/off | `false` (turn on for full experience) |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | Graph DB connection | from compose |
| `EXECUTION_BACKEND` | `mock` or `kubernetes` | `mock` |
| `APP_ENV` | `production` \| `local` \| `test` (selects backends, fail-fast validation) | `local` |
| `DATABASE_URL` / `REDIS_URL` | Postgres checkpointer + Arq queue / SSE bus | from compose |
| `JWT_SECRET` | Signs auth tokens — **set a strong value in production** | (change me) |
| `BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` | First admin login | (yours) |

> 🔐 **Security:** never commit `.env`. Rotate any key that has ever been pasted
> into a chat, ticket, or screenshot. Keys belong in `.env` (gitignored) or your
> secrets manager only.

---

## 8. Who can do what (roles)

The control plane ships with **JWT auth + role-based access control**. Four roles,
increasing power:

`viewer` → `operator` → `approver` → `admin`

- **viewer** — read incidents, plans, and audit trail.
- **operator** — submit incidents, trigger the workflow.
- **approver** — approve/reject the human-in-the-loop gate. Their identity is
  captured into the audit ledger.
- **admin** — everything, including user management.

Map these to your SSO groups when you integrate with your identity provider.

---

## 9. A sensible rollout path

1. **Shadow / mock mode.** Keep `EXECUTION_BACKEND=mock`. Onboard a few services,
   feed real runbooks, submit real (or replayed) incidents. Watch the plans and
   gate decisions. You're grading the agent without touching production.
2. **Tighten contracts.** Start with narrow `allowed_actions` and `true` approval
   requirements everywhere. Loosen deliberately as you gain confidence.
3. **Turn on the graph.** Set `GRAPH_ENABLED=true` and fill in `topology.json` so
   blast-radius reasoning kicks in.
4. **Go live, carefully.** Flip one non-critical service to
   `EXECUTION_BACKEND=kubernetes`. Keep human approval mandatory at first.
5. **Expand.** Add services, refine adaptive rules, relax approvals where the
   audit trail shows the agent is reliably right.

Every step is reversible, and everything is recorded in the **audit ledger** —
who proposed what, which gates said what, who approved, and what executed.

---

## 10. FAQ

**Do I have to use Kubernetes?** No. Mock is the default, Kubernetes is built in,
and the driver registry lets you plug in any target — Linux/Windows servers,
batch jobs, cloud/SaaS APIs, on-prem apps. See §5b for the recipe.

**Can it govern batch jobs and plain servers, not just microservices?** Yes. Use
the `run_command`, `restart_service`, `run_batch_job`, and `http_request` verbs
in the contract and point `EXECUTION_BACKEND` at a driver that performs them (the
built-in `HostCommandDriver` covers SSH/WinRM/local + HTTP).

**Can the AI do something my contract forbids?** No. The contract and guardrails
are deterministic code, not suggestions to the model. A forbidden action cannot
execute even if the model insists on it.

**What if I have no GPU / no embedding budget?** Use `EMBEDDING_PROVIDER=local` —
retrieval runs on a small local model with no external calls.

**What if the AI is wrong?** The gates catch out-of-contract plans; risky plans
require human approval; postconditions verify the outcome; and everything is in
the audit log. Worst case, the incident escalates to a human — the safe default.

**How is this different from a script/runbook automation?** Scripts do exactly
what you wrote. This *reasons* over novel incidents using your knowledge, then is
*constrained* by your contracts. You get adaptability **and** guardrails.

**Where do I change the demo topology / rules?** You already can — they live in
`knowledge/topology.json` and each contract's `adaptive_rules`. Nothing is
hardcoded in the application.

---

Happy adopting. Start with the 5-minute demo, then onboard one service with the
four files in section 4 — you'll have a governed autonomous remediation loop
running against your own stack the same afternoon.
