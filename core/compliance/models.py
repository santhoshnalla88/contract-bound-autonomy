from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from core.models import NormalizedAction

class PolicyRule(BaseModel):
    """A single compliance rule."""
    rule_id: str
    description: str
    
    # Simple evaluation criteria
    forbidden_actions: List[str] = Field(default_factory=list)
    forbidden_targets: List[str] = Field(default_factory=list)
    
    def evaluate(self, action: NormalizedAction) -> Optional[str]:
        """Returns violation message if action violates rule, else None."""
        action_name = action.action.value.lower()
        if action_name in self.forbidden_actions:
            return f"Action '{action_name}' is forbidden by compliance rule {self.rule_id}."
            
        if action.target in self.forbidden_targets:
            return f"Target '{action.target}' is forbidden by compliance rule {self.rule_id}."
            
        return None

class PolicyPack(BaseModel):
    """A collection of rules for a specific compliance standard (e.g. PCI, GDPR)."""
    pack_id: str
    name: str
    description: str
    rules: List[PolicyRule]

class ComplianceResult(BaseModel):
    """Result of evaluating an action against policy packs."""
    is_compliant: bool
    violations: List[str] = Field(default_factory=list)
