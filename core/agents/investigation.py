"""Investigation agent for gathering context.

The InvestigationAgent searches organizational knowledge (runbooks,
architecture docs, historical incidents) to build a context dossier
for the PlannerAgent.
"""

from __future__ import annotations

import logging
from typing import Any

from core.models import BaseIncident as Incident
from core.knowledge.retriever import KnowledgeRetriever

logger = logging.getLogger(__name__)


class InvestigationAgent:
    """Agent responsible for context gathering via RAG."""

    def __init__(self, collection: Any, top_k: int = 3) -> None:
        self.retriever = KnowledgeRetriever(collection=collection, top_k=top_k)
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def investigate(self, incident: Incident) -> list[dict[str, Any]]:
        """Gather context for an incident.
        
        Returns:
            A list of retrieved document dicts.
        """
        service = incident.service
        environment = incident.environment or "production"

        query = (
            f"Service: {service}, Environment: {environment}. "
            f"Logs: {incident.logs}. "
            f"Error rate: {incident.metrics.get('error_rate', 'N/A') if incident.metrics else 'N/A'}"
        )

        results: list[dict[str, Any]] = []
        try:
            documents = self.retriever.retrieve(
                query=query, service=service, environment=environment
            )
            self._logger.info("Gathered %d documents for %s", len(documents), service)
            results = [
                {
                    "content": doc.content,
                    "metadata": doc.metadata.model_dump(mode="json"),
                    "relevance_score": doc.relevance_score,
                }
                for doc in documents
            ]
        except Exception as e:
            self._logger.warning("RAG retrieval failed: %s", e)

        # GraphRAG: enrich with the service's blast radius from the Neo4j
        # dependency graph so the planner reasons about impact, not just symptoms.
        graph_doc = self._blast_radius_context(service)
        if graph_doc:
            results.insert(0, graph_doc)
        return results

    def _blast_radius_context(self, service: str) -> dict[str, Any] | None:
        try:
            from core.knowledge.graph import blast_radius

            br = blast_radius(service)
        except Exception:
            br = None
        if not br:
            return None
        impacted = br.get("impacted_services", [])
        critical = br.get("critical_dependents", [])
        depends_on = br.get("depends_on", [])
        content = (
            f"SERVICE DEPENDENCY GRAPH — blast radius for '{service}':\n"
            f"- Directly depends on: {', '.join(depends_on) or 'none'}\n"
            f"- Downstream services impacted if '{service}' is disrupted: "
            f"{', '.join(impacted) or 'none'}\n"
            f"- CRITICAL dependents at risk: {', '.join(critical) or 'none'}\n"
            "Prefer non-disruptive remediation and connection draining when critical "
            "dependents are present."
        )
        self._logger.info(
            "Blast radius for %s: %d impacted (%d critical)", service, len(impacted), len(critical)
        )
        return {
            "content": content,
            "metadata": {
                "document_type": "dependency_graph",
                "service": service,
                "trust_level": "organization-approved",
                "source": "neo4j",
            },
            "relevance_score": 1.0,
        }
