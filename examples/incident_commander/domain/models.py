"""Domain models for incident commander."""
from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from core.enums import Severity

from core.models import BaseIncident

class IncidentMetrics(BaseModel):
    error_rate: float = Field(..., ge=0, description="Error rate percentage")
    healthy_pods: int = Field(..., ge=0, description="Number of healthy pods")
    total_pods: int = Field(..., ge=0, description="Total pod count")

class Incident(BaseIncident):
    incident_id: str = Field(..., pattern=r"^INC-\d+$", description="Unique incident identifier")
    metrics: IncidentMetrics
    active_checkout_connections: bool = Field(default=False)
