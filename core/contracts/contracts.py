"""Operational Contract model and loader.

Contracts are the hard autonomy boundaries of the system.
They are loaded DETERMINISTICALLY from the filesystem — never from
RAG vector search — to prevent semantic drift and ensure exact matching.

Design decision: contracts use JSON for machine-readability.
The ContractLoader resolves by (service, environment) with optional version pinning.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from core.models import PostconditionRule


class ContractLimits(BaseModel):
    """Hard numerical limits on autonomous actions."""

    max_pod_restarts_per_incident: int = Field(default=2, ge=0)
    max_replicas: int = Field(default=10, ge=1)
    max_scale_up_percentage: int = Field(default=200, ge=100)


class AvailabilityConstraints(BaseModel):
    """Minimum availability requirements during remediation."""

    minimum_available_replicas: int = Field(default=2, ge=0)
    preserve_active_connections: bool = Field(default=True)
    max_unavailability_percentage: int = Field(default=25, ge=0, le=100)


class RetryPolicy(BaseModel):
    """Retry policy for plan generation."""

    max_plan_retries: int = Field(default=3, ge=1)


class OperationalContract(BaseModel):
    """Machine-readable operational boundaries for a service.

    This is the authority that determines what the agent is ALLOWED to do.
    The LLM can propose anything; the contract decides what passes.

    Fields:
        contract_id: Unique identifier for this contract version
        service: Target service name
        environment: Target environment
        version: Semantic version for contract integrity tracking
        allowed_actions: Allowlist of actions the agent may execute
        forbidden_actions: Blocklist of absolutely prohibited actions
        limits: Numerical limits on action parameters
        availability_constraints: Minimum availability during remediation
        approval_requirements: Map of action → requires_human_approval
        retry_policy: How many times the planner can retry after rejection
        postconditions: Success criteria that must be met after execution
    """

    contract_id: str
    service: str
    environment: str
    version: str = "1.0.0"

    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)

    limits: ContractLimits = Field(default_factory=ContractLimits)
    availability_constraints: AvailabilityConstraints = Field(
        default_factory=AvailabilityConstraints
    )

    approval_requirements: dict[str, bool] = Field(default_factory=dict)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

    postconditions: list[str] = Field(default_factory=list)

    # Optional per-service adaptive rules (context → narrow the contract).
    # Each entry matches core.contracts.adaptive.AdaptiveRule. Config-driven so an
    # organization tunes autonomy per service WITHOUT code changes.
    adaptive_rules: list[dict[str, Any]] = Field(default_factory=list)

    def get_postcondition_rules(self) -> list[PostconditionRule]:
        """Parse string postconditions into structured evaluable rules."""
        rules = []
        for condition in self.postconditions:
            try:
                rules.append(PostconditionRule.from_string(condition))
            except ValueError:
                continue
        return rules

    def is_action_allowed(self, action: str) -> bool:
        """Check if an action is in the allowlist."""
        return action in self.allowed_actions

    def is_action_forbidden(self, action: str) -> bool:
        """Check if an action is in the blocklist."""
        return action in self.forbidden_actions

    def requires_approval(self, action: str) -> bool:
        """Check if an action requires human approval per contract."""
        return self.approval_requirements.get(action, False)

    def to_summary(self) -> str:
        """Generate a human-readable summary for the planner agent context."""
        return (
            f"Contract: {self.contract_id} v{self.version}\n"
            f"Service: {self.service} ({self.environment})\n"
            f"Allowed actions: {', '.join(self.allowed_actions)}\n"
            f"Forbidden actions: {', '.join(self.forbidden_actions)}\n"
            f"Max pod restarts: {self.limits.max_pod_restarts_per_incident}\n"
            f"Max replicas: {self.limits.max_replicas}\n"
            f"Min available replicas: {self.availability_constraints.minimum_available_replicas}\n"
            f"Preserve active connections: {self.availability_constraints.preserve_active_connections}\n"
            f"Postconditions: {'; '.join(self.postconditions)}"
        )


class ContractLoader:
    """Loads operational contracts from the filesystem.

    Design decision: Contracts are loaded deterministically by exact
    (service, environment) match. This is NOT a vector search — contracts
    must be precise, versioned, and auditable.

    The loader searches the contracts directory for JSON files matching
    the service name pattern.
    """

    def __init__(self, contracts_dir: Path) -> None:
        self.contracts_dir = contracts_dir

    def load(
        self,
        service: str,
        environment: str,
        version: Optional[str] = None,
    ) -> OperationalContract:
        """Load a contract for the given service and environment.

        Args:
            service: Service name (e.g. 'inventory-service')
            environment: Environment (e.g. 'production')
            version: Optional exact version to match

        Returns:
            The matching OperationalContract

        Raises:
            FileNotFoundError: If no matching contract file exists
            ValueError: If the contract doesn't match the requested parameters
        """
        contract_file = self.contracts_dir / f"{service}-contract.json"

        if not contract_file.exists():
            raise FileNotFoundError(
                f"No contract found for service '{service}' at {contract_file}"
            )

        with open(contract_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        contract = OperationalContract(**data)

        # Verify the loaded contract matches the request
        if contract.service != service:
            raise ValueError(
                f"Contract service mismatch: expected '{service}', got '{contract.service}'"
            )
        if contract.environment != environment:
            raise ValueError(
                f"Contract environment mismatch: expected '{environment}', "
                f"got '{contract.environment}'"
            )
        if version and contract.version != version:
            raise ValueError(
                f"Contract version mismatch: expected '{version}', got '{contract.version}'"
            )

        return contract

    def list_contracts(self) -> list[str]:
        """List all available contract files."""
        if not self.contracts_dir.exists():
            return []
        return [f.stem for f in self.contracts_dir.glob("*-contract.json")]
