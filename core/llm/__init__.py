"""Provider-agnostic LLM access for agent roles."""

from core.llm.factory import get_chat_model, get_embeddings

__all__ = ["get_chat_model", "get_embeddings"]
