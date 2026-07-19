"""RAG knowledge ingestion module.

Walks the knowledge directory for Markdown documents, splits them into
overlapping chunks, extracts metadata from the directory structure, and
upserts them into a ChromaDB collection with content-hash-based
idempotency.

Contract JSON files are deliberately excluded — they are loaded
deterministically by ContractLoader, not via vector search.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.knowledge.metadata import DocumentMetadata, extract_metadata_from_path

logger = logging.getLogger(__name__)


class KnowledgeIngestion:
    """Ingests Markdown knowledge documents into ChromaDB.

    Responsibilities:
        - Discover .md files in the knowledge directory tree
        - Skip .json contract files (those are loaded deterministically)
        - Chunk documents using RecursiveCharacterTextSplitter
        - Extract metadata from the directory structure
        - Generate content hashes for idempotent upserts
        - Add documents + metadata to a ChromaDB collection

    Args:
        knowledge_dir: Root directory containing the knowledge base.
        chroma_client: An initialized ChromaDB client instance.
        collection_name: Name of the ChromaDB collection to use.
        embedding_function: ChromaDB-compatible embedding function.
    """

    def __init__(
        self,
        knowledge_dir: Path,
        chroma_client: chromadb.ClientAPI,
        collection_name: str,
        embedding_function: Any,
    ) -> None:
        self.knowledge_dir = knowledge_dir
        self.chroma_client = chroma_client
        self.collection_name = collection_name
        self.embedding_function = embedding_function

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
        )

    def _get_or_create_collection(self) -> chromadb.Collection:
        """Get or create the ChromaDB collection with the embedding function."""
        return self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _content_hash(content: str) -> str:
        """Generate a deterministic SHA-256 hash for content deduplication.

        Args:
            content: The text content to hash.

        Returns:
            Hex-encoded SHA-256 digest.
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _discover_markdown_files(self) -> list[Path]:
        """Discover all Markdown files in the knowledge directory.

        Skips JSON contract files — those are loaded deterministically
        by ContractLoader and must NOT enter the vector store.

        Returns:
            Sorted list of .md file paths.
        """
        if not self.knowledge_dir.exists():
            logger.warning("Knowledge directory does not exist: %s", self.knowledge_dir)
            return []

        md_files = sorted(self.knowledge_dir.rglob("*.md"))
        logger.info(
            "Discovered %d Markdown files in %s",
            len(md_files),
            self.knowledge_dir,
        )
        return md_files

    def _metadata_to_chroma_dict(self, metadata: DocumentMetadata, source_file: str, chunk_index: int) -> dict[str, Any]:
        """Convert DocumentMetadata to a flat dict for ChromaDB storage.

        ChromaDB metadata values must be str, int, float, or bool.

        Args:
            metadata: The parsed document metadata.
            source_file: Path string of the source file.
            chunk_index: Index of this chunk within the source document.

        Returns:
            Flat dictionary suitable for ChromaDB metadata.
        """
        return {
            "service": metadata.service,
            "environment": metadata.environment,
            "document_type": str(metadata.document_type.value),
            "version": metadata.version,
            "trust_level": str(metadata.trust_level.value),
            "source_file": source_file,
            "chunk_index": chunk_index,
        }

    def ingest_all(self) -> int:
        """Ingest all Markdown documents into ChromaDB.

        Walks the knowledge directory for .md files, splits them into
        overlapping chunks, and adds them to the ChromaDB collection.
        Uses content hashing for idempotency — chunks that already exist
        (by ID) are skipped.

        Returns:
            Total number of new document chunks ingested.
        """
        collection = self._get_or_create_collection()
        md_files = self._discover_markdown_files()

        if not md_files:
            logger.warning("No Markdown files found for ingestion.")
            return 0

        total_ingested = 0

        for file_path in md_files:
            try:
                ingested = self._ingest_file(collection, file_path)
                total_ingested += ingested
            except Exception:
                logger.exception("Failed to ingest file: %s", file_path)

        logger.info(
            "Ingestion complete: %d new chunks from %d files",
            total_ingested,
            len(md_files),
        )
        return total_ingested

    def _ingest_file(self, collection: chromadb.Collection, file_path: Path) -> int:
        """Ingest a single Markdown file into the collection.

        Args:
            collection: The target ChromaDB collection.
            file_path: Path to the Markdown file.

        Returns:
            Number of new chunks ingested from this file.
        """
        content = file_path.read_text(encoding="utf-8")
        if not content.strip():
            logger.debug("Skipping empty file: %s", file_path)
            return 0

        # Extract metadata from directory structure
        metadata = extract_metadata_from_path(file_path)

        # Split into chunks
        chunks = self._splitter.split_text(content)
        logger.debug(
            "Split %s into %d chunks", file_path.name, len(chunks),
        )

        # Prepare batch for ChromaDB
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        # Get existing IDs to skip duplicates
        existing_ids = set()
        try:
            # Generate all candidate IDs first
            candidate_ids = [
                self._content_hash(chunk) for chunk in chunks
            ]
            # Check which already exist in the collection
            if candidate_ids:
                existing = collection.get(ids=candidate_ids, include=[])
                existing_ids = set(existing["ids"])
        except Exception:
            # If the collection is empty or IDs don't exist, that's fine
            logger.debug("No existing documents found for deduplication check.")

        source_str = str(file_path)

        for chunk_index, chunk in enumerate(chunks):
            doc_id = self._content_hash(chunk)

            # Skip if already ingested (idempotency)
            if doc_id in existing_ids:
                logger.debug(
                    "Skipping duplicate chunk %d from %s (id=%s)",
                    chunk_index,
                    file_path.name,
                    doc_id[:12],
                )
                continue

            ids.append(doc_id)
            documents.append(chunk)
            metadatas.append(
                self._metadata_to_chroma_dict(metadata, source_str, chunk_index)
            )

        if not ids:
            logger.debug("All chunks from %s already ingested.", file_path.name)
            return 0

        # Batch add to ChromaDB
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(
            "Ingested %d new chunks from %s (metadata: service=%s, type=%s)",
            len(ids),
            file_path.name,
            metadata.service,
            metadata.document_type.value,
        )
        return len(ids)
