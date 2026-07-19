"""Risk evaluation for remediation plans (v2).

The RiskEvaluator computes a numeric risk score (0-100) for a proposed
remediation plan based on complexity, business impact, and compliance risk.
It then maps this score to a decision matrix (RiskLevel and approval flag).

Score Bands:
- 0-30: LOW risk (Auto-approve)
- 31-70: MEDIUM to HIGH risk (Requires human approval)
- 71-100: CRITICAL risk (Escalate / Block)
"""

from __future__ import annotations

import logging
from typing import Final, Tuple

from core.enums import ActionType, RiskLevel, Severity
from core.models import RemediationPlan
from core.models import BaseIncident as Incident
from core.contracts import OperationalContract

logger = logging.getLogger(__name__)

class RiskEvaluator:
    """Evaluates the numeric risk score of a remediation plan."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def evaluate(
        self,
        plan: RemediationPlan,
        incident: Incident,
        contract: OperationalContract,
        trust_score: float = 0.5,
    ) -> Tuple[int, RiskLevel, bool]:
        """Evaluate the numeric risk of a remediation plan.

        Returns:
            Tuple of (numeric_score, risk_level, requires_human_approval).
        """
        score = 0
        requires_human_approval = False

        self._logger.info(
            "Evaluating risk (v2) for plan with %d action(s), incident severity: %s, trust_score: %.2f",
            len(plan.actions),
            incident.severity.value,
            trust_score,
        )

        # 1. Business Impact (Max 40 points)
        if incident.severity == Severity.CRITICAL:
            score += 40
        elif incident.severity == Severity.HIGH:
            score += 25
        elif incident.severity == Severity.MEDIUM:
            score += 10
            
        if getattr(incident, "active_checkout_connections", 0):
            score += 15

        # 2. Complexity (Max 30 points)
        score += min(len(plan.actions) * 5, 20)  # Up to 20 pts for multiple actions
        
        action_names = [a.action.lower() for a in plan.actions]
        if ActionType.ROLLBACK_DEPLOYMENT.value in action_names:
            score += 20
        elif ActionType.SCALE_DEPLOYMENT.value in action_names:
            score += 10

        # 3. Contract & Compliance checks (Max 30 points)
        for planned_action in plan.actions:
            action_name = planned_action.action.lower()
            if contract.requires_approval(action_name):
                requires_human_approval = True
                score += 25
                break # Only add once

        # 4. Apply Trust Multiplier
        # trust_score is 0.0 to 1.0. 
        # 1.0 trust -> 0.7 multiplier (reduces risk by 30%)
        # 0.5 trust -> 1.0 multiplier (no change)
        # 0.0 trust -> 1.3 multiplier (increases risk by 30%)
        trust_multiplier = 1.0 + (0.5 - trust_score) * 0.6
        score = int(score * trust_multiplier)

        # Cap score at 100
        score = min(max(score, 0), 100)

        # Map to RiskLevel and Approval
        if score <= 30:
            risk_level = RiskLevel.LOW
        elif score <= 50:
            risk_level = RiskLevel.MEDIUM
            requires_human_approval = True
        elif score <= 70:
            risk_level = RiskLevel.HIGH
            requires_human_approval = True
        else:
            risk_level = RiskLevel.CRITICAL
            requires_human_approval = True

        self._logger.info(
            "Risk evaluation complete: score=%d, level=%s, approval_required=%s",
            score,
            risk_level.value,
            requires_human_approval,
        )

        return score, risk_level, requires_human_approval
