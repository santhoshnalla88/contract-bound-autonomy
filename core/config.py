"""Application configuration using Pydantic BaseSettings.

Backends are selected by environment so the same codebase runs three ways:

* **production** — Postgres (state + checkpointer), Redis (events + Arq queue),
  Kubernetes execution driver, JWT auth with a mandatory secret.
* **local / dev** — SQLite, in-memory event bus, inline task execution, mock
  Kubernetes driver. Boots with a single ``uvicorn`` command, no services.
* **test** — same lightweight backends, isolated temp resources.

Every secret is read from the environment only; nothing sensitive is hardcoded.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables / ``.env``."""

    # --- Environment ---
    app_env: Literal["production", "local", "test"] = "local"

    # --- Project Paths ---
    project_root: Path = Path(__file__).parent.parent
    knowledge_dir: Path = Path(__file__).parent.parent / "knowledge"
    chroma_db_dir: Path = Path(__file__).parent.parent / "data" / "chroma"
    sqlite_db_path: Path = Path(__file__).parent.parent / "data" / "audit.db"

    # --- LLM Configuration ---
    # Provider-agnostic: each agent role maps to a provider + model (see core/llm/factory.py).
    # "Use both keys wisely": Claude for reasoning (planner/policy), Gemini for cheap tasks (summary).
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    llm_model: str = "gpt-4o"  # legacy fallback
    llm_temperature: float = 0.1

    planner_provider: Literal["anthropic", "google", "openai"] = "anthropic"
    planner_model: str = "claude-opus-4-8"
    policy_provider: Literal["anthropic", "google", "openai"] = "anthropic"
    policy_model: str = "claude-haiku-4-5"
    summary_provider: Literal["anthropic", "google", "openai"] = "google"
    summary_model: str = "gemini-2.0-flash"

    # --- RAG Configuration ---
    chroma_collection_name: str = "knowledge_base"
    retrieval_top_k: int = 5
    chunk_size: int = 1000
    chunk_overlap: int = 200
    # Embeddings: "local" uses Chroma's built-in ONNX model (no key, no quota — reliable);
    # "google" uses Gemini embeddings (free-tier quota applies).
    embedding_provider: Literal["local", "google", "openai"] = "local"
    embedding_model: str = "text-embedding-004"
    ingest_on_startup: bool = True

    # --- Graph DB (Neo4j) ---
    graph_enabled: bool = False
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # --- Persistence ---
    # SQLAlchemy async URL. Postgres in prod, SQLite locally.
    #   postgresql+asyncpg://user:pass@host:5432/db   OR   sqlite+aiosqlite:///./data/app.db
    database_url: str = ""
    # Separate psycopg-style URL for the LangGraph Postgres checkpointer.
    #   postgresql://user:pass@host:5432/db
    checkpointer_url: str = ""

    # --- Redis / queue / events ---
    redis_url: str = ""  # redis://host:6379/0 ; empty → in-memory bus + inline tasks

    # --- LangSmith Configuration ---
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "contract-bound-autonomy"

    # --- Execution boundary ---
    execution_backend: Literal["mock", "kubernetes"] = "mock"
    k8s_namespace: str = "default"
    k8s_in_cluster: bool = False  # True when running inside a pod
    k8s_kubeconfig: str = ""      # optional explicit kubeconfig path

    # --- Auth ---
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    # Bootstrap admin (created on startup if no users exist).
    bootstrap_admin_email: str = "admin@local"
    bootstrap_admin_password: str = ""

    # --- Security / ops ---
    allowed_origins: str = "*"  # comma-separated; '*' only permitted in local/test
    rate_limit: str = "120/minute"
    enable_metrics: bool = True

    # --- Operational Defaults ---
    max_plan_retries: int = 3
    default_risk_threshold: str = "HIGH"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def use_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql", "postgres"))

    @property
    def use_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def effective_database_url(self) -> str:
        """SQLAlchemy async URL, defaulting to a local SQLite file."""
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{(self.project_root / 'data' / 'app.db').as_posix()}"

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        return origins or ["*"]

    @model_validator(mode="after")
    def _validate_production_invariants(self) -> "Settings":
        """Fail fast on unsafe production configuration."""
        if self.is_production:
            problems: list[str] = []
            if not self.jwt_secret:
                problems.append("JWT_SECRET must be set in production")
            elif len(self.jwt_secret) < 32:
                problems.append("JWT_SECRET must be at least 32 characters in production")
            if not self.use_postgres:
                problems.append("DATABASE_URL must point to Postgres in production")
            if not self.use_redis:
                problems.append("REDIS_URL must be set in production")
            if "*" in self.cors_origins:
                problems.append("ALLOWED_ORIGINS must be an explicit list in production")
            if self.bootstrap_admin_email and not self.bootstrap_admin_password:
                problems.append("BOOTSTRAP_ADMIN_PASSWORD must be set in production")
            if problems:
                raise ValueError(
                    "Invalid production configuration:\n  - " + "\n  - ".join(problems)
                )
        # In dev/test, generate an ephemeral JWT secret so tokens still work.
        if not self.jwt_secret:
            object.__setattr__(self, "jwt_secret", secrets.token_urlsafe(48))
        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
