from __future__ import annotations

import logging
from typing import List

from core.models import NormalizedAction
from .models import PolicyPack, ComplianceResult

class PolicyEvaluator:
    """Evaluates proposed actions against active PolicyPacks."""
    
    def __init__(self, active_packs: List[PolicyPack]) -> None:
        self.active_packs = active_packs
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def evaluate(self, actions: List[NormalizedAction]) -> ComplianceResult:
        """Evaluate a set of actions against all active policies."""
        violations = []
        
        for action in actions:
            for pack in self.active_packs:
                for rule in pack.rules:
                    violation = rule.evaluate(action)
                    if violation:
                        self._logger.warning(f"Compliance violation in pack '{pack.name}': {violation}")
                        violations.append(violation)
                        
        return ComplianceResult(
            is_compliant=len(violations) == 0,
            violations=violations
        )
