"""Conditional routing functions for the LangGraph workflow.

Each routing function takes the current OrchestratorState and returns
a string key that maps to the next node via add_conditional_edges.

Uses Literal return types for LangGraph 1.2.x validation.
"""

from typing import Literal

from core.orchestration.state import OrchestratorState


def route_after_contract(state: OrchestratorState) -> Literal["proceed", "escalate"]:
    """Route based on whether an operational contract was resolved.

    A missing contract means the agent has no authority to act autonomously,
    so the incident is escalated to a human instead of planning remediation.
    """
    if state.get("retrieved_contract"):
        return "proceed"
    return "escalate"


def route_after_guardrail(state: OrchestratorState) -> Literal["approved", "rejected"]:
    """Route based on guardrail evaluation result.

    APPROVED → proceed to risk evaluation.
    REJECTED → increment retry counter.
    """
    if state.get("guardrail_status") == "APPROVED":
        return "approved"
    return "rejected"


def route_after_rejection(state: OrchestratorState) -> Literal["retry", "escalate"]:
    """Route based on retry count after a plan rejection.

    If retry_count < max_retries (3) → retry planning with violation feedback.
    If retry_count >= max_retries → escalate to human.
    """
    retry_count = state.get("retry_count", 0)
    # Max retries is defined in the contract, default 3
    contract = state.get("retrieved_contract", {})
    max_retries = contract.get("retry_policy", {}).get("max_plan_retries", 3)

    if retry_count < max_retries:
        return "retry"
    return "escalate"


def route_after_risk(state: OrchestratorState) -> Literal["execute", "human_approval"]:
    """Route based on risk evaluation.

    LOW/MEDIUM risk without approval requirement → execute automatically.
    HIGH/CRITICAL risk or approval_required → human approval needed.
    """
    approval_required = state.get("approval_required", False)
    risk_level = state.get("risk_level", "LOW")

    if approval_required or risk_level in ("HIGH", "CRITICAL"):
        return "human_approval"
    return "execute"


def route_after_human(state: OrchestratorState) -> Literal["execute", "denied"]:
    """Route based on human decision.

    APPROVED → proceed to execution.
    REJECTED → finalize as denied.
    """
    decision = state.get("human_decision", "")
    if decision == "APPROVED":
        return "execute"
    return "denied"


def route_after_postcondition(state: OrchestratorState) -> Literal["success", "retry", "escalate"]:
    """Route based on postcondition validation results.

    All passed → success.
    Some failed and retries available → retry with new plan.
    Some failed and retries exhausted → escalate.
    """
    results = state.get("postcondition_results", [])
    all_passed = all(r.get("passed", False) for r in results) if results else False

    if all_passed:
        return "success"

    # Check if we can retry
    retry_count = state.get("retry_count", 0)
    contract = state.get("retrieved_contract", {})
    max_retries = contract.get("retry_policy", {}).get("max_plan_retries", 3)

    if retry_count < max_retries:
        return "retry"
    return "escalate"
