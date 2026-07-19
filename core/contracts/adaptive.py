from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from core.contracts.contracts import OperationalContract

logger = logging.getLogger(__name__)

class AdaptiveContext(BaseModel):
    """Contextual information used to evaluate adaptive rules."""
    incident_severity: str
    trust_score: float = Field(default=50.0)
    agent_id: str = Field(default="system")
    environment: str
    additional_flags: Dict[str, Any] = Field(default_factory=dict)

class RuleMutation(BaseModel):
    """Defines how a contract should be mutated if a rule matches."""
    # Narrowing limits (must be stricter than the hard ceiling)
    override_max_replicas: Optional[int] = None
    override_max_pod_restarts: Optional[int] = None
    
    # Restricting actions
    remove_allowed_actions: List[str] = Field(default_factory=list)
    add_forbidden_actions: List[str] = Field(default_factory=list)
    
    # Changing approval requirements
    require_approval_for: List[str] = Field(default_factory=list)

class AdaptiveRule(BaseModel):
    """A rule that adapts an operational contract based on context."""
    rule_id: str
    description: str
    
    # Simple predicates (we could use a full expression engine, but keep it simple for now)
    min_severity_level: Optional[str] = None
    max_trust_score: Optional[float] = None
    requires_flag: Optional[str] = None
    
    mutation: RuleMutation

    def matches(self, context: AdaptiveContext) -> bool:
        """Evaluates whether this rule applies to the given context."""
        
        # In a real implementation we would parse actual severity order, 
        # but for simplicity we match exact severity or use a generic flag.
        if self.min_severity_level and context.incident_severity != self.min_severity_level:
            # We would normally do an ordinal check here, like RiskEvaluator does.
            # Assuming exact match for this basic engine unless we import the enum and ordinal logic.
            # Let's assume it checks for equality for now.
            if context.incident_severity != self.min_severity_level:
                return False
                
        if self.max_trust_score is not None and context.trust_score > self.max_trust_score:
            return False
            
        if self.requires_flag and not context.additional_flags.get(self.requires_flag, False):
            return False
            
        return True

class AdaptiveContractResolver:
    """Resolves an EffectiveContract by applying AdaptiveRules to an OperationalContract."""
    
    def __init__(self, rules: List[AdaptiveRule]) -> None:
        self.rules = rules
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def resolve_effective_contract(
        self, base_contract: OperationalContract, context: AdaptiveContext
    ) -> OperationalContract:
        """Applies matching rules to mutate the base contract into an effective contract."""
        
        # Create a deep copy using Pydantic
        effective = OperationalContract(**base_contract.model_dump())
        
        applied_rules = []
        
        for rule in self.rules:
            if rule.matches(context):
                self._apply_mutation(effective, rule.mutation, base_contract)
                applied_rules.append(rule.rule_id)
                
        if applied_rules:
            self._logger.info(
                f"Adapted contract {effective.contract_id} using rules: {', '.join(applied_rules)}"
            )
            
        return effective

    def _apply_mutation(
        self, 
        effective: OperationalContract, 
        mutation: RuleMutation, 
        base: OperationalContract
    ) -> None:
        """Applies the mutations while guaranteeing we never elevate above the base contract."""
        
        # Narrow limits (must be less than or equal to the base limit)
        if mutation.override_max_replicas is not None:
            effective.limits.max_replicas = min(
                mutation.override_max_replicas, base.limits.max_replicas
            )
            
        if mutation.override_max_pod_restarts is not None:
            effective.limits.max_pod_restarts_per_incident = min(
                mutation.override_max_pod_restarts, base.limits.max_pod_restarts_per_incident
            )
            
        # Remove allowed actions
        for action in mutation.remove_allowed_actions:
            if action in effective.allowed_actions:
                effective.allowed_actions.remove(action)
                
        # Add forbidden actions
        for action in mutation.add_forbidden_actions:
            if action not in effective.forbidden_actions:
                effective.forbidden_actions.append(action)
                
        # Add approval requirements
        for action in mutation.require_approval_for:
            effective.approval_requirements[action] = True
