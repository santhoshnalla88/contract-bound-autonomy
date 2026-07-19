"""Anomaly generator for synthetic payments incidents."""

import random
from core.enums import Severity
from examples.payments_commander.domain.models import PaymentsIncident, PaymentsMetrics

class AnomalyGenerator:
    """Generates synthetic incidents for the payments domain."""
    
    @staticmethod
    def generate_high_decline_rate() -> PaymentsIncident:
        return PaymentsIncident(
            incident_id=f"PAY-{random.randint(1000, 9999)}",
            service="gateway-service",
            environment="production",
            severity=Severity.HIGH,
            logs="Multiple card networks returning 5xx errors",
            metrics=PaymentsMetrics(
                decline_rate=15.5,
                latency_ms=1200.0,
                active_merchants=5000
            ),
            requires_pci_audit=True,
            context={"gateway": "stripe", "region": "us-east"}
        )
        
    @staticmethod
    def generate_merchant_fraud_spike() -> PaymentsIncident:
        return PaymentsIncident(
            incident_id=f"PAY-{random.randint(1000, 9999)}",
            service="fraud-detection",
            environment="production",
            severity=Severity.CRITICAL,
            logs="Unusual volume of chargebacks for merchant ID M-492",
            metrics=PaymentsMetrics(
                decline_rate=5.0,
                latency_ms=250.0,
                active_merchants=5000
            ),
            requires_pci_audit=False,
            context={"merchant_id": "M-492", "chargeback_volume": 15000.0}
        )
