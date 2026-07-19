"""Manager for tracking and updating agent trust scores."""

import logging
from core.trust.models import TrustScore

logger = logging.getLogger(__name__)


class TrustManager:
    """Manages trust scores for agents.
    
    In a real system, this would persist to a database.
    For this MVP, it uses an in-memory dictionary.
    """
    
    def __init__(self):
        self._scores: dict[str, TrustScore] = {}
        
    def get_score(self, agent_id: str, domain: str = "global") -> TrustScore:
        """Get or initialize a trust score for an agent."""
        key = f"{agent_id}::{domain}"
        if key not in self._scores:
            self._scores[key] = TrustScore(agent_id=agent_id, domain=domain)
        return self._scores[key]
        
    def record_success(self, agent_id: str, domain: str = "global") -> TrustScore:
        """Record a successful remediation by the agent."""
        score = self.get_score(agent_id, domain)
        score.success_count += 1
        logger.info(f"Recorded success for {agent_id}. New score: {score.score:.2f}")
        return score
        
    def record_failure(self, agent_id: str, domain: str = "global") -> TrustScore:
        """Record a failed remediation by the agent."""
        score = self.get_score(agent_id, domain)
        score.failure_count += 1
        logger.info(f"Recorded failure for {agent_id}. New score: {score.score:.2f}")
        return score
        
    def record_escalation(self, agent_id: str, domain: str = "global") -> TrustScore:
        """Record an escalation by the agent."""
        score = self.get_score(agent_id, domain)
        score.escalation_count += 1
        logger.info(f"Recorded escalation for {agent_id}. New score: {score.score:.2f}")
        return score
        
    def record_guardrail_rejection(self, agent_id: str, domain: str = "global") -> TrustScore:
        """Record a guardrail rejection for the agent's plan."""
        score = self.get_score(agent_id, domain)
        score.guardrail_rejections += 1
        logger.info(f"Recorded guardrail rejection for {agent_id}. New score: {score.score:.2f}")
        return score
