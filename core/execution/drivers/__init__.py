"""Execution drivers behind the MCP boundary.

The MCP client dispatches guardrail-approved actions to an ``ExecutionDriver``.
Two implementations exist:

* :class:`MockDriver` — simulated cluster state (default; safe for dev/test/CI).
* :class:`KubernetesDriver` — performs real restarts/scale/rollback against a
  cluster via the Kubernetes API.

Selection is by ``EXECUTION_BACKEND`` so a real cluster is only ever touched
when explicitly configured.
"""

from __future__ import annotations

from core.config import Settings
from core.execution.drivers.base import ExecutionDriver
from core.execution.drivers.mock import MockDriver


def create_driver(settings: Settings) -> ExecutionDriver:
    """Instantiate the configured execution driver."""
    if settings.execution_backend == "kubernetes":
        from examples.incident_commander.drivers.kubernetes import KubernetesDriver

        return KubernetesDriver(
            namespace=settings.k8s_namespace,
            in_cluster=settings.k8s_in_cluster,
            kubeconfig=settings.k8s_kubeconfig or None,
        )
    return MockDriver()


__all__ = ["ExecutionDriver", "MockDriver", "create_driver"]
