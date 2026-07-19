"""Incident submission, querying, and real-time event routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.identity.deps import CurrentUser, require_operator, require_viewer
from examples.incident_commander.domain.models import Incident
from core.events import get_event_bus
from core.orchestration.builder import build_graph
from apps.worker.queue import submit_workflow

router = APIRouter(prefix="/api/incidents", tags=["Incidents"])


class IncidentResponse(BaseModel):
    incident_id: str
    message: str
    thread_id: str


@router.get("")
async def list_incidents(request: Request, _: CurrentUser = Depends(require_viewer)):
    """List all known incidents for the operations dashboard."""
    db = request.app.state.db
    incidents = await db.list_incidents()
    return {"incidents": incidents, "count": len(incidents)}


@router.post("", response_model=IncidentResponse, status_code=202)
async def submit_incident(
    incident: Incident, request: Request, user: CurrentUser = Depends(require_operator)
):
    """Submit a new incident for autonomous remediation (operator+)."""
    db = request.app.state.db
    thread_id = incident.incident_id

    await submit_workflow(
        db=db,
        arq=getattr(request.app.state, "arq", None),
        incident_id=thread_id,
        incident_data=incident.model_dump(mode="json"),
        actor=user.email,
    )

    return IncidentResponse(
        incident_id=incident.incident_id,
        message="Incident accepted. Remediation workflow started.",
        thread_id=thread_id,
    )


@router.get("/{incident_id}")
async def get_incident_status(incident_id: str, _: CurrentUser = Depends(require_viewer)):
    """Get the current status and key decision state of an incident workflow."""
    graph = build_graph()
    config = {"configurable": {"thread_id": incident_id}}

    try:
        state = await graph.aget_state(config)
        if not state or not state.values:
            raise HTTPException(status_code=404, detail="Incident not found or no state available.")

        values = state.values
        next_nodes = list(state.next) if state.next else []
        awaiting_approval = "request_human_approval" in next_nodes

        if values.get("final_status"):
            status = values["final_status"]
        elif awaiting_approval:
            status = "AWAITING_APPROVAL"
        else:
            status = "IN_PROGRESS"

        return {
            "incident_id": incident_id,
            "status": status,
            "current_node": next_nodes[0] if next_nodes else "COMPLETED",
            "awaiting_approval": awaiting_approval,
            "retry_count": values.get("retry_count", 0),
            "guardrail_status": values.get("guardrail_status"),
            "violations": values.get("violations", []),
            "risk_level": values.get("risk_level"),
            "approval_required": values.get("approval_required", False),
            "approved_by": values.get("approved_by"),
            "service": values.get("service_name"),
            "incident": values.get("incident"),
            "proposed_plan": values.get("proposed_plan"),
            "normalized_actions": values.get("normalized_actions", []),
            "retrieved_contract": values.get("retrieved_contract"),
            "retrieved_documents": values.get("retrieved_documents", []),
            "execution_history": values.get("execution_history", []),
            "postcondition_results": values.get("postcondition_results", []),
            "final_status": values.get("final_status"),
            "executive_summary": values.get("executive_summary"),
            "compensation_history": values.get("compensation_history", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{incident_id}/audit")
async def get_incident_audit(
    incident_id: str, request: Request, _: CurrentUser = Depends(require_viewer)
):
    """Get the full audit trail for an incident (DB first, graph state fallback)."""
    db = request.app.state.db
    audit_trail = await db.get_audit_trail(incident_id)

    if audit_trail:
        return {"audit_trail": audit_trail, "source": "database"}

    graph = build_graph()
    config = {"configurable": {"thread_id": incident_id}}
    state = await graph.aget_state(config)
    if state and state.values:
        return {"audit_trail": state.values.get("audit_trail", []), "source": "state"}

    raise HTTPException(status_code=404, detail="No audit trail found for incident.")


@router.get("/{incident_id}/events")
async def stream_incident_events(
    incident_id: str, request: Request, _: CurrentUser = Depends(require_viewer)
):
    """Server-Sent Events stream of real-time workflow events for an incident.

    Auth is via the ``token`` query parameter because ``EventSource`` cannot set
    headers. Replays history, then tails live events until disconnect/terminal.
    """
    bus = get_event_bus()

    async def event_generator():
        subscription = bus.subscribe(incident_id, replay=True)
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await subscription.get(timeout=15.0)
                if event is None:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
                if event.terminal:
                    break
        finally:
            await subscription.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
