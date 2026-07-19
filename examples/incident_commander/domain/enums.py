"""Domain enumerations for the orchestrator."""

from enum import StrEnum


class Severity(StrEnum):
    """Incident severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ActionType(StrEnum):
    """Allowed remediation action types.

    Each value corresponds to an MCP tool name.
    The guardrail engine validates proposed actions against this enum.
    """
    RESTART_PODS = "restart_pods"
    SCALE_DEPLOYMENT = "scale_deployment"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    GET_SERVICE_STATUS = "get_service_status"
    GET_METRICS = "get_metrics"


class GuardrailStatus(StrEnum):
    """Result of guardrail evaluation."""
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RiskLevel(StrEnum):
    """Risk assessment levels.

    HIGH and CRITICAL trigger mandatory human approval
    regardless of contract approval_requirements.
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FinalStatus(StrEnum):
    """Final outcome of the orchestration workflow."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    DENIED = "DENIED"


class TrustLevel(StrEnum):
    """Trust classification for RAG-retrieved documents.

    Documents are treated as untrusted data for execution purposes.
    Trust level is metadata for audit and context weighting only —
    it cannot override contracts or security policy.
    """
    ORGANIZATION_APPROVED = "organization-approved"
    TEAM_CONTRIBUTED = "team-contributed"
    AUTO_GENERATED = "auto-generated"


class DocumentType(StrEnum):
    """Knowledge base document categories."""
    ARCHITECTURE = "architecture"
    RUNBOOK = "runbook"
    INCIDENT = "incident"
    CONTRACT = "contract"
