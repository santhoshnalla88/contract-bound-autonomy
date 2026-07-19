"""Mock execution driver — simulated cluster state (default backend).

Wraps the pure functions in :mod:`core.execution.tools` with a per-instance
``MockInfrastructureState`` so each incident's MCP client observes a consistent
cluster across execute → postcondition steps (no shared global mutation).
"""

from __future__ import annotations

from typing import Any

from core.execution.drivers.base import ExecutionDriver
from core.execution.tools import (
    MockInfrastructureState,
    get_metrics,
    get_service_status,
    restart_pods,
    rollback_deployment,
    scale_deployment,
)


class MockDriver(ExecutionDriver):
    def __init__(self) -> None:
        self._state = MockInfrastructureState()

    # Target-neutral verbs the mock simulates so ANY workload's contract
    # (server/batch/cloud/on-prem) can be exercised in dev/test/CI without a
    # real backend. A real deployment swaps in a driver that actually performs them.
    _GENERIC_VERBS = frozenset({
        "run_command", "restart_service", "start_service",
        "stop_service", "run_batch_job", "http_request",
    })

    def execute(self, action: str, target: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if action == "restart_pods":
            return self.restart_pods(target, int(parameters.get("count", 1)))
        if action == "scale_deployment":
            return self.scale_deployment(target, int(parameters.get("replicas", 1)))
        if action == "rollback_deployment":
            return self.rollback_deployment(target, int(parameters.get("revision", 1)))
        if action in self._GENERIC_VERBS:
            return {
                "success": True,
                "action": action,
                "target": target,
                "parameters": parameters,
                "simulated": True,
                "message": f"[mock] {action} on '{target}' completed",
            }
        return {"success": False, "error": f"Unknown mock action: {action}"}

    def restart_pods(self, deployment: str, count: int) -> dict[str, Any]:
        return restart_pods(deployment, count, self._state)

    def scale_deployment(self, deployment: str, replicas: int) -> dict[str, Any]:
        return scale_deployment(deployment, replicas, self._state)

    def rollback_deployment(self, deployment: str, revision: int) -> dict[str, Any]:
        return rollback_deployment(deployment, revision, self._state)

    def get_service_status(self, service: str) -> dict[str, Any]:
        return get_service_status(service, self._state)

    def get_metrics(self, service: str) -> dict[str, Any]:
        return get_metrics(service, self._state)
