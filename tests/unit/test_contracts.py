import pytest
from pathlib import Path

from core.contracts import ContractLoader, OperationalContract

@pytest.fixture
def mock_contracts_dir(tmp_path):
    contract_data = """
    {
      "contract_id": "test-contract",
      "service": "test-service",
      "environment": "production",
      "version": "1.0.0",
      "allowed_actions": ["restart_pods"],
      "forbidden_actions": ["drop_database"],
      "limits": {
        "max_pod_restarts_per_incident": 2,
        "max_replicas": 10,
        "max_scale_up_percentage": 200
      }
    }
    """
    contract_file = tmp_path / "test-service-contract.json"
    contract_file.write_text(contract_data)
    return tmp_path

def test_contract_loader(mock_contracts_dir):
    loader = ContractLoader(mock_contracts_dir)
    contract = loader.load("test-service", "production")
    
    assert contract.service == "test-service"
    assert "restart_pods" in contract.allowed_actions
    assert contract.is_action_allowed("restart_pods") is True
    assert contract.is_action_allowed("scale_deployment") is False
    assert contract.is_action_forbidden("drop_database") is True
    
    with pytest.raises(FileNotFoundError):
        loader.load("unknown-service", "production")
