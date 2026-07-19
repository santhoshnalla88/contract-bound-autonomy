"""Mock infrastructure tools simulating real Kubernetes operations.

These functions serve dual purpose:
1. Called directly by the MCPClient for in-process execution (MVP mode)
2. Wrapped as MCP tools by the FastMCP server for subprocess execution

The MockInfrastructureState holds simulated cluster state that evolves
as remediation actions are applied, enabling realistic postcondition
evaluation without a live Kubernetes cluster.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MockInfrastructureState:
    """Simulated infrastructure state for mock Kubernetes operations.

    Holds pod inventories and service metrics that evolve realistically
    as remediation actions are applied.  The initial state represents a
    degraded inventory-service with 3 out of 5 pods unhealthy and an
    elevated error rate.
    """

    pods: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    metrics: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize default degraded state if no data was provided."""
        if not self.pods:
            self.pods = {
                "inventory-service": [
                    {"name": "inventory-service-pod-1", "status": "healthy"},
                    {"name": "inventory-service-pod-2", "status": "healthy"},
                    {"name": "inventory-service-pod-3", "status": "unhealthy"},
                    {"name": "inventory-service-pod-4", "status": "unhealthy"},
                    {"name": "inventory-service-pod-5", "status": "unhealthy"},
                ]
            }
        if not self.metrics:
            self.metrics = {
                "inventory-service": {
                    "error_rate": 12.4,
                    "healthy_pods": 2,
                    "total_pods": 5,
                    "latency_p99_ms": 850.0,
                    "requests_per_second": 120.0,
                }
            }

    def _recalculate_metrics(self, deployment: str) -> None:
        """Recalculate derived metrics from current pod state.

        After any mutation (restart, scale, rollback) the error rate and
        pod counts are recomputed so postcondition checks see consistent
        data.
        """
        pods = self.pods.get(deployment, [])
        total = len(pods)
        healthy = sum(1 for p in pods if p["status"] == "healthy")

        if deployment not in self.metrics:
            self.metrics[deployment] = {}

        health_ratio = healthy / total if total > 0 else 0.0
        # Error rate drops proportionally as pods become healthy
        base_error_rate = self.metrics[deployment].get("error_rate", 12.4)
        self.metrics[deployment].update({
            "error_rate": round(max(0.1, base_error_rate * (1 - health_ratio)), 2),
            "healthy_pods": healthy,
            "total_pods": total,
        })


def restart_pods(
    deployment: str,
    count: int,
    state: MockInfrastructureState,
) -> dict[str, Any]:
    """Restart unhealthy pods in a deployment.

    Marks up to *count* unhealthy pods as healthy, simulating a rolling
    restart.  Returns the updated pod list and summary.

    Args:
        deployment: Name of the target deployment (e.g. 'inventory-service').
        count: Maximum number of unhealthy pods to restart.
        state: The shared mock infrastructure state.

    Returns:
        Dict with 'action', 'deployment', 'restarted_count', 'pods',
        and 'timestamp' keys.
    """
    pods = state.pods.get(deployment, [])
    if not pods:
        return {
            "action": "restart_pods",
            "deployment": deployment,
            "error": f"Deployment '{deployment}' not found",
            "success": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    restarted = 0
    for pod in pods:
        if restarted >= count:
            break
        if pod["status"] == "unhealthy":
            pod["status"] = "healthy"
            restarted += 1
            logger.info("Restarted pod %s in %s", pod["name"], deployment)

    state._recalculate_metrics(deployment)

    return {
        "action": "restart_pods",
        "deployment": deployment,
        "restarted_count": restarted,
        "pods": copy.deepcopy(pods),
        "metrics": copy.deepcopy(state.metrics.get(deployment, {})),
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def scale_deployment(
    deployment: str,
    replicas: int,
    state: MockInfrastructureState,
) -> dict[str, Any]:
    """Scale a deployment to the desired replica count.

    If scaling up, new pods are added as healthy.  If scaling down, pods
    are removed from the tail of the list.

    Args:
        deployment: Name of the target deployment.
        replicas: Desired total replica count.
        state: The shared mock infrastructure state.

    Returns:
        Dict with 'action', 'deployment', 'previous_count',
        'new_count', 'pods', and 'timestamp' keys.
    """
    pods = state.pods.get(deployment, [])
    previous_count = len(pods)

    if replicas < 0:
        return {
            "action": "scale_deployment",
            "deployment": deployment,
            "error": "Replica count cannot be negative",
            "success": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    if replicas > previous_count:
        # Scale up — add healthy pods
        for i in range(previous_count + 1, replicas + 1):
            pods.append({
                "name": f"{deployment}-pod-{i}",
                "status": "healthy",
            })
        logger.info(
            "Scaled %s from %d to %d replicas", deployment, previous_count, replicas
        )
    elif replicas < previous_count:
        # Scale down — remove from the tail
        state.pods[deployment] = pods[:replicas]
        pods = state.pods[deployment]
        logger.info(
            "Scaled %s from %d to %d replicas", deployment, previous_count, replicas
        )

    state.pods[deployment] = pods
    state._recalculate_metrics(deployment)

    return {
        "action": "scale_deployment",
        "deployment": deployment,
        "previous_count": previous_count,
        "new_count": len(pods),
        "pods": copy.deepcopy(pods),
        "metrics": copy.deepcopy(state.metrics.get(deployment, {})),
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def rollback_deployment(
    deployment: str,
    revision: int,
    state: MockInfrastructureState,
) -> dict[str, Any]:
    """Roll back a deployment to a previous revision.

    Simulates a rollback by marking ALL pods as healthy (the previous
    known-good image is assumed stable).

    Args:
        deployment: Name of the target deployment.
        revision: Target revision number (for audit trail purposes).
        state: The shared mock infrastructure state.

    Returns:
        Dict with 'action', 'deployment', 'revision', 'pods', and
        'timestamp' keys.
    """
    pods = state.pods.get(deployment, [])
    if not pods:
        return {
            "action": "rollback_deployment",
            "deployment": deployment,
            "error": f"Deployment '{deployment}' not found",
            "success": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    for pod in pods:
        pod["status"] = "healthy"

    state._recalculate_metrics(deployment)
    # After rollback the error rate drops to near-zero
    if deployment in state.metrics:
        state.metrics[deployment]["error_rate"] = 0.3

    logger.info("Rolled back %s to revision %d", deployment, revision)

    return {
        "action": "rollback_deployment",
        "deployment": deployment,
        "revision": revision,
        "pods": copy.deepcopy(pods),
        "metrics": copy.deepcopy(state.metrics.get(deployment, {})),
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_service_status(
    service: str,
    state: MockInfrastructureState,
) -> dict[str, Any]:
    """Return current pod health information for a service.

    Args:
        service: Service / deployment name.
        state: The shared mock infrastructure state.

    Returns:
        Dict with pod list, healthy/unhealthy counts, and timestamp.
    """
    pods = state.pods.get(service, [])
    healthy = [p for p in pods if p["status"] == "healthy"]
    unhealthy = [p for p in pods if p["status"] == "unhealthy"]

    return {
        "action": "get_service_status",
        "service": service,
        "total_pods": len(pods),
        "healthy_pods": len(healthy),
        "unhealthy_pods": len(unhealthy),
        "pods": copy.deepcopy(pods),
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_metrics(
    service: str,
    state: MockInfrastructureState,
) -> dict[str, Any]:
    """Return current metrics for a service.

    Args:
        service: Service / deployment name.
        state: The shared mock infrastructure state.

    Returns:
        Dict with error_rate, healthy_pods, total_pods and timestamp.
    """
    metrics = state.metrics.get(service, {})
    if not metrics:
        return {
            "action": "get_metrics",
            "service": service,
            "error": f"No metrics found for service '{service}'",
            "success": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "action": "get_metrics",
        "service": service,
        "error_rate": metrics.get("error_rate", 0.0),
        "healthy_pods": metrics.get("healthy_pods", 0),
        "total_pods": metrics.get("total_pods", 0),
        "latency_p99_ms": metrics.get("latency_p99_ms"),
        "requests_per_second": metrics.get("requests_per_second"),
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
