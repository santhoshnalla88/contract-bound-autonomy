"""Domain models for payments incident commander."""
from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Any
from core.models import BaseIncident
from core.enums import Severity

class PaymentsMetrics(BaseModel):
    decline_rate: float = Field(..., ge=0, description="Decline rate percentage")
    latency_ms: float = Field(..., ge=0, description="Average transaction latency in ms")
    active_merchants: int = Field(..., ge=0, description="Number of active merchants")

class PaymentsIncident(BaseIncident):
    incident_id: str = Field(..., pattern=r"^PAY-\d+$", description="Unique incident identifier")
    metrics: PaymentsMetrics
    requires_pci_audit: bool = Field(default=False)
    
class Transaction(BaseModel):
    transaction_id: str
    merchant_id: str
    amount: float
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Merchant(BaseModel):
    merchant_id: str
    name: str
    status: str
    risk_score: int
