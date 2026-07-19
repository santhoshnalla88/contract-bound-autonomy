"""FastAPI application entry point (production-grade wiring)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from apps.api import (
    routes_approvals,
    routes_auth,
    routes_contracts,
    routes_health,
    routes_incidents,
    routes_knowledge,
)
from core.identity.service import bootstrap_admin
from core.config import get_settings
from apps.worker.context import build_context

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Built React control plane (apps/ui/dist). Run `npm run build` in apps/ui to populate.
STATIC_DIR = Path(__file__).resolve().parents[1] / "ui" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build backends, bootstrap admin, wire the job queue; tear down cleanly."""
    settings = get_settings()

    ctx = await build_context(settings)
    app.state.ctx = ctx
    app.state.db = ctx.db
    app.state.graph = ctx.graph

    await bootstrap_admin(ctx.db, settings)

    # Durable job queue (production) — API enqueues, worker executes.
    app.state.arq = None
    if settings.use_redis:
        from arq import create_pool
        from arq.connections import RedisSettings

        app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        logger.info("Arq job queue connected.")

    logger.info("Startup complete (env=%s, execution=%s).", settings.app_env, settings.execution_backend)
    try:
        yield
    finally:
        if app.state.arq is not None:
            await app.state.arq.aclose()
        await ctx.aclose()
        logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Contract-Bound Autonomous Remediation",
        description="AI-powered incident remediation with hard operational boundaries.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Rate limiting (default limits applied to all routes).
    limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)

    # CORS — explicit origins in production; '*' only permitted in dev/test.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials="*" not in settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routers
    app.include_router(routes_health.router)
    app.include_router(routes_auth.router)
    app.include_router(routes_incidents.router)
    app.include_router(routes_approvals.router)
    app.include_router(routes_contracts.router)
    app.include_router(routes_knowledge.router)

    # Prometheus metrics at /metrics
    if settings.enable_metrics:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    # Serve the built React control plane with SPA deep-link fallback.
    # Registered last so API routes (more specific) always match first.
    if STATIC_DIR.exists():
        from fastapi.responses import FileResponse

        assets_dir = STATIC_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            candidate = STATIC_DIR / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")

    return app


def _rate_limit_handler(request, exc):  # pragma: no cover - trivial
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


app = create_app()
