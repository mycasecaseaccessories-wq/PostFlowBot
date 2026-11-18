"""Admin-facing inspection and explicit recovery for publishing jobs."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from app.database.automation_models import (
    AuditEvent,
    PublishAttempt,
    PublishDeliveryReceipt,
    PublishJob,
    PublishJobStatus,
)
from app.database.models import Admin
from app.services.publishing_worker import mark_stale_processing_job_uncertain


class PublishJobAdminService:
    """Read publish state and perform audited, deliberate operator recovery."""

    VALID_STATUSES = {item.value for item in PublishJobStatus}

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def _active_admin(self, session: AsyncSession, telegram_user_id: int) -> Admin:
        admin = await session.scalar(
            select(Admin).where(Admin.telegram_user_id == telegram_user_id)
        )
        if admin is None:
            admin = Admin(telegram_user_id=telegram_user_id, is_active=True)
            session.add(admin)
            await session.flush()
        if not admin.is_active:
            raise PermissionError("This admin account is inactive in the database.")
        return admin

    async def list_jobs(self, *, status: str | None = None, limit: int = 8) -> list[dict]:
        if status is not None and status not in self.VALID_STATUSES:
            raise ValueError("Invalid publish status.")
        limit = min(max(int(limit), 1), 20)
        async with self.session_factory() as session:
            statement = (
                select(PublishJob)
                .options(
                    joinedload(PublishJob.content),
                    joinedload(PublishJob.target_channel),
                )
                .order_by(PublishJob.created_at.desc())
                .limit(limit)
            )
            if status is not None:
                statement = statement.where(PublishJob.status == status)
            jobs = list((await session.scalars(statement)).unique().all())
            return [
                {
                    "id": job.id,
                    "status": job.status,
                    "content_title": job.content.title or job.content.caption or "Untitled",
                    "target_title": job.target_channel.title or str(job.target_channel.telegram_chat_id),
                    "target_chat_id": job.target_channel.telegram_chat_id,
                    "attempts": job.attempts,
                    "max_attempts": job.max_attempts,
                    "run_at": job.run_at,
                    "last_error": job.last_error,
                }
                for job in jobs
            ]

    async def get_job(self, job_id: str) -> dict | None:
        async with self.session_factory() as session:
            job = await session.scalar(
                select(PublishJob)
                .options(
                    joinedload(PublishJob.content),
                    joinedload(PublishJob.target_channel),
                )
                .where(PublishJob.id == job_id)
            )
            if job is None:
                return None
            attempts = list((await session.scalars(
                select(PublishAttempt)
                .where(PublishAttempt.publish_job_id == job.id)
                .order_by(PublishAttempt.attempt_number.asc())
            )).all())
            receipts = list((await session.scalars(
                select(PublishDeliveryReceipt)
                .where(PublishDeliveryReceipt.publish_job_id == job.id)
                .order_by(PublishDeliveryReceipt.created_at.asc(), PublishDeliveryReceipt.message_ordinal.asc())
            )).all())
            return {
                "id": job.id,
                "status": job.status,
                "content_title": job.content.title or job.content.caption or "Untitled",
                "target_title": job.target_channel.title or str(job.target_channel.telegram_chat_id),
                "target_chat_id": job.target_channel.telegram_chat_id,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "run_at": job.run_at,
                "last_error": job.last_error,
                "telegram_message_id": job.telegram_message_id,
                "attempt_history": [
                    {
                        "number": attempt.attempt_number,
                        "outcome": attempt.outcome,
                        "error": attempt.error_message,
                        "message_id": attempt.telegram_message_id,
                    }
                    for attempt in attempts
                ],
                "receipts": [
                    {
                        "message_id": receipt.telegram_message_id,
                        "ordinal": receipt.message_ordinal,
                    }
                    for receipt in receipts
                ],
            }

    async def retry_job(self, job_id: str, *, operator_telegram_user_id: int) -> PublishJob:
        """Requeue a failed/uncertain job only after explicit operator confirmation."""
        async with self.session_factory() as session:
            admin = await self._active_admin(session, operator_telegram_user_id)
            job = await session.get(PublishJob, job_id)
            if job is None:
                raise LookupError("Publish job was not found.")
            if job.status not in {
                PublishJobStatus.UNCERTAIN.value,
                PublishJobStatus.FAILED.value,
            }:
                raise ValueError("Only failed or uncertain jobs can be manually retried.")
            if job.attempts >= job.max_attempts:
                raise ValueError("Retry limit is exhausted; automatic retry is not allowed.")
            previous_status = job.status
            previous_error = job.last_error
            now = datetime.now(UTC)
            job.status = PublishJobStatus.QUEUED.value
            job.run_at = now
            job.locked_at = None
            job.last_error = None
            job.updated_at = now
            session.add(AuditEvent(
                actor_admin_id=admin.id,
                action="publish_job.manual_retry",
                entity_type="publish_job",
                entity_id=job.id,
                details_json=json.dumps({
                    "previous_status": previous_status,
                    "previous_error": previous_error,
                    "operator_confirmed_no_existing_delivery": True,
                }),
            ))
            await session.commit()
            return job

    async def recover_stale_job(
        self,
        job_id: str,
        *,
        operator_telegram_user_id: int,
        stale_after: timedelta = timedelta(minutes=10),
    ) -> PublishJob:
        """Move a stale processing lock to UNCERTAIN; never resend automatically."""
        async with self.session_factory() as session:
            admin = await self._active_admin(session, operator_telegram_user_id)
            job = await mark_stale_processing_job_uncertain(
                session,
                job_id,
                operator_admin_id=admin.id,
                stale_after=stale_after,
            )
            await session.commit()
            return job
