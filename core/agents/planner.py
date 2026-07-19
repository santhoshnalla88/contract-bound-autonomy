"""Planning agent for incident remediation.

The PlannerAgent uses an LLM to analyze incidents, retrieved knowledge
context, and contract summaries to generate structured remediation plans.
It outputs a RemediationPlan using LangChain's structured output, which
is then normalized into NormalizedActions for guardrail validation.

The planner is contract-AWARE but not contract-ENFORCING — it receives
the contract summary as context to inform its proposals, but the actual
enforcement is done by the guardrail engine. This separation ensures
the LLM cannot bypass deterministic rules.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.enums import ActionType
from core.models import BaseIncident as Incident
from core.models import AuditEvent
from core.models import ExecutionResult
from core.models import PostconditionResult
from core.models import PostconditionRule
from core.models import GuardrailResult
from core.models import NormalizedAction
from core.models import BaseIncident as Incident, RemediationPlan
from core.models import PlannedAction

logger = logging.getLogger(__name__)


def _metric_reader(metrics):
    """Return a getter that reads a metric from a dict OR a typed object OR None."""
    def get(key, default="N/A"):
        if metrics is None:
            return default
        if isinstance(metrics, dict):
            return metrics.get(key, default)
        return getattr(metrics, key, default)
    return get

_SYSTEM_PROMPT = """\
You are an expert incident remediation analyst for a Kubernetes-based \
e-commerce platform. Your role is to analyze operational incidents and \
generate structured remediation plans.

## Guidelines

1. **Use retrieved knowledge**: Base your remediation strategy on the \
provided context from runbooks, architecture docs, and past incident reports.

2. **Respect contract boundaries**: The operational contract defines what \
actions you are allowed to propose. Stay within these boundaries. Only \
propose actions from the allowed list.

3. **Generate structured plans**: Output a clear, step-by-step remediation \
plan with specific actions, parameters, and rationale for each step.

4. **Be conservative**: Prefer less disruptive actions first (e.g., restart \
before rollback). Scale interventions proportionally to incident severity.

5. **Consider availability**: Always account for minimum availability \
requirements and active connections when planning disruptive operations.

## Available Action Types
- restart_pods: Restart unhealthy pods (parameters: count)
- scale_deployment: Scale a deployment (parameters: replicas)
- rollback_deployment: Rollback to a previous deployment version (parameters: version)
- get_service_status: Get current service status (parameters: none)
- get_metrics: Retrieve current metrics (parameters: none)

## If Retrying After Violations
If previous plan attempts were rejected by guardrails, you MUST learn from \
the listed violations and adjust your plan accordingly. Do NOT repeat the \
same actions that caused violations. Propose alternative approaches that \
stay within contract limits.
"""


class PlannerAgent:
    """LLM-powered planning agent for incident remediation.

    Uses ChatOpenAI with structured output to generate RemediationPlan
    instances directly from incident analysis. The planner receives
    contract summaries as context but does not enforce them — enforcement
    is handled by the guardrail engine downstream.

    Attributes:
        llm: The ChatOpenAI instance configured for planning.
    """

    def __init__(
        self,
        model_name: str = "gpt-4o",
        temperature: float = 0.1,
    ) -> None:
        """Initialize the PlannerAgent.

        Args:
            model_name: OpenAI model to use for plan generation.
            temperature: Sampling temperature. Low values (0.0-0.2)
                produce more deterministic, conservative plans.
        """
        from core.llm.factory import get_chat_model

        # Provider-agnostic: the planner role maps to Claude by default (config-driven).
        self.llm = get_chat_model("planner", temperature=temperature)
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def plan(
        self,
        incident: Incident,
        context: str,
        contract_summary: str,
        previous_violations: list[str] | None = None,
    ) -> RemediationPlan:
        """Generate a structured remediation plan for an incident.

        Builds a prompt from the incident details, retrieved context,
        contract summary, and any previous violations (for retry loops).
        Uses LLM structured output to produce a typed RemediationPlan.

        Args:
            incident: The incident requiring remediation.
            context: Retrieved knowledge context from RAG (runbooks,
                architecture docs, past incidents).
            contract_summary: Human-readable summary of the operational
                contract boundaries.
            previous_violations: Optional list of violation strings from
                a prior guardrail rejection. If provided, the planner
                adjusts its strategy to avoid repeating violations.

        Returns:
            A structured RemediationPlan with summary, ordered actions,
            and estimated impact.
        """
        self._logger.info(
            "Generating remediation plan for incident %s (severity: %s)",
            incident.incident_id,
            incident.severity.value,
        )

        # Build the user message with all context
        user_content = self._build_user_message(
            incident, context, contract_summary, previous_violations
        )

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        # Use structured output for typed plan generation
        structured_llm = self.llm.with_structured_output(RemediationPlan)
        plan: RemediationPlan = await structured_llm.ainvoke(messages)

        self._logger.info(
            "Plan generated: %d action(s), estimated impact: %s",
            len(plan.actions),
            plan.estimated_impact,
        )

        return plan

    def _build_user_message(
        self,
        incident: Incident,
        context: str,
        contract_summary: str,
        previous_violations: list[str] | None,
    ) -> str:
        """Build the user message content for the planning prompt.

        Args:
            incident: The incident to analyze.
            context: Retrieved RAG context.
            contract_summary: Contract boundary summary.
            previous_violations: Prior guardrail violations, if retrying.

        Returns:
            Formatted user message string.
        """
        m = _metric_reader(getattr(incident, "metrics", None))
        sections = [
            "## Incident Details",
            f"- **Incident ID**: {incident.incident_id}",
            f"- **Service**: {incident.service}",
            f"- **Environment**: {incident.environment}",
            f"- **Severity**: {incident.severity.value}",
            f"- **Error Rate**: {m('error_rate')}%",
            f"- **Healthy Pods**: {m('healthy_pods')}/{m('total_pods')}",
            f"- **Active Checkout Connections**: {getattr(incident, 'active_checkout_connections', False)}",
            "",
            "## Logs",
            incident.logs if incident.logs else "(no logs available)",
            "",
            "## Retrieved Knowledge Context",
            context if context else "(no context available)",
            "",
            "## Operational Contract Boundaries",
            contract_summary,
        ]

        if previous_violations:
            sections.extend([
                "",
                "## ⚠️ PREVIOUS PLAN REJECTED — Violations to Avoid",
                "Your previous plan was rejected by the guardrail engine. "
                "You MUST adjust your plan to avoid these violations:",
                "",
            ])
            for i, violation in enumerate(previous_violations, 1):
                sections.append(f"{i}. {violation}")
            sections.append(
                "\nGenerate a NEW plan that addresses the incident while "
                "respecting these constraints."
            )

        sections.append(
            "\nAnalyze the incident and generate a remediation plan."
        )

        return "\n".join(sections)


def normalize_plan(plan: RemediationPlan, service: str) -> list[NormalizedAction]:
    """Convert a RemediationPlan into a list of NormalizedActions.

    Maps each PlannedAction to a NormalizedAction by resolving the
    action string to an ActionType enum value. This normalization step
    ensures that the guardrail engine operates on canonical action types
    rather than free-form LLM strings.

    Args:
        plan: The remediation plan to normalize.
        service: The target service name to set on each action.

    Returns:
        A list of NormalizedAction instances.

    Raises:
        ValueError: If a PlannedAction's action string doesn't match
            any known ActionType.
    """
    normalized: list[NormalizedAction] = []

    # Build a lookup map from lowercase action names to ActionType values
    action_type_map: dict[str, ActionType] = {
        member.value.lower(): member for member in ActionType
    }

    for planned_action in plan.actions:
        action_key = planned_action.action.strip().lower()

        if action_key not in action_type_map:
            raise ValueError(
                f"Unknown action type: '{planned_action.action}'. "
                f"Valid types: {[m.value for m in ActionType]}"
            )

        action_type = action_type_map[action_key]

        normalized.append(
            NormalizedAction(
                action=action_type,
                target=service,
                parameters=dict(planned_action.parameters),
            )
        )

    logger.info(
        "Normalized %d planned action(s) to NormalizedActions for service '%s'",
        len(normalized),
        service,
    )

    return normalized
