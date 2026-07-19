"""Mock execution driver for payments domain."""
from __future__ import annotations
from typing import Any
from datetime import datetime, timezone
import logging

from core.execution.drivers.base import ExecutionDriver

logger = logging.getLogger(__name__)

class PaymentsDriver(ExecutionDriver):
    """Simulates execution of payments actions."""

    def __init__(self) -> None:
        self._state = {
            "merchants_blocked": set(),
            "transactions_refunded": set(),
            "gateway_routes": {"default": "primary_gateway"}
        }

    def execute(self, action: str, target: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Execute a domain-specific action."""
        if action == "block_merchant":
            merchant_id = parameters.get("merchant_id", target)
            self._state["merchants_blocked"].add(merchant_id)
            return {
                "success": True, 
                "merchant_id": merchant_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        if action == "refund_transaction":
            transaction_id = parameters.get("transaction_id", target)
            self._state["transactions_refunded"].add(transaction_id)
            return {
                "success": True, 
                "transaction_id": transaction_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        if action == "reroute_gateway":
            gateway = parameters.get("gateway", target)
            self._state["gateway_routes"]["default"] = gateway
            return {
                "success": True, 
                "new_gateway": gateway,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        return {"success": False, "error": f"Unknown action: {action}"}

    def get_service_status(self, service: str) -> dict[str, Any]:
        """Mock status."""
        return {"success": True, "status": "operational", "service": service}

    def get_metrics(self, service: str) -> dict[str, Any]:
        """Mock metrics."""
        return {"success": True, "decline_rate": 5.0, "latency_ms": 200, "service": service}
