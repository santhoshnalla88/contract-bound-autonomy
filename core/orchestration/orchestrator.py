"""Runs the orchestration graph and bridges it to the UI.

``run_workflow`` drives the compiled LangGraph with ``astream`` so each node's
state update becomes a real-time :class:`WorkflowEvent` on the event bus
(consumed by the SSE endpoint). It also keeps the incidents table's status
current, manages the pending-approvals table, and persists the full audit trail
(including the approver's identity) to the database on terminal states.

The same entry point handles a fresh run (``resume=None``) and resuming a
human-in-the-loop interrupt (``resume="APPROVED" | "REJECTED"`` with an actor).
In production it runs inside the Arq worker; locally it runs inline.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import Command

from core.models import AuditEvent
from core.events import WorkflowEvent, get_event_bus
from core.orchestration.builder import build_graph
from core.persistence.database import DatabaseManager

logger = logging.getLogger(__name__)

_NODE_EVENTS: dict[str, tuple[str, str]] = {
    "ingest_incident": ("incident_ingested", "Incident ingested and validated"),
    "identify_service": ("service_identified", "Service identified"),
    "retrieve_knowledge": ("knowledge_retrieved", "Organizational knowledge retrieved (RAG)"),
    "resolve_contract": ("contract_resolved", "Operational contract resolved"),
    "plan_remediation": ("plan_proposed", "Remediation plan generated"),
    "evaluate_guardrails": ("guardrail_evaluated", "Guardrails evaluated"),
    "increment_retry": ("retry", "Re-planning after guardrail rejection"),
    "evaluate_risk": ("risk_evaluated", "Risk assessed"),
    "request_human_approval": ("approval_recorded", "Human decision recorded"),
    "execute_actions": ("actions_executed", "Actions executed via MCP boundary"),
    "validate_postconditions": ("postconditions_validated", "Postconditions validated"),
    "handle_escalation": ("escalated", "Incident escalated to a human operator"),
    "finalize": ("finalized", "Workflow finalized"),
}


async def _emit(incident_id: str, node_name: str, update: dict[str, Any]) -> None:
    if node_name.startswith("__"):
        return

    event_type, message = _NODE_EVENTS.get(node_name, (node_name, f"Step '{node_name}' completed"))
    data: dict[str, Any] = {}
    terminal = False

    if node_name == "plan_remediation":
        plan = update.get("proposed_plan") or {}
        actions = plan.get("actions", [])
        data = {"summary": plan.get("summary"), "action_count": len(actions)}
        if plan.get("summary"):
            message = f"Plan generated: {plan['summary']} ({len(actions)} action(s))"
    elif node_name == "evaluate_guardrails":
        status = update.get("guardrail_status")
        violations = update.get("violations", [])
        data = {"status": status, "violations": violations}
        message = f"Guardrails {status}" + (f" - {len(violations)} violation(s)" if violations else "")
    elif node_name == "evaluate_risk":
        data = {"risk_level": update.get("risk_level"), "approval_required": update.get("approval_required")}
        message = f"Risk assessed: {update.get('risk_level')}"
    elif node_name == "validate_postconditions":
        results = update.get("postcondition_results", [])
        passed = all(r.get("passed") for r in results) if results else True
        data = {"results": results, "all_passed": passed}
        message = "Postconditions " + ("passed" if passed else "failed")
    elif node_name == "execute_actions":
        history = update.get("execution_history", [])
        data = {"executed": len(history)}
        message = f"Executed {len(history)} action(s) via MCP"
    elif node_name == "finalize":
        final_status = update.get("final_status")
        data = {"final_status": final_status}
        message = f"Workflow finalized: {final_status}"
        terminal = True

    await get_event_bus().publish(
        WorkflowEvent(
            incident_id=incident_id,
            type=event_type,
            message=message,
            node=node_name,
            data=data,
            terminal=terminal,
        )
    )


async def _persist_terminal(db: DatabaseManager, graph: Any, config: dict[str, Any], incident_id: str) -> None:
    snapshot = await graph.aget_state(config)
    values = snapshot.values if snapshot else {}

    if snapshot and snapshot.next:
        # Paused at the approval interrupt: record a pending-approval row and
        # tell the UI. Supersede any stale pending row for this incident first.
        await db.resolve_approval(incident_id, "superseded")
        await db.create_pending_approval(
            incident_id=incident_id,
            thread_id=incident_id,
            plan=values.get("proposed_plan") or {},
            context={
                "service": values.get("service_name"),
                "risk_level": values.get("risk_level"),
                "violations": values.get("violations", []),
            },
        )
        await db.upsert_incident(incident_id, values.get("incident", {}), "AWAITING_APPROVAL")
        await get_event_bus().publish(
            WorkflowEvent(
                incident_id=incident_id,
                type="approval_required",
                message="Human approval required before execution",
                node="request_human_approval",
                data={
                    "service": values.get("service_name"),
                    "risk_level": values.get("risk_level"),
                    "violations": values.get("violations", []),
                    "proposed_plan": values.get("proposed_plan"),
                },
            )
        )
        return

    # Terminal — record final status and flush the audit trail exactly once.
    final_status = values.get("final_status", "FAILED")
    await db.upsert_incident(incident_id, values.get("incident", {}), final_status)

    for entry in values.get("audit_trail", []):
        try:
            await db.insert_audit_event(AuditEvent(**entry))
        except Exception:
            logger.exception("Failed to persist audit event for %s", incident_id)


async def run_workflow(
    db: DatabaseManager,
    incident_id: str,
    incident_data: dict[str, Any] | None = None,
    resume: str | None = None,
    actor: str | None = None,
) -> None:
    """Run (or resume) the orchestration workflow, streaming events + persisting."""
    graph = build_graph()
    config = {"configurable": {"thread_id": incident_id}}

    if resume is not None:
        graph_input: Any = Command(resume={"decision": resume, "actor": actor or "unknown"})
        await db.resolve_approval(incident_id, resume, resolved_by=actor)
    else:
        graph_input = {"incident": incident_data}
        await db.upsert_incident(incident_id, incident_data or {}, "IN_PROGRESS", submitted_by=actor)
        await get_event_bus().publish(
            WorkflowEvent(
                incident_id=incident_id,
                type="workflow_started",
                message="Autonomous remediation workflow started",
                node="start",
            )
        )

    try:
        async for chunk in graph.astream(graph_input, config=config, stream_mode="updates"):
            for node_name, update in chunk.items():
                await _emit(incident_id, node_name, update or {})
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Workflow failed for %s", incident_id)
        await db.upsert_incident(incident_id, incident_data or {}, "FAILED")
        await get_event_bus().publish(
            WorkflowEvent(incident_id=incident_id, type="error", message=f"Workflow error: {exc}", terminal=True)
        )
        return

    await _persist_terminal(db, graph, config, incident_id)
