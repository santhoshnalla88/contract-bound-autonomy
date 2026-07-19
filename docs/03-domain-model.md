# 03 — Domain Model (DDD)

> **Author:** Santhosh Kumar Nalla | [LinkedIn](https://linkedin.com/in/techiesanthoshnalla)

Ubiquitous language and tactical patterns per bounded context. `[✓]` exists, `[▢]` planned.

## Governance context
**Aggregates**
- **Contract** `[✓]` — root of governance for an agent/context. Invariants: forbidden ∩ allowed = ∅; limits ≥ 0; version is immutable once published.
  - Value objects: `ActionPermission`, `Limit` (max restarts/replicas/…), `AvailabilityConstraint`, `ApprovalRequirement`, `Postcondition` `[✓]`; `Budget` (tokens/cost/time/calls) `[▢]`, `CompliancePack` ref `[▢]`, `RollbackStrategy` `[▢]`.
- **AdaptiveContract** `[▢]` — a Contract + ordered `AdaptiveRule`s. A rule = `when(context predicate) → mutate(permissions/limits/approval)`. Produces an **EffectiveContract** (value object) for a specific case. Invariant: rules may only *narrow below* a hard ceiling unless an explicit `elevation` rule with an approval gate fires.
- **PolicyPack** `[▢]` — named set of `PolicyRule`s (PCI/GDPR/SOX/custom). Evaluates an action → `Compliant | Violation(reason)`.

**Value objects**: `RiskAssessment` (score 0–100, band, factors, decision) `[~]`, `BudgetLedgerEntry` `[▢]`.

**Domain services**: `GuardrailEnforcer` (deterministic allow/forbid/limits/availability) `[✓]`; `RiskScorer` `[~]`; `PolicyEvaluator` `[▢]`; `BudgetAccountant` `[▢]`; `AdaptiveContractResolver` `[▢]`.

## Orchestration context
**Aggregates**
- **Case** `[✓ as Incident]` — the unit of work (incident, payment failure, refund request). Root that owns the workflow state, plan, executions, decisions. Invariant: terminal state is final.
- **Plan** `[✓]` — proposed by the Planner agent; ordered `PlannedAction`s with rationale. Normalized to `NormalizedAction` (canonical, enum-typed) before governance.
- **AgentRun** `[▢]` — an invocation of a role agent with its inputs/outputs, tokens, cost, latency (feeds budget + trust).

**Value objects**: `NormalizedAction` `[✓]`, `ExecutionResult` `[✓]`, `PostconditionResult` `[✓]`.

**Domain services**: `Planner` `[✓]`; `Investigation/Knowledge/Policy/Summary agents` `[▢]`; `ExecutionRuntime` (MCP) `[✓]`; `CompensationCoordinator` (saga-style rollback) `[▢]`.

## Approval context
- **ApprovalRequest** `[✓]` aggregate: case ref, proposed plan, risk, required role, status. **Decision** value object: `APPROVED|REJECTED|CHANGES_REQUESTED`, actor identity, reasoning, timestamp. Invariant: only a role ≥ required may resolve; resolution is idempotent.

## Knowledge context
- **KnowledgeDocument** `[✓]` (content + metadata + trust level, retrieved via RAG). **MemoryRecord** `[▢]`: short-term (per case) and long-term (per agent/domain) with recall scope. Trust level is advisory metadata — never grants permission.

## Audit & Observability context
- **AuditEvent** `[✓]` (immutable): case, actor (`system` or user), event type, contract id/version, details, outcome, timestamp. The **AuditLedger** is append-only. **DecisionTrace** `[▢]` = the ordered projection of a case's events for explainability.

## Identity context
- **User** `[✓]` (email, hashed pw, **Role**). Role ladder value object: `viewer < operator < approver < admin` `[✓]`. **TrustScore** `[▢]` per agent: rolling success/violation/override history → autonomy modifier consumed by the Risk/Adaptive services.

## Commands (intent) → Events (fact)
| Command `[status]` | Emits Event |
|---|---|
| `SubmitCase` `[✓]` | `CaseSubmitted` |
| `RetrieveKnowledge` `[✓]` | `KnowledgeRetrieved` |
| `ResolveEffectiveContract` `[▢]` | `EffectiveContractResolved` |
| `ProposePlan` `[✓]` | `PlanProposed` |
| `EvaluateGovernance` (guardrail+policy+risk+budget) `[~]` | `GovernanceEvaluated` (Approved/Rejected + reasons) |
| `RequestApproval` `[✓]` | `ApprovalRequested` |
| `RecordDecision` `[✓]` | `DecisionRecorded` |
| `ExecuteAction` `[✓]` | `ActionExecuted` |
| `ValidatePostconditions` `[✓]` | `PostconditionsValidated` |
| `Compensate` `[▢]` | `CompensationExecuted` |
| `Escalate` `[✓]` | `CaseEscalated` |
| `FinalizeCase` `[✓]` | `CaseFinalized` |

## Domain policies (reactions)
- On `GovernanceEvaluated(Rejected)` → increment retry; if retries exhausted → `Escalate`. `[✓]`
- On `RiskAssessment.band ≥ HIGH` **or** `EffectiveContract.requiresApproval(action)` → `RequestApproval`. `[✓ / ▢ adaptive part]`
- On `BudgetExceeded` → block action + `Escalate`. `[▢]`
- On `ActionExecuted(failure)` with a `RollbackStrategy` → `Compensate`. `[▢]`
- On `CaseFinalized` → update agent `TrustScore`. `[▢]`

## Anti-corruption / boundaries
- Domains (payments, infra) map their concepts to core `Case`/`Action` via adapters; **core never imports a domain**.
- LLM output is untrusted: it only produces a `Plan`, always normalized + governed before any effect. Deterministic governance **always wins**.
