"""Core models for the orchestrator."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field

from core.enums import (
    ActionType,
    GuardrailStatus,
    RiskLevel,
    Severity,
    FinalStatus,
)

class BaseIncident(BaseModel):
    """Base incident model for all domains.

    ``extra='allow'`` preserves domain-specific fields (e.g. incident-commander's
    ``metrics`` / ``active_checkout_connections``, payments' ``decline_rate``) when
    the generic core reconstructs an incident from a serialized dict, so
    domain-aware agents can still read them.
    """
    model_config = {"extra": "allow"}

    incident_id: str = Field(..., description="Unique incident identifier")
    service: str = Field(..., min_length=1, description="Affected service name")
    environment: str = Field(..., description="Deployment environment (e.g. production)")
    severity: Severity
    logs: str = Field(default="", description="Raw log messages")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Generic context for domain-specific fields
    context: dict[str, Any] = Field(default_factory=dict, description="Domain-specific metrics or context")

class PlannedAction(BaseModel):
    action: str = Field(..., description="Action name (should map to ActionType)")
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(default="", description="Why this action was chosen")
    # A plain-text description is used for the LLM-facing schema: recursive object
    # schemas confuse structured output across providers. The structured
    # compensating action is derived deterministically during normalization.
    compensation: Optional[str] = Field(
        default=None, description="Optional plain-text description of how to undo this action"
    )

class RemediationPlan(BaseModel):
    summary: str = Field(..., min_length=1, description="Human-readable plan summary")
    actions: list[PlannedAction] = Field(..., min_length=1, description="Ordered list of actions")
    estimated_impact: str = Field(default="MEDIUM", description="LOW / MEDIUM / HIGH")

class NormalizedAction(BaseModel):
    action: ActionType
    target: str = Field(..., min_length=1, description="Target service or deployment")
    parameters: dict[str, Any] = Field(default_factory=dict)
    compensation: Optional['NormalizedAction'] = Field(None, description="Compensating action")

class GuardrailResult(BaseModel):
    status: GuardrailStatus
    violations: list[str] = Field(default_factory=list)
    approval_required: bool = Field(default=False)

class PostconditionRule(BaseModel):
    metric: str = Field(..., description="Metric name to evaluate")
    operator: str = Field(..., pattern=r"^(>=|<=|>|<|==|!=)$", description="Comparison operator")
    threshold: float = Field(..., description="Expected threshold value")

    @classmethod
    def from_string(cls, condition: str) -> PostconditionRule:
        match = re.match(r"(\w+)\s*(>=|<=|>|<|==|!=)\s*([\d.]+)", condition.strip())
        if not match:
            raise ValueError(f"Cannot parse postcondition: '{condition}'")
        return cls(
            metric=match.group(1),
            operator=match.group(2),
            threshold=float(match.group(3)),
        )

    def evaluate(self, actual_value: float) -> bool:
        ops = {
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        return ops[self.operator](actual_value, self.threshold)

class PostconditionResult(BaseModel):
    rule: str = Field(..., description="Original postcondition string")
    actual_value: float
    passed: bool

class ExecutionResult(BaseModel):
    action: str
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AuditEvent(BaseModel):
    incident_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = Field(..., description="Event category")
    contract_id: Optional[str] = None
    contract_version: Optional[str] = None
    actor: Optional[str] = Field(default=None)
    details: dict[str, Any] = Field(default_factory=dict)
    outcome: Optional[str] = None
