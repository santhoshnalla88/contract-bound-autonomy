import pytest
from core.enums import ActionType, GuardrailStatus
from core.models import NormalizedAction
from examples.incident_commander.domain.models import IncidentMetrics
from core.contracts import OperationalContract, ContractLimits, AvailabilityConstraints
from core.guardrails.validators import validate_action_allowed, validate_limits, validate_availability
from core.guardrails.engine import GuardrailEngine

@pytest.fixture
def test_contract():
    return OperationalContract(
        contract_id="test",
        service="test",
        environment="prod",
        allowed_actions=["restart_pods", "scale_deployment"],
        forbidden_actions=["drop_database"],
        limits=ContractLimits(max_pod_restarts_per_incident=2, max_replicas=10),
        availability_constraints=AvailabilityConstraints(minimum_available_replicas=2)
    )

def test_validate_action_allowed(test_contract):
    valid_action = NormalizedAction(action=ActionType.RESTART_PODS, target="test")
    assert not validate_action_allowed(valid_action, test_contract)
    
    invalid_action = NormalizedAction(action=ActionType.ROLLBACK_DEPLOYMENT, target="test")
    violations = validate_action_allowed(invalid_action, test_contract)
    assert len(violations) == 1

def test_validate_limits(test_contract):
    action = NormalizedAction(action=ActionType.RESTART_PODS, target="test", parameters={"count": 3})
    violations = validate_limits(action, test_contract, [])
    assert len(violations) == 1 # Exceeds max 2

def test_guardrail_engine(test_contract):
    engine = GuardrailEngine()
    
    # Valid
    actions = [NormalizedAction(action=ActionType.RESTART_PODS, target="test", parameters={"count": 1})]
    result = engine.evaluate(actions, test_contract, [], {"total_pods": 5, "healthy_pods": 3})
    assert result.status == GuardrailStatus.APPROVED
    
    # Invalid (limit exceeded)
    actions = [NormalizedAction(action=ActionType.RESTART_PODS, target="test", parameters={"count": 5})]
    result = engine.evaluate(actions, test_contract, [], {"total_pods": 5, "healthy_pods": 3})
    assert result.status == GuardrailStatus.REJECTED
