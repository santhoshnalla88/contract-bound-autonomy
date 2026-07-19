"""Neo4j service-dependency graph — GraphRAG blast-radius enrichment.

RAG (vector search) answers *"what do the runbooks say?"*; the graph answers
*"what else breaks if I touch this service?"* — a question vector similarity
can't. We model the microservice topology as a directed dependency graph and,
during investigation, query the **blast radius** (upstream dependents) of the
affected service so the planner reasons about impact, not just symptoms.

Graceful by design: if Neo4j is unavailable the driver returns empty results and
the workflow proceeds on RAG alone — the graph *enriches*, it never blocks.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Built-in fallback topology, used only when no topology file is provided.
# An organization supplies its OWN topology via knowledge/topology.json (see
# `_load_topology`) — this default just lets the demo run out of the box.
# "A DEPENDS_ON B" means A breaks if B is degraded — so B's blast radius includes A.
_TOPOLOGY: list[tuple[str, str]] = [
    ("checkout-service", "inventory-service"),
    ("checkout-service", "payment-gateway"),
    ("api-gateway", "checkout-service"),
    ("api-gateway", "inventory-service"),
    ("inventory-service", "inventory-db"),
    ("inventory-service", "cache-redis"),
    ("payment-gateway", "cache-redis"),
    ("settlement-worker", "payment-gateway"),
    ("mobile-bff", "api-gateway"),
]
_CRITICALITY: dict[str, str] = {
    "checkout-service": "CRITICAL",
    "payment-gateway": "CRITICAL",
    "api-gateway": "HIGH",
    "inventory-service": "HIGH",
    "settlement-worker": "MEDIUM",
}


def _load_topology(
    settings: Settings,
) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """Load the service topology from ``knowledge/topology.json`` if present.

    File format (all fields optional)::

        {
          "dependencies": [{"service": "checkout-service", "depends_on": "inventory-service"}, ...],
          "criticality":  {"checkout-service": "CRITICAL", ...}
        }

    Falls back to the built-in demo topology when the file is absent or invalid,
    so the graph always seeds *something* rather than blocking startup.
    """
    path = settings.knowledge_dir / "topology.json"
    if not path.exists():
        return _TOPOLOGY, _CRITICALITY
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        edges = [
            (d["service"], d["depends_on"])
            for d in data.get("dependencies", [])
            if d.get("service") and d.get("depends_on")
        ]
        criticality = dict(data.get("criticality", {}))
        if not edges:
            logger.warning("topology.json has no dependencies — using built-in topology")
            return _TOPOLOGY, _CRITICALITY
        logger.info("Loaded service topology from %s (%d edges)", path, len(edges))
        return edges, criticality
    except Exception:
        logger.warning("Failed to parse %s — using built-in topology", path)
        return _TOPOLOGY, _CRITICALITY


class ServiceGraph:
    """Thin wrapper over the Neo4j driver for dependency queries."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def verify(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    def seed(
        self,
        topology: list[tuple[str, str]] | None = None,
        criticality: dict[str, str] | None = None,
    ) -> int:
        """Create the service topology (idempotent via MERGE). Returns edge count.

        Pass an org-specific ``topology``/``criticality`` (see ``_load_topology``);
        omit both to use the built-in demo topology.
        """
        topology = topology if topology is not None else _TOPOLOGY
        criticality = criticality if criticality is not None else _CRITICALITY
        with self._driver.session() as session:
            session.run("MATCH (n:Service) DETACH DELETE n")
            for dependent, dependency in topology:
                session.run(
                    """
                    MERGE (a:Service {name: $a})
                    MERGE (b:Service {name: $b})
                    MERGE (a)-[:DEPENDS_ON]->(b)
                    """,
                    a=dependent,
                    b=dependency,
                )
            for name, crit in criticality.items():
                session.run(
                    "MERGE (s:Service {name: $name}) SET s.criticality = $crit",
                    name=name,
                    crit=crit,
                )
        return len(topology)

    def blast_radius(self, service: str) -> dict[str, Any]:
        """Return services impacted if ``service`` is degraded/restarted.

        Downstream dependents are everything that (transitively) DEPENDS_ON it.
        """
        with self._driver.session() as session:
            rec = session.run(
                """
                MATCH (dependent:Service)-[:DEPENDS_ON*1..4]->(target:Service {name: $name})
                RETURN DISTINCT dependent.name AS name, dependent.criticality AS criticality
                ORDER BY name
                """,
                name=service,
            ).data()
            deps = session.run(
                """
                MATCH (target:Service {name: $name})-[:DEPENDS_ON]->(dep:Service)
                RETURN dep.name AS name ORDER BY name
                """,
                name=service,
            ).data()
        impacted = [r["name"] for r in rec]
        critical = [r["name"] for r in rec if r.get("criticality") == "CRITICAL"]
        return {
            "service": service,
            "impacted_services": impacted,
            "critical_dependents": critical,
            "depends_on": [d["name"] for d in deps],
        }


_graph: ServiceGraph | None = None


def get_service_graph(settings: Settings | None = None) -> ServiceGraph | None:
    """Return a connected ServiceGraph, or None if disabled/unavailable."""
    global _graph
    s = settings or get_settings()
    if not s.graph_enabled:
        return None
    if _graph is not None:
        return _graph
    try:
        g = ServiceGraph(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
        if not g.verify():
            g.close()
            logger.warning("Neo4j not reachable at %s — graph enrichment disabled", s.neo4j_uri)
            return None
        _graph = g
        return _graph
    except Exception:
        logger.warning("Neo4j driver init failed — graph enrichment disabled")
        return None


def seed_service_graph(settings: Settings) -> None:
    """Seed the dependency topology at startup (best-effort)."""
    g = get_service_graph(settings)
    if g is None:
        return
    topology, criticality = _load_topology(settings)
    n = g.seed(topology, criticality)
    logger.info("Neo4j service-dependency graph seeded (%d edges)", n)


def blast_radius(service: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Convenience: blast radius for a service, or None if graph unavailable."""
    g = get_service_graph(settings)
    if g is None:
        return None
    try:
        return g.blast_radius(service)
    except Exception:
        logger.exception("Blast-radius query failed for %s", service)
        return None
