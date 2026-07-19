"""Deterministic guardrail validator functions.

Each validator checks a specific aspect of contract compliance and returns
a list of human-readable violation strings. An empty list means the check
passed. Validators are pure functions with no side effects — they receive
all required state as arguments.

These validators form the core deterministic enforcement layer. They are
called in priority order by the GuardrailEngine and their results are
aggregated into a final GuardrailResult.
"""

from __future__ import annotations

from core.enums import ActionType
from core.models import NormalizedAction
from core.contracts import OperationalContract


def validate_action_allowed(
    action: NormalizedAction,
    contract: OperationalContract,
) -> list[str]:
    """Check if the action is in the contract's allowlist.

    An action that is not explicitly allowed is rejected. This implements
    a default-deny posture: only actions on the allowlist may proceed.

    Args:
        action: The normalized action to validate.
        contract: The operational contract defining boundaries.

    Returns:
        A list of violation strings. Empty if the action is allowed.
    """
    if not contract.is_action_allowed(action.action.value):
        return [
            f"Action '{action.action.value}' is not in the allowed actions list. "
            f"Allowed: {contract.allowed_actions}"
        ]
    return []


def validate_action_not_forbidden(
    action: NormalizedAction,
    contract: OperationalContract,
) -> list[str]:
    """Check if the action is on the contract's forbidden list.

    Forbidden actions are an absolute blocklist — they are rejected
    immediately regardless of any other conditions.

    Args:
        action: The normalized action to validate.
        contract: The operational contract defining boundaries.

    Returns:
        A list of violation strings. Empty if the action is not forbidden.
    """
    if contract.is_action_forbidden(action.action.value):
        return [
            f"Action '{action.action.value}' is explicitly forbidden by the contract."
        ]
    return []


def validate_limits(
    action: NormalizedAction,
    contract: OperationalContract,
    execution_history: list[dict],
) -> list[str]:
    """Validate action parameters against contract numerical limits.

    Checks action-specific limits:
    - restart_pods: total restarts (history + requested) <= max_pod_restarts_per_incident
    - scale_deployment: requested replicas <= max_replicas

    Args:
        action: The normalized action to validate.
        contract: The operational contract defining limits.
        execution_history: List of previously executed actions in this
            incident, each as a dict with at least an 'action' key and
            optionally a 'parameters' dict with a 'count' field.

    Returns:
        A list of violation strings. Empty if all limits are satisfied.
    """
    violations: list[str] = []
    limits = contract.limits

    if action.action == ActionType.RESTART_PODS:
        # Count prior restarts from execution history
        prior_restarts = sum(
            entry.get("parameters", {}).get("count", 1)
            for entry in execution_history
            if entry.get("action") == ActionType.RESTART_PODS.value
        )
        requested_count = action.parameters.get("count", 1)
        total = prior_restarts + requested_count

        if total > limits.max_pod_restarts_per_incident:
            violations.append(
                f"Restart limit exceeded: requesting {requested_count} restart(s) "
                f"with {prior_restarts} prior restart(s) (total {total}) "
                f"exceeds max of {limits.max_pod_restarts_per_incident} per incident."
            )

    elif action.action == ActionType.SCALE_DEPLOYMENT:
        requested_replicas = action.parameters.get("replicas", 0)

        if requested_replicas > limits.max_replicas:
            violations.append(
                f"Scale limit exceeded: requesting {requested_replicas} replicas "
                f"exceeds maximum of {limits.max_replicas}."
            )

        # Also check max_scale_up_percentage if current replicas are known
        current_replicas = action.parameters.get("current_replicas")
        if current_replicas is not None and current_replicas > 0:
            scale_percentage = (requested_replicas / current_replicas) * 100
            if scale_percentage > limits.max_scale_up_percentage:
                violations.append(
                    f"Scale-up percentage exceeded: scaling from {current_replicas} "
                    f"to {requested_replicas} ({scale_percentage:.0f}%) exceeds "
                    f"maximum of {limits.max_scale_up_percentage}%."
                )

    return violations


def validate_availability(
    action: NormalizedAction,
    contract: OperationalContract,
    current_metrics: dict,
) -> list[str]:
    """Validate that the action won't violate availability constraints.

    Checks:
    - For restart_pods: ensures that restarting pods won't drop below
      minimum_available_replicas.
    - For any action: respects preserve_active_connections when active
      connections exist.

    Args:
        action: The normalized action to validate.
        contract: The operational contract defining availability constraints.
        current_metrics: Dict with current system metrics. Expected keys:
            - 'total_pods': int — current total pod count
            - 'healthy_pods': int — current healthy pod count
            - 'active_connections': bool — whether active connections exist

    Returns:
        A list of violation strings. Empty if availability is maintained.
    """
    violations: list[str] = []
    constraints = contract.availability_constraints

    if action.action == ActionType.RESTART_PODS:
        total_pods = current_metrics.get("total_pods", 0)
        restart_count = action.parameters.get("count", 1)
        remaining_pods = total_pods - restart_count

        if remaining_pods < constraints.minimum_available_replicas:
            violations.append(
                f"Availability violation: restarting {restart_count} pod(s) from "
                f"{total_pods} total would leave {remaining_pods} available, "
                f"below minimum of {constraints.minimum_available_replicas}."
            )

        # Check max unavailability percentage
        if total_pods > 0:
            unavailability_pct = (restart_count / total_pods) * 100
            if unavailability_pct > constraints.max_unavailability_percentage:
                violations.append(
                    f"Unavailability percentage exceeded: restarting {restart_count} "
                    f"of {total_pods} pods ({unavailability_pct:.0f}%) exceeds "
                    f"maximum of {constraints.max_unavailability_percentage}%."
                )

    # Check active connection preservation for disruptive actions
    if constraints.preserve_active_connections:
        has_active_connections = current_metrics.get("active_connections", False)
        disruptive_actions = {
            ActionType.RESTART_PODS,
            ActionType.ROLLBACK_DEPLOYMENT,
        }

        if has_active_connections and action.action in disruptive_actions:
            violations.append(
                f"Active connection preservation violated: action '{action.action.value}' "
                f"would disrupt active connections. Contract requires connection "
                f"draining before disruptive operations."
            )

    return violations


def validate_approval_required(
    action: NormalizedAction,
    contract: OperationalContract,
) -> list[str]:
    """Check if the action requires human approval.

    This validator does not produce rejection violations — approval
    requirements are handled separately by the engine to set the
    approval_required flag on the GuardrailResult. The actual approval
    check is done via contract.requires_approval().

    This function exists in the validator chain for extensibility and
    to maintain a uniform validator interface.

    Args:
        action: The normalized action to validate.
        contract: The operational contract defining approval requirements.

    Returns:
        Always returns an empty list. Approval is tracked as metadata,
        not as a violation.
    """
    # Approval requirements don't generate violations — they're tracked
    # as a separate flag in GuardrailResult. The engine uses
    # contract.requires_approval() directly to set approval_required.
    return []
