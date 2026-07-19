"""Trust and reputation models for the autonomous agent system."""

from pydantic import BaseModel, Field


class TrustScore(BaseModel):
    """A rolling scorecard for an agent's historical performance."""
    agent_id: str = Field(..., description="Unique ID of the agent")
    domain: str = Field("global", description="Domain of expertise (e.g. database, network)")
    success_count: int = Field(0, description="Number of successful remediations")
    failure_count: int = Field(0, description="Number of failed remediations")
    escalation_count: int = Field(0, description="Number of escalated cases")
    guardrail_rejections: int = Field(0, description="Number of times guardrails rejected plans")
    
    @property
    def score(self) -> float:
        """Calculate a 0.0 to 1.0 trust score based on history.
        
        Formula: (successes) / (total_attempts) penalized by guardrail rejections.
        """
        total = self.success_count + self.failure_count + self.escalation_count
        if total == 0:
            return 0.5  # Neutral starting score
            
        base_score = self.success_count / total
        
        # Penalize for proposing illegal actions
        rejection_penalty = min(0.3, self.guardrail_rejections * 0.05)
        
        final_score = max(0.0, min(1.0, base_score - rejection_penalty))
        return final_score
