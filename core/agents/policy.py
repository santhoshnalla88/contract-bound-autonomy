"""Semantic validator for ambiguous contract rules.

The SemanticValidator uses an LLM to evaluate remediation plans against
contract rules that are too nuanced for deterministic checks. For example,
"preserve active connections" can mean different things depending on the
specific action — the semantic validator assesses whether the plan
adequately addresses connection draining.

CRITICAL DESIGN PRINCIPLE: The semantic validator can only ADD restrictions
to the guardrail result. It can NEVER override or reverse a deterministic
rejection. If the deterministic guardrail engine has already rejected a
plan, the semantic validator's approval is irrelevant.

This is a supplementary validation layer, not a replacement for the
deterministic guardrail engine.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.models import BaseIncident as Incident, RemediationPlan
from core.contracts import OperationalContract

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a compliance validator for an autonomous remediation system. \
Your role is to evaluate whether a proposed remediation plan adequately \
addresses the SEMANTIC requirements of an operational contract.

## Your Scope
You evaluate ONLY ambiguous or contextual rules that cannot be checked \
deterministically. Examples:
- Does the plan include connection draining before restarting pods when \
active connections exist?
- Does the plan consider the impact on dependent services?
- Does the plan sequence actions in a safe order?

## What You Do NOT Check
Deterministic rules are already enforced by the guardrail engine:
- Whether actions are in the allowed list
- Whether actions exceed numerical limits
- Whether forbidden actions are proposed
DO NOT re-evaluate these. Assume they have already been checked.

## CRITICAL RULE
You can only ADD restrictions. If you identify a semantic compliance \
issue, flag it. You CANNOT approve something that would violate \
deterministic rules, and you CANNOT override a deterministic rejection.

## Output
Respond with:
- is_compliant: true/false
- reasoning: Detailed explanation of your assessment
"""


class _PolicyValidationResult(BaseModel):
    """Structured output for semantic validation LLM calls."""

    is_compliant: bool = Field(
        ..., description="Whether the plan is semantically compliant"
    )
    reasoning: str = Field(
        ..., description="Detailed reasoning for the compliance decision"
    )


class PolicyAgent:
    """LLM-based validator for ambiguous contract rules.

    Supplements the deterministic guardrail engine by evaluating
    contextual compliance requirements that are difficult to express
    as boolean checks. The validator cannot override deterministic
    rejections — it can only identify additional compliance concerns.

    Attributes:
        llm: The ChatOpenAI instance for semantic evaluation.
    """

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ) -> None:
        """Initialize the PolicyAgent.

        Args:
            model_name: OpenAI model to use. Defaults to gpt-4o-mini
                for cost efficiency — semantic validation doesn't require
                the most capable model.
            temperature: Sampling temperature. Set to 0.0 for maximum
                determinism in compliance decisions.
        """
        from core.llm.factory import get_chat_model

        # Policy role maps to Claude (cheap Haiku tier) for compliance judgement.
        self.llm = get_chat_model("policy", temperature=temperature)
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def validate(
        self,
        plan: RemediationPlan,
        contract: OperationalContract,
        incident: Incident,
    ) -> tuple[bool, str]:
        """Evaluate semantic compliance of a remediation plan.

        Analyzes the plan against contextual contract requirements that
        cannot be checked deterministically. Focuses on:
        - Connection draining for disruptive operations
        - Action sequencing safety
        - Dependent service impact

        CRITICAL: This method can only ADD restrictions. A return of
        (True, ...) does NOT override a deterministic guardrail rejection.
        The orchestration workflow must check deterministic guardrails
        first and only call semantic validation if those pass.

        Args:
            plan: The proposed remediation plan to validate.
            contract: The operational contract to validate against.
            incident: The incident context for understanding the situation.

        Returns:
            A tuple of (is_compliant, reasoning):
            - is_compliant: True if the plan meets semantic requirements
            - reasoning: Detailed explanation of the assessment
        """
        self._logger.info(
            "Running semantic validation for plan: '%s'",
            plan.summary[:80],
        )

        user_content = self._build_validation_prompt(plan, contract, incident)

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        structured_llm = self.llm.with_structured_output(_PolicyValidationResult)
        result: _PolicyValidationResult = await structured_llm.ainvoke(messages)

        self._logger.info(
            "Semantic validation result: compliant=%s, reasoning=%s",
            result.is_compliant,
            result.reasoning[:100],
        )

        return result.is_compliant, result.reasoning

    def _build_validation_prompt(
        self,
        plan: RemediationPlan,
        contract: OperationalContract,
        incident: Incident,
    ) -> str:
        """Build the validation prompt with all relevant context.

        Args:
            plan: The plan to validate.
            contract: The operational contract.
            incident: The incident context.

        Returns:
            Formatted prompt string for the LLM.
        """
        # Format plan actions for the prompt
        actions_text = []
        for i, action in enumerate(plan.actions, 1):
            params_str = ", ".join(
                f"{k}={v}" for k, v in action.parameters.items()
            ) if action.parameters else "none"
            actions_text.append(
                f"  {i}. {action.action} (params: {params_str}) — {action.rationale}"
            )

        # Identify semantic rules to evaluate
        semantic_checks = []
        if contract.availability_constraints.preserve_active_connections:
            semantic_checks.append(
                "- **Preserve Active Connections**: The contract requires preserving "
                "active connections. If the plan includes disruptive actions (restart, "
                "rollback), verify that it includes connection draining or graceful "
                "shutdown steps."
            )
        if contract.availability_constraints.minimum_available_replicas > 0:
            semantic_checks.append(
                f"- **Minimum Availability**: At least "
                f"{contract.availability_constraints.minimum_available_replicas} "
                f"replica(s) must remain available during remediation. Verify that "
                f"the plan sequences actions to maintain this."
            )

        _m = getattr(incident, "metrics", None)
        def mv(key, default="N/A"):
            if _m is None:
                return default
            return _m.get(key, default) if isinstance(_m, dict) else getattr(_m, key, default)
        sections = [
            "## Incident Context",
            f"- Service: {incident.service} ({incident.environment})",
            f"- Severity: {incident.severity.value}",
            f"- Error Rate: {mv('error_rate')}%",
            f"- Pods: {mv('healthy_pods')}/{mv('total_pods')} healthy",
            f"- Active Checkout Connections: {getattr(incident, 'active_checkout_connections', False)}",
            "",
            "## Proposed Remediation Plan",
            f"Summary: {plan.summary}",
            f"Estimated Impact: {plan.estimated_impact}",
            "Actions:",
            "\n".join(actions_text),
            "",
            "## Contract Semantic Rules to Evaluate",
        ]

        if semantic_checks:
            sections.extend(semantic_checks)
        else:
            sections.append("No specific semantic rules require evaluation.")

        sections.extend([
            "",
            "## Task",
            "Evaluate whether this plan adequately addresses the semantic "
            "contract requirements listed above. Focus ONLY on contextual "
            "compliance — deterministic checks (allowed actions, limits) "
            "have already been validated.",
        ])

        return "\n".join(sections)
