"""Vector-store bootstrap — populate ChromaDB from the knowledge base at startup.

Uses Chroma's built-in local embedding model (ONNX all-MiniLM-L6-v2) by default:
no API key, no quota ceiling, works offline, and — crucially — the *same*
embedding function the retrieval node uses, so ingest and query vectors match.
Ingestion is content-hash idempotent, so re-running on every boot is cheap.
"""

from __future__ import annotations

import logging

import chromadb

from core.config import Settings
from core.knowledge.ingestion import KnowledgeIngestion

logger = logging.getLogger(__name__)


def ingest_knowledge(settings: Settings) -> int:
    """Ingest the knowledge base into the Chroma vector store. Returns new chunks."""
    settings.chroma_db_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(settings.chroma_db_dir))

    ingestion = KnowledgeIngestion(
        knowledge_dir=settings.knowledge_dir,
        chroma_client=client,
        collection_name=settings.chroma_collection_name,
        # None → Chroma's default local ONNX embeddings (matches the retrieval node).
        embedding_function=None,
    )
    new_chunks = ingestion.ingest_all()
    try:
        col = client.get_or_create_collection(settings.chroma_collection_name)
        logger.info("Vector store ready: %d chunks total (%d new this boot)", col.count(), new_chunks)
    except Exception:
        logger.exception("Could not read vector-store count")
    return new_chunks
