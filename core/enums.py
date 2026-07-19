"""Core enumerations for the orchestrator."""

from enum import Enum, StrEnum

class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class ActionType(str, Enum):
    """Supported remediation actions."""
    RESTART_PODS = "restart_pods"
    SCALE_DEPLOYMENT = "scale_deployment"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    GET_SERVICE_STATUS = "get_service_status"
    GET_METRICS = "get_metrics"
    
    # Payments domain actions
    BLOCK_MERCHANT = "block_merchant"
    REFUND_TRANSACTION = "refund_transaction"
    REROUTE_GATEWAY = "reroute_gateway"
    # Will be made extensible in future phases

class GuardrailStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class FinalStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    DENIED = "DENIED"

class TrustLevel(StrEnum):
    ORGANIZATION_APPROVED = "organization-approved"
    TEAM_CONTRIBUTED = "team-contributed"
    AUTO_GENERATED = "auto-generated"

class DocumentType(StrEnum):
    ARCHITECTURE = "architecture"
    RUNBOOK = "runbook"
    INCIDENT = "incident"
    CONTRACT = "contract"
