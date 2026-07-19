import pytest
from core.enums import ActionType
from core.models import NormalizedAction
from core.compliance.models import PolicyRule, PolicyPack
from core.compliance.evaluator import PolicyEvaluator

def test_policy_rule_evaluation():
    rule = PolicyRule(
        rule_id="PCI-01",
        description="No rollbacks",
        forbidden_actions=["rollback_deployment"]
    )
    
    action1 = NormalizedAction(action=ActionType.ROLLBACK_DEPLOYMENT, target="users-db")
    action2 = NormalizedAction(action=ActionType.RESTART_PODS, target="users-db")
    
    assert rule.evaluate(action1) is not None
    assert rule.evaluate(action2) is None

def test_policy_evaluator():
    pack = PolicyPack(
        pack_id="GDPR",
        name="GDPR Compliance",
        description="Data protection rules",
        rules=[
            PolicyRule(
                rule_id="GDPR-01",
                description="No rollback on auth service",
                forbidden_actions=["rollback_deployment"],
                forbidden_targets=["auth-service"]
            )
        ]
    )
    
    evaluator = PolicyEvaluator([pack])
    
    # Violates target
    action1 = NormalizedAction(action=ActionType.RESTART_PODS, target="auth-service")
    res1 = evaluator.evaluate([action1])
    assert not res1.is_compliant
    assert len(res1.violations) == 1
    
    # Violates action
    action2 = NormalizedAction(action=ActionType.ROLLBACK_DEPLOYMENT, target="other-service")
    res2 = evaluator.evaluate([action2])
    assert not res2.is_compliant
    
    # Compliant
    action3 = NormalizedAction(action=ActionType.RESTART_PODS, target="other-service")
    res3 = evaluator.evaluate([action3])
    assert res3.is_compliant
