import pytest
from core.enums import ActionType, RiskLevel, Severity
from core.models import PlannedAction, RemediationPlan
from core.contracts import OperationalContract
from core.guardrails.risk import RiskEvaluator
from examples.incident_commander.domain.models import Incident

@pytest.fixture
def mock_incident():
    return Incident(
        incident_id="INC-1",
        service="checkout-service",
        environment="prod",
        severity=Severity.HIGH,
        title="Latency",
        description="High latency",
        metrics={"error_rate": 0.05, "healthy_pods": 5, "total_pods": 5},
        active_checkout_connections=True
    )

@pytest.fixture
def mock_contract():
    return OperationalContract(
        contract_id="C-1",
        service="checkout-service",
        environment="prod",
        allowed_actions=["restart_pods", "rollback_deployment"]
    )

def test_risk_evaluator_v2_numeric(mock_incident, mock_contract):
    evaluator = RiskEvaluator()
    
    plan = RemediationPlan(
        summary="Restart pods",
        actions=[
            PlannedAction(action=ActionType.RESTART_PODS, rationale="Fix latency")
        ],
        estimated_impact="Low"
    )
    
    score, level, needs_approval = evaluator.evaluate(plan, mock_incident, mock_contract)
    
    # Base score for HIGH severity = 25
    # Active checkout = 15
    # 1 action = 5
    # Total = 45 -> MEDIUM (31-50) -> Needs approval
    
    assert score == 45
    assert level == RiskLevel.MEDIUM
    assert needs_approval is True

def test_risk_evaluator_v2_critical(mock_incident, mock_contract):
    evaluator = RiskEvaluator()
    
    mock_incident.severity = Severity.CRITICAL
    
    plan = RemediationPlan(
        summary="Rollback deployment",
        actions=[
            PlannedAction(action=ActionType.ROLLBACK_DEPLOYMENT, rationale="Revert bad deployment")
        ],
        estimated_impact="High"
    )
    
    score, level, needs_approval = evaluator.evaluate(plan, mock_incident, mock_contract)
    
    # CRITICAL severity = 40
    # Active checkout = 15
    # 1 action = 5
    # Rollback = 20
    # Total = 80 -> CRITICAL (71-100) -> Needs approval
    
    assert score == 80
    assert level == RiskLevel.CRITICAL
    assert needs_approval is True
