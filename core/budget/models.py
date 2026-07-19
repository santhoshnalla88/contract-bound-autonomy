from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

class BudgetType(str, Enum):
    """Types of execution budgets."""
    TOKEN = "token"            # LLM token limits
    COST = "cost"              # Total USD limits
    TIME = "time"              # Execution time limits (ms/s)
    TOOL_CALL = "tool_call"    # Limits on number of tool calls

class Budget(BaseModel):
    """A configured limit for a specific budget type."""
    budget_type: BudgetType
    limit: float
    description: str = ""

class BudgetLedgerEntry(BaseModel):
    """A record of consumption against a budget."""
    entry_id: str
    incident_id: str
    budget_type: BudgetType
    amount: float
    agent_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, str] = Field(default_factory=dict)
