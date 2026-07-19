"""Provider-agnostic LLM + embeddings factory.

The platform's philosophy is "swappable behind interfaces" — the model provider
is no exception. Each **agent role** (planner, policy, summary) maps to a
provider + model via config, so you flip Claude ↔ Gemini ↔ OpenAI with one env
var and never touch agent code.

Deliberate allocation ("use both keys wisely"):
- **planner / policy** → Anthropic Claude — high-stakes structured reasoning and
  compliance judgement, where "follow the contract, don't improvise" matters.
- **summary** → Google Gemini — cheap post-incident narrative; non-critical, so a
  rate-limit degrades gracefully rather than blocking remediation.
- **embeddings** → local ONNX (Chroma default) — high-volume, no API quota ceiling,
  and works offline; Gemini embeddings are available via config when preferred.

Every provider returns a LangChain chat model exposing the same
`.ainvoke()` / `.with_structured_output()` surface, so agents are provider-blind.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

from core.config import get_settings

logger = logging.getLogger(__name__)

# Newer Claude models removed sampling params — passing `temperature` returns a 400.
# (Opus 4.8/4.7, Sonnet 5, Fable 5/Mythos 5.) Steer these via prompting instead.
_ANTHROPIC_NO_SAMPLING = {
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos-5",
}


def _role_config(role: str) -> tuple[str, str]:
    """Return (provider, model) for an agent role from settings."""
    s = get_settings()
    mapping = {
        "planner": (s.planner_provider, s.planner_model),
        "policy": (s.policy_provider, s.policy_model),
        "summary": (s.summary_provider, s.summary_model),
    }
    if role not in mapping:
        raise ValueError(f"Unknown LLM role '{role}'. Known: {list(mapping)}")
    return mapping[role]


def get_chat_model(role: str, *, temperature: float | None = None, **kwargs: Any) -> BaseChatModel:
    """Return a LangChain chat model for the given agent role."""
    s = get_settings()
    provider, model = _role_config(role)
    temp = s.llm_temperature if temperature is None else temperature

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": kwargs.pop("max_tokens", 4096),
            "api_key": s.anthropic_api_key or None,
            "timeout": 60,
            **kwargs,
        }
        if model not in _ANTHROPIC_NO_SAMPLING:
            params["temperature"] = temp
        return ChatAnthropic(**params)
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temp,
            google_api_key=s.google_api_key or None,
            **kwargs,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, temperature=temp, api_key=s.openai_api_key or None, **kwargs)

    raise ValueError(f"Unsupported LLM provider '{provider}' for role '{role}'")


def get_embeddings() -> Any:
    """Return an embedding function for the vector DB (RAG).

    ``local`` (default) → Chroma's built-in ONNX MiniLM: no key, no quota, offline.
    Returning ``None`` tells Chroma to use its default embedding function.
    """
    s = get_settings()
    if s.embedding_provider == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        model = s.embedding_model if s.embedding_model.startswith("models/") else f"models/{s.embedding_model}"
        return GoogleGenerativeAIEmbeddings(model=model, google_api_key=s.google_api_key or None)
    if s.embedding_provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=s.embedding_model, api_key=s.openai_api_key or None)
    # local → Chroma default ONNX embedding function
    return None
