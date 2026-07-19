"""Document metadata models for the RAG knowledge retrieval pipeline.

Metadata is attached to every document during ingestion and carried through
retrieval so the planner agent can assess document provenance and trust level.
The extract_metadata_from_path helper infers metadata from the knowledge base
directory structure, avoiding the need for manual tagging.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from core.enums import DocumentType, TrustLevel


class DocumentMetadata(BaseModel):
    """Metadata for a knowledge base document.

    Attached during ingestion and stored alongside the document content
    in the ChromaDB collection. Used for filtered retrieval and trust
    level annotations in the planner context.
    """

    service: str = Field(
        default="unknown",
        description="Service this document pertains to",
    )
    environment: str = Field(
        default="production",
        description="Deployment environment context",
    )
    document_type: DocumentType = Field(
        default=DocumentType.RUNBOOK,
        description="Category of the document",
    )
    version: str = Field(
        default="1.0.0",
        description="Document version for change tracking",
    )
    trust_level: TrustLevel = Field(
        default=TrustLevel.TEAM_CONTRIBUTED,
        description="Trust classification — metadata only, does not override contracts",
    )


class RetrievedDocument(BaseModel):
    """A document retrieved from the knowledge base with relevance scoring.

    The retriever produces these by querying ChromaDB and mapping the
    raw results to structured models with provenance metadata.
    """

    content: str = Field(
        ...,
        description="The text content of the retrieved document chunk",
    )
    metadata: DocumentMetadata = Field(
        ...,
        description="Provenance and classification metadata",
    )
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance score (0.0 = irrelevant, 1.0 = exact match)",
    )


# ---------------------------------------------------------------------------
# Document type mapping — used by extract_metadata_from_path
# ---------------------------------------------------------------------------

_DIRECTORY_TO_DOC_TYPE: dict[str, DocumentType] = {
    "architecture": DocumentType.ARCHITECTURE,
    "runbooks": DocumentType.RUNBOOK,
    "incidents": DocumentType.INCIDENT,
    "contracts": DocumentType.CONTRACT,
}

_DIRECTORY_TO_TRUST_LEVEL: dict[str, TrustLevel] = {
    "architecture": TrustLevel.ORGANIZATION_APPROVED,
    "runbooks": TrustLevel.ORGANIZATION_APPROVED,
    "incidents": TrustLevel.TEAM_CONTRIBUTED,
    "contracts": TrustLevel.ORGANIZATION_APPROVED,
}


def extract_metadata_from_path(file_path: Path) -> DocumentMetadata:
    """Infer document metadata from the knowledge base directory structure.

    Convention:
        knowledge/<category>/<service>-<descriptor>.<ext>

    Examples:
        knowledge/runbooks/inventory-service-connection-pool-runbook.md
            → document_type=RUNBOOK, service=inventory-service

        knowledge/architecture/inventory-service-architecture.md
            → document_type=ARCHITECTURE, service=inventory-service

        knowledge/incidents/incident-2026-001.md
            → document_type=INCIDENT, service=unknown (no service prefix match)

    Args:
        file_path: Path to the document file, absolute or relative.

    Returns:
        DocumentMetadata with fields inferred from the path structure.
    """
    parts = file_path.parts

    # --- Determine document type from parent directory name ---
    document_type = DocumentType.RUNBOOK  # default
    trust_level = TrustLevel.TEAM_CONTRIBUTED  # default

    for part in parts:
        part_lower = part.lower()
        if part_lower in _DIRECTORY_TO_DOC_TYPE:
            document_type = _DIRECTORY_TO_DOC_TYPE[part_lower]
            trust_level = _DIRECTORY_TO_TRUST_LEVEL[part_lower]
            break

    # --- Extract service name from filename ---
    # Convention: filenames start with the service name
    # e.g., "inventory-service-connection-pool-runbook.md"
    # We look for known service-name patterns (word-service)
    filename = file_path.stem  # e.g., "inventory-service-connection-pool-runbook"
    service = _extract_service_from_filename(filename)

    return DocumentMetadata(
        service=service,
        environment="production",
        document_type=document_type,
        version="1.0.0",
        trust_level=trust_level,
    )


def _extract_service_from_filename(filename: str) -> str:
    """Extract the service name from a filename by convention.

    Looks for the pattern '<name>-service' at the start of the filename.
    Falls back to 'unknown' if no match is found.

    Args:
        filename: The file stem (no extension).

    Returns:
        The extracted service name or 'unknown'.
    """
    # Split on hyphens and look for the 'service' token
    tokens = filename.lower().split("-")

    for i, token in enumerate(tokens):
        if token == "service" and i > 0:
            # Return everything up to and including 'service'
            return "-".join(tokens[: i + 1])

    # Fallback: if the filename starts with 'incident-', try to infer
    # from incident content later; for now return unknown
    return "unknown"
