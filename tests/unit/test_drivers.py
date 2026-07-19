"""Execution driver + MCP client behaviour (mock backend)."""

import pytest

from core.enums import ActionType
from core.models import NormalizedAction
from core.execution.client import MCPClient, get_mcp_client, reset_mcp_clients
from core.execution.drivers.mock import MockDriver


def test_mock_driver_restart_improves_health():
    driver = MockDriver()
    before = driver.get_metrics("inventory-service")["healthy_pods"]
    result = driver.restart_pods("inventory-service", 2)
    assert result["success"]
    after = driver.get_metrics("inventory-service")["healthy_pods"]
    assert after > before


def test_mcp_client_allowlist_blocks_read_actions():
    client = MCPClient(driver=MockDriver())
    action = NormalizedAction(action=ActionType.GET_METRICS, target="inventory-service")
    result = client.execute_action(action)
    assert result.success is False
    assert "allowlist" in (result.error or "")


def test_per_incident_client_isolation():
    reset_mcp_clients()
    a = get_mcp_client("INC-A")
    b = get_mcp_client("INC-B")
    same = get_mcp_client("INC-A")
    assert a is same
    assert a is not b
    reset_mcp_clients()
