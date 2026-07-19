"""Execution driver protocol.

Every driver takes an incident-scoped ``target`` (the service/deployment) and
returns a plain result dict with at least ``action``, ``success``, and either
result fields or an ``error``. Keeping the surface tiny means the guardrail
engine and MCP client are identical regardless of backend.
"""

from __future__ import annotations

import abc
from typing import Any


class ExecutionDriver(abc.ABC):
    """Abstract execution backend for remediation actions."""

    @abc.abstractmethod
    def execute(self, action: str, target: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Execute a domain-specific action."""
        ...

    @abc.abstractmethod
    def get_service_status(self, service: str) -> dict[str, Any]: ...

    @abc.abstractmethod
    def get_metrics(self, service: str) -> dict[str, Any]: ...
