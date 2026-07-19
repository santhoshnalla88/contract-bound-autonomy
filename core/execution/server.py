"""Mock MCP server using FastMCP.

Registers mock infrastructure tools as MCP tool endpoints.  The server
can be started via ``python -m core.execution.server`` or ``python app/mcp/server.py``
for stdio transport (used by MCP clients in subprocess mode).

Fallback: If ``fastmcp`` is not installed the module still importable
so that ``tools.py`` functions remain usable in direct / in-process mode.
"""

from __future__ import annotations

import logging
from typing import Any

from core.execution.tools import (
    MockInfrastructureState,
    get_metrics,
    get_service_status,
    restart_pods,
    rollback_deployment,
    scale_deployment,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state shared across all MCP tool invocations within this server
# process.  Each server process gets its own independent state.
# ---------------------------------------------------------------------------
_state = MockInfrastructureState()

# ---------------------------------------------------------------------------
# FastMCP server setup — wrapped in try/except so the rest of the package
# remains importable even when fastmcp is not installed.
# ---------------------------------------------------------------------------
_mcp_available = False

try:
    from fastmcp import FastMCP

    mcp = FastMCP("Remediation Tools")
    _mcp_available = True

    @mcp.tool()
    def tool_restart_pods(deployment: str, count: int) -> dict[str, Any]:
        """Restart unhealthy pods in a Kubernetes deployment.

        Args:
            deployment: Target deployment name.
            count: Maximum number of unhealthy pods to restart.
        """
        return restart_pods(deployment, count, _state)

    @mcp.tool()
    def tool_scale_deployment(deployment: str, replicas: int) -> dict[str, Any]:
        """Scale a Kubernetes deployment to the desired replica count.

        Args:
            deployment: Target deployment name.
            replicas: Desired total replica count.
        """
        return scale_deployment(deployment, replicas, _state)

    @mcp.tool()
    def tool_rollback_deployment(deployment: str, revision: int) -> dict[str, Any]:
        """Roll back a Kubernetes deployment to a previous revision.

        Args:
            deployment: Target deployment name.
            revision: Target revision number to roll back to.
        """
        return rollback_deployment(deployment, revision, _state)

    @mcp.tool()
    def tool_get_service_status(service: str) -> dict[str, Any]:
        """Get current pod health status for a service.

        Args:
            service: Service name to query.
        """
        return get_service_status(service, _state)

    @mcp.tool()
    def tool_get_metrics(service: str) -> dict[str, Any]:
        """Get current operational metrics for a service.

        Args:
            service: Service name to query.
        """
        return get_metrics(service, _state)

    logger.info("FastMCP server 'Remediation Tools' initialised with %d tools", 5)

except ImportError:
    logger.warning(
        "fastmcp is not installed — MCP server will not be available. "
        "Tools are still usable directly via core.execution.tools."
    )
    mcp = None  # type: ignore[assignment]


def get_state() -> MockInfrastructureState:
    """Return the global infrastructure state (useful for testing)."""
    return _state


def reset_state() -> None:
    """Reset the global infrastructure state to defaults."""
    global _state
    _state = MockInfrastructureState()


if __name__ == "__main__":
    if _mcp_available and mcp is not None:
        mcp.run()
    else:
        print("ERROR: fastmcp is not installed. Cannot start MCP server.")
        raise SystemExit(1)
