"""Transactional primitives for the durable publishing queue.

This module claims database jobs only. It deliberately does not send Telegram
messages; a separately enabled publisher must verify target permissions first.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.automation_models import PublishJob, PublishJobStatus


async def claim_next_publish_job(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> PublishJob | None:
    """Atomically claim the oldest due queued job in the caller's transaction.

    The conditional UPDATE is the concurrency boundary: if two workers select
    the same candidate, only the first UPDATE can change its queued status.
    The caller must commit promptly to make the claim visible to other workers.
    A processing job is never silently re-queued because a worker may have
    completed the external Telegram send immediately before crashing.
    """
    claimed_at = now or datetime.now(UTC)
    candidate_id = (
        select(PublishJob.id)
        .where(
            PublishJob.status == PublishJobStatus.QUEUED.value,
            PublishJob.run_at <= claimed_at,
            PublishJob.attempts < PublishJob.max_attempts,
        )
        .order_by(PublishJob.run_at.asc(), PublishJob.created_at.asc())
        .limit(1)
        .scalar_subquery()
    )
    statement = (
        update(PublishJob)
        .where(
            PublishJob.id == candidate_id,
            PublishJob.status == PublishJobStatus.QUEUED.value,
            PublishJob.attempts < PublishJob.max_attempts,
        )
        .values(
            status=PublishJobStatus.PROCESSING.value,
            attempts=PublishJob.attempts + 1,
            locked_at=claimed_at,
            updated_at=claimed_at,
        )
        .returning(PublishJob.id)
    )
    result = await session.execute(statement)
    job_id = result.scalar_one_or_none()
    if job_id is None:
        return None
    return await session.get(PublishJob, job_id)
