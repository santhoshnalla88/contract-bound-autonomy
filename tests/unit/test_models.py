import pytest
from pathlib import Path
from pydantic import ValidationError

from core.enums import Severity
from core.models import PostconditionRule, PostconditionResult
from examples.incident_commander.domain.models import Incident

def test_incident_validation():
    # Valid incident
    inc = Incident(
        incident_id="INC-123",
        service="inventory",
        environment="production",
        severity=Severity.HIGH,
        metrics={"error_rate": 5.0, "healthy_pods": 2, "total_pods": 5}
    )
    assert inc.incident_id == "INC-123"
    
    # Invalid incident_id
    with pytest.raises(ValidationError):
        Incident(
            incident_id="123",
            service="inventory",
            environment="production",
            severity=Severity.HIGH,
            metrics={"error_rate": 5.0, "healthy_pods": 2, "total_pods": 5}
        )

def test_postcondition_rule_parsing():
    rule = PostconditionRule.from_string("healthy_pod_count >= 3")
    assert rule.metric == "healthy_pod_count"
    assert rule.operator == ">="
    assert rule.threshold == 3.0
    
    assert rule.evaluate(4) is True
    assert rule.evaluate(2) is False

    with pytest.raises(ValueError):
        PostconditionRule.from_string("invalid_format")
