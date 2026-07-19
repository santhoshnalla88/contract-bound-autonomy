"""Async database manager built on SQLAlchemy — Postgres in prod, SQLite locally.

Provides typed helpers for audit events, incidents, pending approvals, and
users. The public method surface is backend-agnostic; swapping ``DATABASE_URL``
between Postgres and SQLite requires no code changes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from core.models import AuditEvent
from core.persistence.orm import (
    AuditEventORM,
    Base,
    IncidentORM,
    PendingApprovalORM,
    UserORM,
)

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Async persistence manager backed by SQLAlchemy."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._engine: AsyncEngine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            future=True,
        )
        self._session = async_sessionmaker(self._engine, expire_on_commit=False)
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables if absent (idempotent). Prod deploys use Alembic; this
        is the bootstrap/local path and is safe to run alongside migrations."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._initialized = True
        logger.info("Database initialised (%s)", self._engine.url.render_as_string(hide_password=True))

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def ping(self) -> bool:
        """Lightweight connectivity check for readiness probes."""
        try:
            async with self._session() as s:
                await s.execute(select(1))
            return True
        except Exception:
            logger.exception("Database ping failed")
            return False

    # ------------------------------------------------------------------
    # Audit Events
    # ------------------------------------------------------------------
    async def insert_audit_event(self, event: AuditEvent) -> None:
        async with self._session() as s:
            s.add(
                AuditEventORM(
                    incident_id=event.incident_id,
                    timestamp=event.timestamp,
                    event_type=event.event_type,
                    contract_id=event.contract_id,
                    contract_version=event.contract_version,
                    actor=event.actor,
                    details=event.details or {},
                    outcome=event.outcome,
                )
            )
            await s.commit()

    async def get_audit_trail(self, incident_id: str) -> list[dict[str, Any]]:
        async with self._session() as s:
            rows = (
                await s.execute(
                    select(AuditEventORM)
                    .where(AuditEventORM.incident_id == incident_id)
                    .order_by(AuditEventORM.timestamp.asc(), AuditEventORM.id.asc())
                )
            ).scalars().all()

        return [
            {
                "id": r.id,
                "incident_id": r.incident_id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "event_type": r.event_type,
                "contract_id": r.contract_id,
                "contract_version": r.contract_version,
                "actor": r.actor,
                "details": r.details or {},
                "outcome": r.outcome,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------
    async def upsert_incident(
        self,
        incident_id: str,
        data: dict[str, Any],
        status: str,
        submitted_by: str | None = None,
    ) -> None:
        async with self._session() as s:
            existing = await s.get(IncidentORM, incident_id)
            if existing:
                existing.data = data or existing.data
                existing.status = status
                existing.updated_at = datetime.now(timezone.utc)
                if submitted_by:
                    existing.submitted_by = submitted_by
            else:
                s.add(
                    IncidentORM(
                        incident_id=incident_id,
                        data=data or {},
                        status=status,
                        submitted_by=submitted_by,
                    )
                )
            await s.commit()

    async def list_incidents(self) -> list[dict[str, Any]]:
        async with self._session() as s:
            rows = (
                await s.execute(select(IncidentORM).order_by(IncidentORM.updated_at.desc()))
            ).scalars().all()

        return [
            {
                "incident_id": r.incident_id,
                "data": r.data or {},
                "status": r.status,
                "submitted_by": r.submitted_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Pending Approvals
    # ------------------------------------------------------------------
    async def create_pending_approval(
        self, incident_id: str, thread_id: str, plan: dict[str, Any], context: dict[str, Any]
    ) -> None:
        async with self._session() as s:
            s.add(
                PendingApprovalORM(
                    incident_id=incident_id,
                    thread_id=thread_id,
                    plan=plan or {},
                    context=context or {},
                    status="pending",
                )
            )
            await s.commit()

    async def resolve_approval(
        self, incident_id: str, decision: str, resolved_by: str | None = None, reasoning: str = ""
    ) -> None:
        async with self._session() as s:
            await s.execute(
                update(PendingApprovalORM)
                .where(
                    PendingApprovalORM.incident_id == incident_id,
                    PendingApprovalORM.status == "pending",
                )
                .values(status=decision, resolved_by=resolved_by, reasoning=reasoning)
            )
            await s.commit()

    async def get_pending_approvals(self) -> list[dict[str, Any]]:
        async with self._session() as s:
            rows = (
                await s.execute(
                    select(PendingApprovalORM)
                    .where(PendingApprovalORM.status == "pending")
                    .order_by(PendingApprovalORM.created_at.asc())
                )
            ).scalars().all()

        return [
            {
                "id": r.id,
                "incident_id": r.incident_id,
                "thread_id": r.thread_id,
                "plan": r.plan or {},
                "context": r.context or {},
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        async with self._session() as s:
            r = (
                await s.execute(select(UserORM).where(UserORM.email == email))
            ).scalar_one_or_none()
        if not r:
            return None
        return {
            "id": r.id,
            "email": r.email,
            "hashed_password": r.hashed_password,
            "role": r.role,
            "is_active": r.is_active,
        }

    async def create_user(
        self, user_id: str, email: str, hashed_password: str, role: str
    ) -> None:
        async with self._session() as s:
            s.add(
                UserORM(
                    id=user_id,
                    email=email,
                    hashed_password=hashed_password,
                    role=role,
                )
            )
            await s.commit()

    async def count_users(self) -> int:
        async with self._session() as s:
            return int((await s.execute(select(func.count(UserORM.id)))).scalar_one())

    async def list_users(self) -> list[dict[str, Any]]:
        async with self._session() as s:
            rows = (await s.execute(select(UserORM).order_by(UserORM.created_at.asc()))).scalars().all()
        return [
            {"id": r.id, "email": r.email, "role": r.role, "is_active": r.is_active}
            for r in rows
        ]

    async def delete_user(self, email: str) -> None:
        async with self._session() as s:
            await s.execute(delete(UserORM).where(UserORM.email == email))
            await s.commit()
