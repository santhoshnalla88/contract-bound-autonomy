"""Memory store for persisting and retrieving agent memory."""

import logging
import uuid
from typing import Any
from datetime import datetime, timezone

from core.memory.models import MemoryItem, MemoryScope, MemoryQuery

logger = logging.getLogger(__name__)


class MemoryStore:
    """Abstract memory store.
    
    In a production system, this would be backed by pgvector.
    For this MVP, it uses an in-memory dictionary.
    """
    
    def __init__(self):
        self._memories: dict[str, MemoryItem] = {}
        
    def store(
        self,
        scope: MemoryScope,
        agent_role: str,
        content: str,
        incident_id: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> MemoryItem:
        """Store a new memory."""
        item = MemoryItem(
            id=str(uuid.uuid4()),
            scope=scope,
            agent_role=agent_role,
            incident_id=incident_id,
            content=content,
            metadata=metadata or {},
            timestamp=datetime.now(timezone.utc)
        )
        self._memories[item.id] = item
        logger.info(f"Stored {scope.value} memory for {agent_role} (id: {item.id})")
        return item
        
    def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        """Retrieve memories matching the query.
        
        This mock implementation does naive substring matching.
        A real implementation would use vector embeddings.
        """
        results = []
        for item in self._memories.values():
            if item.agent_role != query.agent_role:
                continue
            if query.scope and item.scope != query.scope:
                continue
            if query.incident_id and item.incident_id != query.incident_id:
                continue
                
            # Naive semantic search fallback
            if query.query.lower() in item.content.lower():
                results.append(item)
                
        # Sort by latest
        results.sort(key=lambda x: x.timestamp, reverse=True)
        return results[:query.top_k]
