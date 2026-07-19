"""LangGraph node functions for the orchestration workflow.

Each node function:
1. Takes OrchestratorState as input
2. Returns a partial dict updating only the keys it modifies
3. Never mutates state in-place
4. Generates audit trail entries

Node responsibilities are aligned with the architecture:
- RAG provides organizational intelligence
- LLM provides reasoning (planner)
- Contract provides boundaries
- Guardrails enforce boundaries
- MCP provides controlled execution
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.types import interrupt

from core.config import get_settings
from core.contracts import ContractLoader, OperationalContract
from core.contracts.adaptive import (
    AdaptiveContractResolver,
    AdaptiveContext,
    AdaptiveRule,
    RuleMutation,
)
from core.enums import ActionType, FinalStatus, GuardrailStatus, RiskLevel
from core.models import BaseIncident as Incident
from core.models import AuditEvent
from core.models import ExecutionResult
from core.models import PostconditionResult
from core.models import PostconditionRule
from core.models import GuardrailResult
from core.models import NormalizedAction
from core.models import RemediationPlan
from core.models import PlannedAction
from core.orchestration.state import OrchestratorState
from core.trust.manager import TrustManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node 1: Incident Ingestion
# ---------------------------------------------------------------------------

def ingest_incident(state: OrchestratorState) -> dict[str, Any]:
    """Validate and parse the incoming incident data.

    This is the entry point. The incident arrives as a dict and is
    validated through the Incident Pydantic model.
    """
    incident_data = state["incident"]
    incident = Incident(**incident_data)

    logger.info(f"Ingested incident {incident.incident_id} for {incident.service}")

    return {
        "incident": incident.model_dump(mode="json"),
        "service_name": incident.service,
        "retry_count": 0,
        "audit_trail": [
            AuditEvent(
                incident_id=incident.incident_id,
                event_type="incident_ingested",
                details={
                    "service": incident.service,
                    "severity": incident.severity,
                    "environment": incident.environment,
                },
                outcome="accepted",
            ).model_dump(mode="json")
        ],
    }


# ---------------------------------------------------------------------------
# Node 2: Service Identification
# ---------------------------------------------------------------------------

def identify_service(state: OrchestratorState) -> dict[str, Any]:
    """Extract and confirm the service name from the incident.

    In a production system, this could involve service registry lookups
    or dependency graph traversal. For the MVP, we extract from incident data.
    """
    incident = state["incident"]
    service_name = incident.get("service", "")

    logger.info(f"Identified service: {service_name}")

    return {"service_name": service_name}


# ---------------------------------------------------------------------------
# Node 3: RAG Knowledge Retrieval
# ---------------------------------------------------------------------------

async def retrieve_knowledge(state: OrchestratorState) -> dict[str, Any]:
    """Retrieve organization-specific knowledge via InvestigationAgent.

    Uses semantic search with metadata filtering to find relevant:
    - Architecture documentation
    - Operational runbooks
    - Historical incidents

    Retrieved documents are UNTRUSTED DATA — they provide context to
    the LLM but cannot override contracts or security policy.
    """
    from core.agents.investigation import InvestigationAgent
    from core.models import AuditEvent

    settings = get_settings()
    incident_data = state["incident"]
    incident = Incident(**incident_data)

    try:
        import chromadb

        chroma_client = chromadb.PersistentClient(path=str(settings.chroma_db_dir))
        collection = chroma_client.get_or_create_collection(
            name=settings.chroma_collection_name
        )

        agent = InvestigationAgent(collection=collection, top_k=settings.retrieval_top_k)
        retrieved_documents = await agent.investigate(incident)
        
        return {
            "retrieved_documents": retrieved_documents,
            "audit_trail": [
                AuditEvent(
                    incident_id=incident.incident_id,
                    event_type="knowledge_retrieved",
                    details={"document_count": len(retrieved_documents)},
                    outcome="success",
                ).model_dump(mode="json")
            ],
        }
    except Exception as e:
        logger.warning(f"Failed to setup InvestigationAgent: {e}")
        return {
            "retrieved_documents": [],
            "audit_trail": [
                AuditEvent(
                    incident_id=incident.incident_id,
                    event_type="knowledge_retrieved",
                    details={"error": str(e)},
                    outcome="fallback_no_context",
                ).model_dump(mode="json")
            ],
        }



# ---------------------------------------------------------------------------
# Node 4: Contract Resolution
# ---------------------------------------------------------------------------

def resolve_contract(state: OrchestratorState) -> dict[str, Any]:
    """Load the operational contract deterministically from filesystem.

    Contracts are NOT retrieved via RAG — they require exact matching
    by (service, environment) to prevent semantic drift.
    """
    settings = get_settings()
    incident = state["incident"]
    service = state["service_name"]
    environment = incident.get("environment", "production")

    contracts_dir = settings.knowledge_dir / "contracts"
    loader = ContractLoader(contracts_dir)

    try:
        base_contract = loader.load(service=service, environment=environment)
        
        # Phase B1: Resolve Effective Contract using Adaptive Rules
        # Hardcoding a demo rule until a rule persistence layer is implemented
        demo_rules = [
            AdaptiveRule(
                rule_id="restrict_scale_on_critical",
                description="Disable scaling and lower max restarts for CRITICAL incidents",
                min_severity_level="CRITICAL",
                mutation=RuleMutation(
                    override_max_pod_restarts=1,
                    remove_allowed_actions=["scale_deployment"]
                )
            )
        ]
        
        resolver = AdaptiveContractResolver(demo_rules)
        adaptive_ctx = AdaptiveContext(
            incident_severity=incident.get("severity", "LOW"),
            environment=environment,
        )
        
        contract = resolver.resolve_effective_contract(base_contract, adaptive_ctx)
        
        logger.info(f"Loaded and adapted contract: {contract.contract_id} v{contract.version}")

        return {
            "retrieved_contract": contract.model_dump(mode="json"),
            "audit_trail": [
                AuditEvent(
                    incident_id=incident.get("incident_id", ""),
                    event_type="contract_resolved",
                    contract_id=contract.contract_id,
                    contract_version=contract.version,
                    details={"service": service, "environment": environment},
                    outcome="loaded",
                ).model_dump(mode="json")
            ],
        }
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Contract resolution failed: {e}")
        # Without a contract, we cannot proceed autonomously
        return {
            "retrieved_contract": {},
            "guardrail_status": "REJECTED",
            "violations": [f"No contract found: {e}"],
            "final_status": FinalStatus.ESCALATED,
            "audit_trail": [
                AuditEvent(
                    incident_id=incident.get("incident_id", ""),
                    event_type="contract_resolution_failed",
                    details={"error": str(e)},
                    outcome="escalated",
                ).model_dump(mode="json")
            ],
        }


# ---------------------------------------------------------------------------
# Node 5: Plan Remediation
# ---------------------------------------------------------------------------

async def plan_remediation(state: OrchestratorState) -> dict[str, Any]:
    """Invoke the planning agent to propose a structured remediation plan.

    The planner receives:
    - Incident details
    - Retrieved organizational knowledge (as context)
    - Contract summary (to guide proposals)
    - Previous violations (if retrying)

    The planner generates structured output — it does NOT execute tools.
    This node is async because the LLM call is awaited.
    """
    from core.agents.planner import PlannerAgent, normalize_plan
    from core.knowledge.retriever import KnowledgeRetriever

    settings = get_settings()
    incident = Incident(**state["incident"])
    contract_data = state.get("retrieved_contract", {})
    violations = state.get("violations", [])
    retrieved_docs = state.get("retrieved_documents", [])

    # Build context from retrieved documents
    context_parts = []
    for doc in retrieved_docs:
        trust = doc.get("metadata", {}).get("trust_level", "unknown")
        context_parts.append(
            f"[Trust: {trust}]\n{doc.get('content', '')}"
        )
    context = "\n\n---\n\n".join(context_parts) if context_parts else "No organizational context available."

    # Build contract summary
    if contract_data:
        contract = OperationalContract(**contract_data)
        contract_summary = contract.to_summary()
    else:
        contract_summary = "No operational contract loaded."

    try:
        planner = PlannerAgent(
            model_name=settings.llm_model,
            temperature=settings.llm_temperature,
        )

        plan = await planner.plan(
            incident=incident,
            context=context,
            contract_summary=contract_summary,
            previous_violations=violations if violations else None,
        )

        # Normalize the plan into canonical actions
        normalized = normalize_plan(plan, incident.service)

        logger.info(f"Plan proposed: {plan.summary} ({len(plan.actions)} actions)")

        return {
            "proposed_plan": plan.model_dump(mode="json"),
            "normalized_actions": [a.model_dump(mode="json") for a in normalized],
            "audit_trail": [
                AuditEvent(
                    incident_id=incident.incident_id,
                    event_type="plan_proposed",
                    contract_id=contract_data.get("contract_id"),
                    contract_version=contract_data.get("version"),
                    details={
                        "summary": plan.summary,
                        "action_count": len(plan.actions),
                        "estimated_impact": plan.estimated_impact,
                        "retry_number": state.get("retry_count", 0),
                    },
                    outcome="proposed",
                ).model_dump(mode="json")
            ],
        }

    except Exception as e:
        logger.error(f"Planning failed: {e}")
        return {
            "proposed_plan": {},
            "normalized_actions": [],
            "guardrail_status": "REJECTED",
            "violations": [f"Planning failed: {e}"],
            "audit_trail": [
                AuditEvent(
                    incident_id=incident.incident_id,
                    event_type="plan_failed",
                    details={"error": str(e)},
                    outcome="error",
                ).model_dump(mode="json")
            ],
        }


# ---------------------------------------------------------------------------
# Node 6: Evaluate Guardrails
# ---------------------------------------------------------------------------

def evaluate_guardrails(state: OrchestratorState) -> dict[str, Any]:
    """Run the deterministic guardrail engine on the normalized plan.

    Priority order (absolute):
    1. Forbidden action check → instant reject
    2. Allowed action check → reject if not allowlisted
    3. Limit validation → reject if exceeded
    4. Availability constraint validation → reject if violated
    5. Approval requirement check → set flag

    Deterministic rules ALWAYS win. Semantic validation can only ADD
    restrictions, never REMOVE deterministic rejections.
    """
    from core.guardrails.engine import GuardrailEngine

    incident = state["incident"]
    contract_data = state.get("retrieved_contract", {})
    normalized_data = state.get("normalized_actions", [])

    if not contract_data or not normalized_data:
        return {
            "guardrail_status": GuardrailStatus.REJECTED,
            "violations": ["No contract or plan available for validation"],
            "approval_required": False,
        }

    contract = OperationalContract(**contract_data)
    normalized_actions = [NormalizedAction(**a) for a in normalized_data]

    engine = GuardrailEngine()
    result = engine.evaluate(
        normalized_actions=normalized_actions,
        contract=contract,
        execution_history=state.get("execution_history", []),
        current_metrics=state["incident"].get("metrics", {}),
    )

    logger.info(
        f"Guardrail result: {result.status} "
        f"(violations: {len(result.violations)}, approval: {result.approval_required})"
    )

    return {
        "guardrail_status": result.status,
        "violations": result.violations,
        "approval_required": result.approval_required,
        "audit_trail": [
            AuditEvent(
                incident_id=incident.get("incident_id", ""),
                event_type="guardrail_evaluated",
                contract_id=contract.contract_id,
                contract_version=contract.version,
                details={
                    "status": result.status,
                    "violations": result.violations,
                    "approval_required": result.approval_required,
                },
                outcome=result.status,
            ).model_dump(mode="json")
        ],
    }


# ---------------------------------------------------------------------------
# Node 7: Increment Retry
# ---------------------------------------------------------------------------

def increment_retry(state: OrchestratorState) -> dict[str, Any]:
    """Increment the retry counter after a plan rejection.

    Separated into its own node for clean state management —
    retry_count is explicitly incremented, not derived.
    """
    current = state.get("retry_count", 0)
    new_count = current + 1

    incident = state.get("incident", {})
    service = incident.get("service", "global")
    
    from core.trust.manager import TrustManager
    trust_manager = TrustManager()
    trust_manager.record_guardrail_rejection("planner", domain=service)

    logger.info(f"Plan rejected. Retry count: {new_count}")

    return {"retry_count": new_count}


# ---------------------------------------------------------------------------
# Node 7.5: Evaluate Semantics (Policy Agent)
# ---------------------------------------------------------------------------

async def evaluate_semantics(state: OrchestratorState) -> dict[str, Any]:
    """Evaluate semantic policies using the PolicyAgent.
    
    Can only ADD restrictions or rejections, never override deterministic approvals.
    """
    from core.agents.policy import PolicyAgent

    incident = state["incident"]
    incident_obj = Incident(**incident)
    contract_data = state["retrieved_contract"]
    contract = OperationalContract(**contract_data)
    plan = RemediationPlan(**state["proposed_plan"])

    validator = PolicyAgent()
    is_compliant, reasoning = await validator.validate(
        plan=plan,
        contract=contract,
        incident=incident_obj,
    )
    
    if not is_compliant:
        logger.warning(f"Semantic validation failed: {reasoning}")
        violations = state.get("violations", [])
        violations.append(f"Semantic policy violation: {reasoning}")
        
        return {
            "guardrail_status": GuardrailStatus.REJECTED,
            "violations": violations,
            "audit_trail": [
                AuditEvent(
                    incident_id=incident_obj.incident_id,
                    event_type="semantic_validation_failed",
                    details={"reasoning": reasoning},
                    outcome="rejected",
                ).model_dump(mode="json")
            ],
        }
    
    return {
        "audit_trail": [
            AuditEvent(
                incident_id=incident_obj.incident_id,
                event_type="semantic_validation_passed",
                details={"reasoning": reasoning},
                outcome="passed",
            ).model_dump(mode="json")
        ],
    }

# ---------------------------------------------------------------------------
# Node 8: Evaluate Risk
# ---------------------------------------------------------------------------

def evaluate_risk(state: OrchestratorState) -> dict[str, Any]:
    """Assess risk level of an approved plan.

    HIGH/CRITICAL risk or contract approval requirements trigger
    human-in-the-loop approval.
    """
    from core.guardrails.risk import RiskEvaluator
    from core.trust.manager import TrustManager

    incident = Incident(**state["incident"])
    plan = RemediationPlan(**state["proposed_plan"])
    contract = OperationalContract(**state["retrieved_contract"])

    # In a real app, TrustManager would be a singleton or injected
    trust_manager = TrustManager()
    trust_score = trust_manager.get_score("planner", domain=incident.service).score

    evaluator = RiskEvaluator()
    score, risk_level, needs_approval = evaluator.evaluate(plan, incident, contract, trust_score)

    # Merge with guardrail approval_required flag
    approval_required = needs_approval or state.get("approval_required", False)

    logger.info(f"Risk: {risk_level}, approval required: {approval_required}")

    return {
        "risk_level": risk_level,
        "approval_required": approval_required,
        "audit_trail": [
            AuditEvent(
                incident_id=incident.incident_id,
                event_type="risk_evaluated",
                contract_id=contract.contract_id,
                contract_version=contract.version,
                details={
                    "risk_level": risk_level,
                    "approval_required": approval_required,
                },
                outcome=risk_level,
            ).model_dump(mode="json")
        ],
    }


# ---------------------------------------------------------------------------
# Node 9: Request Human Approval (HITL)
# ---------------------------------------------------------------------------

def request_human_approval(state: OrchestratorState) -> dict[str, Any]:
    """Pause execution and request human approval.

    Uses LangGraph's interrupt() function to pause the workflow.
    The human reviewer sees the full context:
    - Incident details
    - Retrieved knowledge
    - Proposed plan
    - Contract
    - Violations (if any)
    - Risk level

    Resumed via Command(resume="APPROVED") or Command(resume="REJECTED").
    """
    incident = state["incident"]
    plan = state.get("proposed_plan", {})
    violations = state.get("violations", [])
    risk_level = state.get("risk_level", "UNKNOWN")

    approval_context = {
        "incident_id": incident.get("incident_id"),
        "service": incident.get("service"),
        "severity": incident.get("severity"),
        "proposed_plan": plan,
        "violations": violations,
        "risk_level": risk_level,
        "retry_count": state.get("retry_count", 0),
        "message": "Human approval required. Review the plan and respond with APPROVED or REJECTED.",
    }

    logger.info(f"Requesting human approval for {incident.get('incident_id')}")

    # interrupt() pauses here — resumes when a human provides a decision.
    # The resume payload may be a bare string or {"decision", "actor"} so the
    # approver's identity is captured into the audit trail.
    resume_value = interrupt(approval_context)

    if isinstance(resume_value, dict):
        decision = str(resume_value.get("decision", "")).upper().strip()
        actor = str(resume_value.get("actor", "unknown"))
    else:
        decision = str(resume_value).upper().strip()
        actor = "unknown"

    if decision not in ("APPROVED", "REJECTED"):
        decision = "REJECTED"

    logger.info(f"Human decision: {decision} by {actor}")

    return {
        "human_decision": decision,
        "approved_by": actor,
        "audit_trail": [
            AuditEvent(
                incident_id=incident.get("incident_id", ""),
                event_type="human_decision",
                actor=actor,
                details={"decision": decision, "context": approval_context},
                outcome=decision,
            ).model_dump(mode="json")
        ],
    }


# ---------------------------------------------------------------------------
# Node 10: Execute Actions via MCP
# ---------------------------------------------------------------------------

def execute_actions(state: OrchestratorState) -> dict[str, Any]:
    """Execute approved actions through the MCP execution boundary.

    The MCP client enforces:
    - Strict input schemas
    - Action allowlist validation
    - Structured results
    - Audit logging

    The LLM never directly accesses infrastructure APIs.
    """
    from core.execution.client import get_mcp_client

    incident = state["incident"]
    normalized_data = state.get("normalized_actions", [])

    if not normalized_data:
        return {
            "execution_history": [],
            "final_status": FinalStatus.FAILED,
        }

    client = get_mcp_client(incident.get("incident_id"))
    results: list[dict] = []
    successful_actions: list[NormalizedAction] = []
    
    compensation_triggered = False

    for action_data in normalized_data:
        action = NormalizedAction(**action_data)

        # Skip non-executable actions (status/metrics queries)
        if action.action in (ActionType.GET_SERVICE_STATUS, ActionType.GET_METRICS):
            continue

        result = client.execute_action(action)
        results.append(result.model_dump(mode="json"))

        logger.info(
            f"Executed {action.action}: success={result.success}"
        )
        
        if result.success:
            successful_actions.append(action)
        else:
            logger.error(f"Action {action.action} failed: {result.error}. Triggering compensation.")
            compensation_triggered = True
            break

    # Saga compensation
    compensation_results: list[dict] = []
    if compensation_triggered:
        # Compensate in reverse order of success
        for successful_action in reversed(successful_actions):
            if successful_action.compensation:
                logger.info(f"Executing compensation for {successful_action.action}: {successful_action.compensation.action}")
                comp_result = client.execute_action(successful_action.compensation)
                compensation_results.append(comp_result.model_dump(mode="json"))
            else:
                logger.info(f"No compensation defined for {successful_action.action}")

    return {
        "execution_history": results,
        "compensation_history": compensation_results,
        "audit_trail": [
            AuditEvent(
                incident_id=incident.get("incident_id", ""),
                event_type="actions_executed",
                contract_id=state.get("retrieved_contract", {}).get("contract_id"),
                contract_version=state.get("retrieved_contract", {}).get("version"),
                details={
                    "action_count": len(results),
                    "all_succeeded": not compensation_triggered,
                    "compensated": compensation_triggered,
                },
                outcome="compensated" if compensation_triggered else "executed",
            ).model_dump(mode="json")
        ],
    }


# ---------------------------------------------------------------------------
# Node 11: Validate Postconditions
# ---------------------------------------------------------------------------

def validate_postconditions(state: OrchestratorState) -> dict[str, Any]:
    """Check postcondition rules against current metrics after execution.

    Postconditions are defined in the contract as strings like:
    'healthy_pod_count >= 3' and parsed into structured PostconditionRule objects.

    If postconditions fail, the system may retry or escalate.
    """
    from core.execution.client import get_mcp_client

    incident = state["incident"]
    contract_data = state.get("retrieved_contract", {})
    service = state.get("service_name", "")

    if not contract_data:
        return {"postcondition_results": [], "final_status": FinalStatus.FAILED}

    contract = OperationalContract(**contract_data)
    rules = contract.get_postcondition_rules()

    if not rules:
        logger.info("No postconditions defined — treating as success")
        return {"postcondition_results": [], "final_status": FinalStatus.SUCCESS}

    # Get current metrics after execution — the per-incident client observes the
    # same cluster mutated by execute_actions.
    client = get_mcp_client(incident.get("incident_id"))
    current_metrics = client.get_current_metrics(service)

    # Map metric names to current values
    metric_map = {
        "healthy_pod_count": current_metrics.get("healthy_pods", 0),
        "error_rate": current_metrics.get("error_rate", 100),
    }

    results = []
    for rule in rules:
        actual = metric_map.get(rule.metric, 0)
        passed = rule.evaluate(actual)
        results.append(
            PostconditionResult(
                rule=f"{rule.metric} {rule.operator} {rule.threshold}",
                actual_value=actual,
                passed=passed,
            ).model_dump(mode="json")
        )

    all_passed = all(r.get("passed", False) for r in results)

    logger.info(
        f"Postconditions: {'ALL PASSED' if all_passed else 'SOME FAILED'} "
        f"({sum(1 for r in results if r.get('passed'))}/{len(results)})"
    )

    return {
        "postcondition_results": results,
        "audit_trail": [
            AuditEvent(
                incident_id=incident.get("incident_id", ""),
                event_type="postconditions_validated",
                contract_id=contract.contract_id,
                contract_version=contract.version,
                details={"results": results, "all_passed": all_passed},
                outcome="passed" if all_passed else "failed",
            ).model_dump(mode="json")
        ],
    }


# ---------------------------------------------------------------------------
# Node 12: Handle Escalation
# ---------------------------------------------------------------------------

def handle_escalation(state: OrchestratorState) -> dict[str, Any]:
    """Prepare escalation package for human review.

    Triggered when retry limit is reached or postconditions fail
    after execution. Collects all context for the human reviewer.
    """
    incident = state["incident"]

    logger.warning(
        f"Escalating incident {incident.get('incident_id')} — "
        f"retries: {state.get('retry_count', 0)}, "
        f"violations: {state.get('violations', [])}"
    )

    return {
        "approval_required": True,
        "audit_trail": [
            AuditEvent(
                incident_id=incident.get("incident_id", ""),
                event_type="escalated",
                details={
                    "retry_count": state.get("retry_count", 0),
                    "violations": state.get("violations", []),
                    "reason": "retry_limit_reached_or_postcondition_failure",
                },
                outcome="escalated",
            ).model_dump(mode="json")
        ],
    }


# ---------------------------------------------------------------------------
# Node 13: Finalize
# ---------------------------------------------------------------------------

async def finalize(state: OrchestratorState) -> dict[str, Any]:
    """Set the final outcome status and generate summary.

    Determines: SUCCESS, FAILED, ESCALATED, or DENIED.
    Generates a post-incident summary using the SummaryAgent.
    """
    from core.agents.summary import SummaryAgent

    incident_data = state["incident"]
    incident = Incident(**incident_data)

    # Determine final status
    if state.get("human_decision") == "REJECTED":
        final_status = FinalStatus.DENIED
    elif state.get("final_status"):
        final_status = state["final_status"]
    else:
        # Check postconditions
        results = state.get("postcondition_results", [])
        all_passed = all(r.get("passed", False) for r in results) if results else True
        exec_history = state.get("execution_history", [])
        all_executed = all(r.get("success", False) for r in exec_history) if exec_history else False

        if all_passed and all_executed:
            final_status = FinalStatus.SUCCESS
        elif state.get("retry_count", 0) >= 3:
            final_status = FinalStatus.ESCALATED
        else:
            final_status = FinalStatus.FAILED

    logger.info(f"Finalized incident {incident.incident_id}: {final_status}")

    # Record trust outcome
    trust_manager = TrustManager()
    if final_status == FinalStatus.SUCCESS:
        trust_manager.record_success("planner", domain=incident.service)
    elif final_status == FinalStatus.FAILED:
        trust_manager.record_failure("planner", domain=incident.service)
    elif final_status == FinalStatus.ESCALATED:
        trust_manager.record_escalation("planner", domain=incident.service)

    # Generate summary
    try:
        agent = SummaryAgent()
        audit_trail = state.get("audit_trail", [])
        summary = await agent.summarize(incident, audit_trail)
    except Exception as e:
        logger.warning(f"Summary generation failed: {e}")
        summary = "Failed to generate summary."

    return {
        "final_status": final_status,
        "executive_summary": summary,
        "audit_trail": [
            AuditEvent(
                incident_id=incident.incident_id,
                event_type="finalized",
                details={
                    "final_status": final_status,
                    "retry_count": state.get("retry_count", 0),
                    "execution_count": len(state.get("execution_history", [])),
                    "executive_summary": summary,
                },
                outcome=final_status,
            ).model_dump(mode="json")
        ],
    }
