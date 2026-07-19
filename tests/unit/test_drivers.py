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


# --- Target-neutral verbs + driver registry (integrate any workload) ---------

def test_mock_driver_handles_generic_verbs():
    """Servers/batch/cloud verbs are simulated so any contract runs offline."""
    driver = MockDriver()
    for verb in ("run_command", "restart_service", "run_batch_job", "http_request"):
        result = driver.execute(verb, "orders-api", {"command": "flush_cache"})
        assert result["success"], verb
        assert result["simulated"] is True


def test_mcp_client_allows_generic_verbs():
    client = MCPClient(driver=MockDriver())
    action = NormalizedAction(
        action=ActionType.RUN_BATCH_JOB, target="nightly-etl", parameters={"job": "reconcile"}
    )
    result = client.execute_action(action)
    assert result.success is True


def test_driver_registry_register_and_select():
    from core.config import Settings
    from core.execution.drivers import (
        available_backends,
        create_driver,
        register_driver,
    )

    assert "mock" in available_backends()
    assert "kubernetes" in available_backends()

    sentinel = MockDriver()
    register_driver("custom-test", lambda _s: sentinel)
    assert "custom-test" in available_backends()

    settings = Settings(execution_backend="custom-test")
    assert create_driver(settings) is sentinel


def test_driver_registry_unknown_backend_raises():
    from core.config import Settings
    from core.execution.drivers import create_driver

    with pytest.raises(ValueError, match="Unknown EXECUTION_BACKEND"):
        create_driver(Settings(execution_backend="does-not-exist"))


def test_host_command_driver_allowlist_and_quoting():
    """Reference driver runs only allowlisted commands; params are shell-quoted."""
    from examples.host_commander.drivers.host_command import HostCommandDriver

    driver = HostCommandDriver(commands={"echo_ok": "echo {target}"}, transport="local")

    # Not in the allowlist -> refused, nothing executed.
    blocked = driver.execute("run_command", "orders-api", {"command": "rm_rf_root"})
    assert blocked["success"] is False
    assert "allowlist" in blocked["error"]

    # Allowlisted command runs; injection attempt is neutralised by shell-quoting.
    ran = driver.execute("run_command", "orders-api; rm -rf /", {"command": "echo_ok"})
    assert ran["success"] is True
    assert "rm -rf" in ran["stdout"]  # printed as literal text, NOT executed
