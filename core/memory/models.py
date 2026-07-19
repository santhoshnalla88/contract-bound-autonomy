"""Memory models for the autonomous agent system."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class MemoryScope(str, Enum):
    """Scope of a memory item."""
    SHORT_TERM = "SHORT_TERM"  # Bound to a specific incident/case
    LONG_TERM = "LONG_TERM"    # Cross-case agent learning


class MemoryItem(BaseModel):
    """A discrete piece of memory."""
    id: str = Field(..., description="Unique memory ID")
    scope: MemoryScope = Field(..., description="Scope of the memory")
    agent_role: str = Field(..., description="Role of the agent that stored this memory")
    incident_id: str | None = Field(None, description="Associated incident if short-term")
    content: str = Field(..., description="The semantic content of the memory")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional structured metadata")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MemoryQuery(BaseModel):
    """A query to retrieve memory context."""
    agent_role: str
    scope: MemoryScope | None = None
    incident_id: str | None = None
    query: str
    top_k: int = 5
