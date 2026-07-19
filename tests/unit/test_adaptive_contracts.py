import pytest
from core.contracts.contracts import OperationalContract, ContractLimits
from core.contracts.adaptive import (
    AdaptiveRule, 
    RuleMutation, 
    AdaptiveContext, 
    AdaptiveContractResolver
)

@pytest.fixture
def base_contract():
    return OperationalContract(
        contract_id="test",
        service="test-service",
        environment="prod",
        allowed_actions=["restart_pods", "scale_deployment"],
        limits=ContractLimits(max_replicas=10, max_pod_restarts_per_incident=5)
    )

def test_adaptive_rule_matches():
    rule = AdaptiveRule(
        rule_id="critical_severity",
        description="Limit scale up on critical incidents",
        min_severity_level="CRITICAL",
        mutation=RuleMutation(override_max_replicas=2)
    )
    
    # Matches exact severity
    context_match = AdaptiveContext(incident_severity="CRITICAL", environment="prod")
    assert rule.matches(context_match)
    
    # Does not match other severity
    context_no_match = AdaptiveContext(incident_severity="HIGH", environment="prod")
    assert not rule.matches(context_no_match)

def test_adaptive_contract_resolver(base_contract):
    rules = [
        AdaptiveRule(
            rule_id="low_trust",
            description="Remove scale action if trust is low",
            max_trust_score=30.0,
            mutation=RuleMutation(remove_allowed_actions=["scale_deployment"])
        )
    ]
    
    resolver = AdaptiveContractResolver(rules)
    
    # Trust is 50, rule shouldn't match
    ctx_high_trust = AdaptiveContext(incident_severity="HIGH", environment="prod", trust_score=50.0)
    effective_contract = resolver.resolve_effective_contract(base_contract, ctx_high_trust)
    assert "scale_deployment" in effective_contract.allowed_actions
    
    # Trust is 20, rule matches
    ctx_low_trust = AdaptiveContext(incident_severity="HIGH", environment="prod", trust_score=20.0)
    effective_contract = resolver.resolve_effective_contract(base_contract, ctx_low_trust)
    assert "scale_deployment" not in effective_contract.allowed_actions
    
def test_adaptive_resolver_enforces_ceilings(base_contract):
    # If a rule tries to increase limits beyond the base contract, it should be capped.
    rule = AdaptiveRule(
        rule_id="try_increase",
        description="Try to increase replicas",
        mutation=RuleMutation(override_max_replicas=100) # Base limit is 10
    )
    
    resolver = AdaptiveContractResolver([rule])
    ctx = AdaptiveContext(incident_severity="LOW", environment="prod")
    
    effective_contract = resolver.resolve_effective_contract(base_contract, ctx)
    assert effective_contract.limits.max_replicas == 10 # Capped at base limit
