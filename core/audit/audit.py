"""Audit logger providing typed convenience methods for audit events.

Each method corresponds to a specific decision point in the orchestration
workflow.  The logger constructs a fully-populated ``AuditEvent`` and
delegates persistence to the ``DatabaseManager``.

The audit trail must answer: *"Why did the agent take this action?"*
Every method captures the contextual details required for post-incident
review, compliance reporting, and LangSmith trace correlation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.models import AuditEvent
from core.persistence.database import DatabaseManager

logger = logging.getLogger(__name__)


class AuditLogger:
    """High-level audit logger for the orchestration workflow.

    Wraps ``DatabaseManager.insert_audit_event`` with typed convenience
    methods so callers don't need to construct ``AuditEvent`` objects
    manually.
    """

    def __init__(self, db: DatabaseManager) -> None:
        """Initialise the logger with a database manager.

        Args:
            db: An initialised ``DatabaseManager`` instance.
        """
        self._db = db

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    async def _log(
        self,
        incident_id: str,
        event_type: str,
        details: dict[str, Any],
        outcome: Optional[str] = None,
        contract_id: Optional[str] = None,
        contract_version: Optional[str] = None,
    ) -> None:
        """Create and persist an audit event.

        Args:
            incident_id: Owning incident identifier.
            event_type: Category / lifecycle stage identifier.
            details: Arbitrary JSON-serialisable payload.
            outcome: Optional summary outcome string.
            contract_id: Optional contract identifier.
            contract_version: Optional contract semantic version.
        """
        event = AuditEvent(
            incident_id=incident_id,
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            contract_id=contract_id,
            contract_version=contract_version,
            details=details,
            outcome=outcome,
        )
        await self._db.insert_audit_event(event)
        logger.debug(
            "Audit [%s] %s — %s",
            event_type,
            incident_id,
            outcome or "recorded",
        )

    # ------------------------------------------------------------------
    # Workflow-specific log methods
    # ------------------------------------------------------------------

    async def log_incident_received(
        self, incident_id: str, details: dict[str, Any]
    ) -> None:
        """Log that an incident has been received by the orchestrator.

        Args:
            incident_id: The incident identifier.
            details: Incident payload (service, severity, metrics, etc.).
        """
        await self._log(
            incident_id=incident_id,
            event_type="incident_received",
            details=details,
            outcome="received",
        )

    async def log_retrieval(
        self,
        incident_id: str,
        doc_count: int,
        details: dict[str, Any],
    ) -> None:
        """Log RAG retrieval results.

        Args:
            incident_id: The incident identifier.
            doc_count: Number of documents retrieved.
            details: Retrieval metadata (sources, scores, etc.).
        """
        await self._log(
            incident_id=incident_id,
            event_type="rag_retrieval",
            details={**details, "doc_count": doc_count},
            outcome=f"retrieved_{doc_count}_docs",
        )

    async def log_contract_loaded(
        self,
        incident_id: str,
        contract_id: str,
        version: str,
    ) -> None:
        """Log that an operational contract was loaded.

        Args:
            incident_id: The incident identifier.
            contract_id: Unique contract identifier.
            version: Contract semantic version.
        """
        await self._log(
            incident_id=incident_id,
            event_type="contract_loaded",
            details={"contract_id": contract_id, "version": version},
            outcome="loaded",
            contract_id=contract_id,
            contract_version=version,
        )

    async def log_plan_proposed(
        self,
        incident_id: str,
        plan_summary: str,
        details: dict[str, Any],
    ) -> None:
        """Log a remediation plan proposed by the planning agent.

        Args:
            incident_id: The incident identifier.
            plan_summary: Human-readable plan summary.
            details: Full plan details (actions, rationale, etc.).
        """
        await self._log(
            incident_id=incident_id,
            event_type="plan_proposed",
            details={**details, "summary": plan_summary},
            outcome="proposed",
        )

    async def log_guardrail_result(
        self,
        incident_id: str,
        status: str,
        violations: list[str],
        contract_id: str,
        version: str,
    ) -> None:
        """Log the result of guardrail evaluation.

        Args:
            incident_id: The incident identifier.
            status: 'APPROVED' or 'REJECTED'.
            violations: List of violated rules (empty if approved).
            contract_id: Contract used for evaluation.
            version: Contract version.
        """
        await self._log(
            incident_id=incident_id,
            event_type="guardrail_evaluation",
            details={"status": status, "violations": violations},
            outcome=status.lower(),
            contract_id=contract_id,
            contract_version=version,
        )

    async def log_risk_evaluation(
        self,
        incident_id: str,
        risk_level: str,
        requires_approval: bool,
    ) -> None:
        """Log risk assessment results.

        Args:
            incident_id: The incident identifier.
            risk_level: Assessed risk level (LOW / MEDIUM / HIGH / CRITICAL).
            requires_approval: Whether human approval is required.
        """
        await self._log(
            incident_id=incident_id,
            event_type="risk_evaluation",
            details={
                "risk_level": risk_level,
                "requires_approval": requires_approval,
            },
            outcome=f"risk_{risk_level.lower()}",
        )

    async def log_execution(
        self,
        incident_id: str,
        action: str,
        result: dict[str, Any],
        contract_id: str,
        version: str,
    ) -> None:
        """Log a tool execution and its result.

        Args:
            incident_id: The incident identifier.
            action: Action type that was executed.
            result: Execution result payload.
            contract_id: Governing contract identifier.
            version: Contract version.
        """
        success = result.get("success", False)
        await self._log(
            incident_id=incident_id,
            event_type="action_executed",
            details={"action": action, "result": result},
            outcome="success" if success else "failure",
            contract_id=contract_id,
            contract_version=version,
        )

    async def log_postcondition(
        self,
        incident_id: str,
        results: list[dict[str, Any]],
        passed: bool,
    ) -> None:
        """Log postcondition evaluation results.

        Args:
            incident_id: The incident identifier.
            results: Per-rule evaluation results.
            passed: Whether all postconditions passed.
        """
        await self._log(
            incident_id=incident_id,
            event_type="postcondition_evaluation",
            details={"results": results, "all_passed": passed},
            outcome="passed" if passed else "failed",
        )

    async def log_human_decision(
        self,
        incident_id: str,
        decision: str,
        reasoning: str,
    ) -> None:
        """Log a human-in-the-loop approval/denial decision.

        Args:
            incident_id: The incident identifier.
            decision: Decision string (e.g. 'approved', 'denied').
            reasoning: Human-provided reasoning for the decision.
        """
        await self._log(
            incident_id=incident_id,
            event_type="human_decision",
            details={"decision": decision, "reasoning": reasoning},
            outcome=decision,
        )

    async def log_final_outcome(
        self,
        incident_id: str,
        status: str,
        details: dict[str, Any],
    ) -> None:
        """Log the final orchestration outcome.

        Args:
            incident_id: The incident identifier.
            status: Final status (SUCCESS / FAILED / ESCALATED / DENIED).
            details: Summary details of the entire workflow run.
        """
        await self._log(
            incident_id=incident_id,
            event_type="final_outcome",
            details={**details, "final_status": status},
            outcome=status.lower(),
        )
