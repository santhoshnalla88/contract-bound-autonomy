"""MCP client — dispatches guardrail-approved actions to an execution driver.

The client enforces an execution allowlist (defence in depth on top of the
contract guardrails) and wraps every result in an ``ExecutionResult``. The
actual side effects are delegated to a pluggable :class:`ExecutionDriver`
(mock or Kubernetes), so the LLM never touches infrastructure directly.

Per-incident isolation: mock runs get their own driver instance (consistent
cluster state across execute → postcondition within one incident, no shared
global mutation); the stateless Kubernetes driver is shared across incidents.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.config import get_settings
from core.enums import ActionType
from core.models import ExecutionResult, NormalizedAction
from core.execution.drivers import ExecutionDriver, create_driver

logger = logging.getLogger(__name__)


class MCPClient:
    """Dispatches NormalizedActions to an execution driver behind an allowlist."""

    ALLOWLIST: frozenset[ActionType] = frozenset({
        ActionType.RESTART_PODS,
        ActionType.SCALE_DEPLOYMENT,
        ActionType.ROLLBACK_DEPLOYMENT,
        ActionType.BLOCK_MERCHANT,
        ActionType.REFUND_TRANSACTION,
        ActionType.REROUTE_GATEWAY,
        # Target-neutral verbs (servers / batch / cloud / on-prem).
        ActionType.RUN_COMMAND,
        ActionType.RESTART_SERVICE,
        ActionType.START_SERVICE,
        ActionType.STOP_SERVICE,
        ActionType.RUN_BATCH_JOB,
        ActionType.HTTP_REQUEST,
    })

    def __init__(self, driver: ExecutionDriver | None = None) -> None:
        self._driver = driver or create_driver(get_settings())
        self._execution_count = 0
        logger.info("MCPClient initialised (driver=%s)", type(self._driver).__name__)

    def execute_action(self, action: NormalizedAction) -> ExecutionResult:
        if action.action not in self.ALLOWLIST:
            logger.warning("Action '%s' is not in the execution allowlist", action.action)
            return ExecutionResult(
                action=action.action.value,
                success=False,
                output={},
                error=f"Action '{action.action.value}' is not in the execution allowlist. "
                      f"Allowed: {sorted(a.value for a in self.ALLOWLIST)}",
                timestamp=datetime.now(timezone.utc),
            )
        try:
            result = self._dispatch(action)
            self._execution_count += 1
            success = result.get("success", True)
            logger.info(
                "Executed %s on %s — success=%s (execution #%d)",
                action.action.value, action.target, success, self._execution_count,
            )
            return ExecutionResult(
                action=action.action.value,
                success=success,
                output=result,
                error=result.get("error"),
                timestamp=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.exception("Execution of %s failed", action.action.value)
            return ExecutionResult(
                action=action.action.value, success=False, output={}, error=str(exc),
                timestamp=datetime.now(timezone.utc),
            )

    def _dispatch(self, action: NormalizedAction) -> dict[str, Any]:
        return self._driver.execute(action.action.value, action.target, action.parameters)

    def get_current_metrics(self, service: str) -> dict[str, Any]:
        return self._driver.get_metrics(service)

    def get_current_status(self, service: str) -> dict[str, Any]:
        return self._driver.get_service_status(service)

    @property
    def driver(self) -> ExecutionDriver:
        return self._driver

    @property
    def execution_count(self) -> int:
        return self._execution_count


# ---------------------------------------------------------------------------
# Per-incident client registry
# ---------------------------------------------------------------------------
_incident_clients: dict[str, MCPClient] = {}
_shared_k8s_client: MCPClient | None = None


def get_mcp_client(incident_id: str | None = None) -> MCPClient:
    """Return an MCP client scoped appropriately for the execution backend.

    - Kubernetes backend: one shared, stateless client (the cluster is the state).
    - Mock backend: one client per incident so execute + postcondition observe
      the same simulated cluster without cross-incident interference.
    """
    settings = get_settings()
    if settings.execution_backend == "kubernetes":
        global _shared_k8s_client
        if _shared_k8s_client is None:
            _shared_k8s_client = MCPClient()
        return _shared_k8s_client

    key = incident_id or "__default__"
    client = _incident_clients.get(key)
    if client is None:
        client = MCPClient()
        _incident_clients[key] = client
    return client


def release_mcp_client(incident_id: str) -> None:
    """Drop an incident's mock client once its workflow is terminal."""
    _incident_clients.pop(incident_id, None)


def reset_mcp_clients() -> None:
    """Clear all cached clients — primarily for tests."""
    global _shared_k8s_client
    _incident_clients.clear()
    _shared_k8s_client = None
