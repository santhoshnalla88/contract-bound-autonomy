"""Guardrail enforcement engine.

The GuardrailEngine orchestrates all deterministic validators in strict
priority order. It is the single authority that produces a GuardrailResult
from a list of normalized actions and an operational contract.

Priority Order (critical for correctness):
1. Forbidden action check → instant reject
2. Allowed action check → reject if not on allowlist
3. Limit validation → reject if limits exceeded
4. Availability constraint validation → reject if constraints violated

Design principle: Deterministic rules ALWAYS win. Semantic validation
(via SemanticValidator) can only ADD restrictions, never REMOVE rejections.
"""

from __future__ import annotations

import logging

from core.enums import ActionType, GuardrailStatus
from core.models import NormalizedAction, GuardrailResult
from core.contracts import OperationalContract
from core.guardrails.validators import (
    validate_action_not_forbidden,
    validate_action_allowed,
    validate_limits,
    validate_availability,
    validate_approval_required,
)
from core.compliance.evaluator import PolicyEvaluator
from core.budget.accountant import ExecutionBudgetAccountant
from core.budget.models import BudgetType

logger = logging.getLogger(__name__)


class GuardrailEngine:
    """Deterministic guardrail enforcement engine.

    Evaluates proposed actions against an operational contract using a
    strict priority-ordered chain of validators. Produces a single
    GuardrailResult indicating whether the actions are approved or rejected,
    along with any violations and approval requirements.

    The engine has no external dependencies — all state is passed in via
    method arguments. This makes it fully testable and deterministic.
    """

    def __init__(self) -> None:
        """Initialize the GuardrailEngine.

        No dependencies required — all validators are pure functions
        and all state is passed per-evaluation.
        """
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def evaluate(
        self,
        normalized_actions: list[NormalizedAction],
        contract: OperationalContract,
        execution_history: list[dict] | None = None,
        current_metrics: dict | None = None,
        accountant: ExecutionBudgetAccountant | None = None,
        policy_evaluator: PolicyEvaluator | None = None,
    ) -> GuardrailResult:
        """Evaluate a list of normalized actions against the contract.

        Runs validators in strict priority order for each action:
        1. Forbidden action check (instant reject)
        2. Allowed action check (reject if not allowlisted)
        3. Limit validation
        4. Availability constraint validation

        After collecting all violations, determines the approval_required
        flag from contract.requires_approval() for each action.

        Args:
            normalized_actions: List of NormalizedAction instances to evaluate.
            contract: The operational contract defining boundaries.
            execution_history: Optional list of previously executed actions
                in this incident. Each entry is a dict with 'action' and
                optionally 'parameters' keys.
            current_metrics: Optional dict of current system metrics with
                keys like 'total_pods', 'healthy_pods', 'active_connections'.

        Returns:
            GuardrailResult with status, violations, and approval_required flag.
        """
        if execution_history is None:
            execution_history = []
        if current_metrics is None:
            current_metrics = {}

        all_violations: list[str] = []
        approval_required = False

        self._logger.info(
            "Evaluating %d action(s) against contract '%s' v%s",
            len(normalized_actions),
            contract.contract_id,
            contract.version,
        )
        
        # --- Pre-check: Execution Budget ---
        if accountant:
            tool_calls_remaining = accountant.get_remaining_budget(BudgetType.TOOL_CALL)
            if tool_calls_remaining < len(normalized_actions):
                all_violations.append(
                    f"Budget exceeded: Plan requires {len(normalized_actions)} tool calls, "
                    f"but only {tool_calls_remaining} remaining."
                )
                self._logger.warning("Budget check failed, rejecting plan.")
                # If budget is breached, we can instantly reject
                return GuardrailResult(
                    status=GuardrailStatus.REJECTED,
                    violations=all_violations,
                    approval_required=False,
                )

        # --- Pre-check: Compliance Policies ---
        if policy_evaluator:
            compliance_result = policy_evaluator.evaluate(normalized_actions)
            if not compliance_result.is_compliant:
                all_violations.extend(compliance_result.violations)
                self._logger.warning("Policy check failed, rejecting plan.")
                # Instant reject if compliance fails
                return GuardrailResult(
                    status=GuardrailStatus.REJECTED,
                    violations=all_violations,
                    approval_required=False,
                )

        # Read-only observability actions never mutate infrastructure and are
        # skipped by the MCP executor — they don't require contract allowlisting.
        _READ_ONLY = {ActionType.GET_SERVICE_STATUS, ActionType.GET_METRICS}

        for action in normalized_actions:
            self._logger.debug(
                "Evaluating action: %s on target '%s'",
                action.action.value,
                action.target,
            )

            if action.action in _READ_ONLY:
                continue

            # --- Priority 1: Forbidden action check (instant reject) ---
            forbidden_violations = validate_action_not_forbidden(action, contract)
            if forbidden_violations:
                all_violations.extend(forbidden_violations)
                self._logger.warning(
                    "Action '%s' is FORBIDDEN by contract — skipping remaining checks",
                    action.action.value,
                )
                # Forbidden = instant reject; skip remaining validators for this action
                continue

            # --- Priority 2: Allowed action check ---
            allowed_violations = validate_action_allowed(action, contract)
            if allowed_violations:
                all_violations.extend(allowed_violations)
                self._logger.warning(
                    "Action '%s' is NOT in the allowed list — skipping remaining checks",
                    action.action.value,
                )
                # Not allowed = reject; skip remaining validators for this action
                continue

            # --- Priority 3: Limit validation ---
            limit_violations = validate_limits(action, contract, execution_history)
            all_violations.extend(limit_violations)

            # --- Priority 4: Availability constraint validation ---
            availability_violations = validate_availability(
                action, contract, current_metrics
            )
            all_violations.extend(availability_violations)

            # --- Approval requirements (not a violation, metadata only) ---
            validate_approval_required(action, contract)
            if contract.requires_approval(action.action.value):
                approval_required = True
                self._logger.info(
                    "Action '%s' requires human approval per contract",
                    action.action.value,
                )

        # Determine final status
        if all_violations:
            status = GuardrailStatus.REJECTED
            self._logger.info(
                "Guardrail evaluation REJECTED: %d violation(s)", len(all_violations)
            )
        else:
            status = GuardrailStatus.APPROVED
            self._logger.info("Guardrail evaluation APPROVED")

        result = GuardrailResult(
            status=status,
            violations=all_violations,
            approval_required=approval_required,
        )

        return result
