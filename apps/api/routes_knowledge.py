"""Knowledge base explorer routes.

Surfaces the organizational knowledge documents (architecture, runbooks,
historical incidents) that the RAG layer draws on. Metadata — service,
document type, trust level — is inferred from the directory structure via the
same helper the ingestion pipeline uses, so the explorer stays consistent
with what the retriever sees.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.identity.deps import CurrentUser, require_viewer
from core.config import get_settings
from core.knowledge.metadata import extract_metadata_from_path

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])


def _relative_id(path, root) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


@router.get("")
async def list_knowledge(_: CurrentUser = Depends(require_viewer)):
    """List all knowledge documents with inferred metadata."""
    settings = get_settings()
    knowledge_dir = settings.knowledge_dir

    documents = []
    if knowledge_dir.exists():
        for path in sorted(knowledge_dir.rglob("*.md")):
            meta = extract_metadata_from_path(path)
            documents.append(
                {
                    "id": _relative_id(path, knowledge_dir),
                    "name": path.stem,
                    "document_type": meta.document_type.value,
                    "service": meta.service,
                    "environment": meta.environment,
                    "version": meta.version,
                    "trust_level": meta.trust_level.value,
                }
            )

    return {"documents": documents, "count": len(documents)}


@router.get("/{doc_id:path}")
async def get_knowledge_document(doc_id: str, _: CurrentUser = Depends(require_viewer)):
    """Return the full content and metadata of a single knowledge document."""
    settings = get_settings()
    knowledge_dir = settings.knowledge_dir
    target = (knowledge_dir / doc_id).resolve()

    # Path-traversal guard: keep the resolved path inside the knowledge dir.
    if not str(target).startswith(str(knowledge_dir.resolve())) or not target.exists():
        raise HTTPException(status_code=404, detail="Document not found.")

    meta = extract_metadata_from_path(target)
    return {
        "id": doc_id,
        "name": target.stem,
        "document_type": meta.document_type.value,
        "service": meta.service,
        "environment": meta.environment,
        "version": meta.version,
        "trust_level": meta.trust_level.value,
        "content": target.read_text(encoding="utf-8"),
    }
