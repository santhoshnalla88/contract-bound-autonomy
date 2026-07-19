"""Execution drivers behind the MCP boundary.

The MCP client dispatches guardrail-approved actions to an ``ExecutionDriver``.
Drivers are the platform's **hands** — the only place that actually touches a
target system. Everything upstream (planning, contracts, policy, risk, approval)
is target-agnostic, so integrating a *new kind of target* — a Linux/Windows
server, a batch scheduler, an on-prem app, a cloud/SaaS API — means writing one
driver and registering it here. No changes to the governance core.

Built-in backends:

* ``mock``       — simulated state (default; safe for dev/test/CI). Handles both
  the Kubernetes verbs and the target-neutral verbs (run_command, restart_service,
  run_batch_job, http_request, …) so any contract can be exercised offline.
* ``kubernetes`` — real restarts/scale/rollback via the Kubernetes API.

Register your own without editing this file::

    from core.execution.drivers import register_driver, ExecutionDriver

    class ServiceNowDriver(ExecutionDriver): ...

    register_driver("servicenow", lambda s: ServiceNowDriver(...))

Then set ``EXECUTION_BACKEND=servicenow``. Selection is by name so a real target
is only ever touched when explicitly configured.
"""

from __future__ import annotations

from typing import Callable

from core.config import Settings
from core.execution.drivers.base import ExecutionDriver
from core.execution.drivers.mock import MockDriver

# name -> factory(settings) -> ExecutionDriver
DriverFactory = Callable[[Settings], ExecutionDriver]
_REGISTRY: dict[str, DriverFactory] = {}


def register_driver(name: str, factory: DriverFactory) -> None:
    """Register (or override) an execution backend under ``name``.

    ``factory`` receives the app ``Settings`` and returns a driver instance.
    Call this at import time from your app/worker startup or a plugin module.
    """
    _REGISTRY[name.lower()] = factory


def available_backends() -> list[str]:
    """Names an operator may set ``EXECUTION_BACKEND`` to."""
    return sorted(_REGISTRY)


def create_driver(settings: Settings) -> ExecutionDriver:
    """Instantiate the configured execution driver (``EXECUTION_BACKEND``)."""
    name = (settings.execution_backend or "mock").lower()
    factory = _REGISTRY.get(name)
    if factory is None:
        raise ValueError(
            f"Unknown EXECUTION_BACKEND '{settings.execution_backend}'. "
            f"Registered backends: {available_backends()}. "
            f"Register one with core.execution.drivers.register_driver(...)."
        )
    return factory(settings)


def _kubernetes_factory(settings: Settings) -> ExecutionDriver:
    # Imported lazily so the kubernetes client is only required when selected.
    from examples.incident_commander.drivers.kubernetes import KubernetesDriver

    return KubernetesDriver(
        namespace=settings.k8s_namespace,
        in_cluster=settings.k8s_in_cluster,
        kubeconfig=settings.k8s_kubeconfig or None,
    )


# Built-in backends.
register_driver("mock", lambda _s: MockDriver())
register_driver("kubernetes", _kubernetes_factory)


__all__ = [
    "ExecutionDriver",
    "MockDriver",
    "create_driver",
    "register_driver",
    "available_backends",
]
