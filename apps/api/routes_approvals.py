"""Human-in-the-loop approval routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.identity.deps import CurrentUser, require_approver, require_viewer
from core.orchestration.builder import build_graph
from apps.worker.queue import submit_workflow

router = APIRouter(prefix="/api/approvals", tags=["Approvals"])


class ApprovalDecision(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")
    reasoning: str = Field(default="")


@router.get("/pending")
async def list_pending_approvals(request: Request, _: CurrentUser = Depends(require_viewer)):
    """List incidents awaiting human approval (from the approvals table)."""
    db = request.app.state.db
    rows = await db.get_pending_approvals()
    pending = [
        {
            "incident_id": r["incident_id"],
            "service": r["context"].get("service"),
            "risk_level": r["context"].get("risk_level"),
            "violations": r["context"].get("violations", []),
            "proposed_plan": r["plan"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {"pending": pending, "count": len(pending)}


@router.get("/{incident_id}")
async def get_approval_details(incident_id: str, _: CurrentUser = Depends(require_viewer)):
    """Get the details of a pending approval (plan, context, violations)."""
    graph = build_graph()
    config = {"configurable": {"thread_id": incident_id}}

    state = await graph.aget_state(config)
    if not state or not state.values:
        raise HTTPException(status_code=404, detail="Incident not found.")
    if not state.next or "request_human_approval" not in state.next:
        raise HTTPException(status_code=400, detail="Incident is not waiting for human approval.")

    values = state.values
    return {
        "incident_id": incident_id,
        "service": values.get("service_name"),
        "incident": values.get("incident"),
        "proposed_plan": values.get("proposed_plan"),
        "normalized_actions": values.get("normalized_actions", []),
        "violations": values.get("violations", []),
        "risk_level": values.get("risk_level"),
        "retry_count": values.get("retry_count"),
        "retrieved_contract": values.get("retrieved_contract"),
    }


@router.post("/{incident_id}")
async def submit_approval(
    incident_id: str,
    decision: ApprovalDecision,
    request: Request,
    user: CurrentUser = Depends(require_approver),
):
    """Submit a human decision to resume the paused workflow (approver+).

    The approver's identity is captured into the audit trail. Resumption runs
    on the durable queue (or inline locally) and continues streaming events.
    """
    db = request.app.state.db
    graph = build_graph()
    config = {"configurable": {"thread_id": incident_id}}

    state = await graph.aget_state(config)
    if not state or not state.values:
        raise HTTPException(status_code=404, detail="Incident not found.")
    if not state.next or "request_human_approval" not in state.next:
        raise HTTPException(status_code=400, detail="Incident is not waiting for human approval.")

    await submit_workflow(
        db=db,
        arq=getattr(request.app.state, "arq", None),
        incident_id=incident_id,
        resume=decision.decision,
        actor=user.email,
    )

    return {
        "message": f"Decision '{decision.decision}' recorded by {user.email}. Workflow resuming.",
        "incident_id": incident_id,
        "actor": user.email,
    }
