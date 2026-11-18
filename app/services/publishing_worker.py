"""Supervised durable publishing worker with conservative failure handling.

The worker accepts an injected publisher. It never retries an ambiguous send:
if the transport fails without proving Telegram rejected the request, the job
moves to UNCERTAIN and requires an explicit operator decision.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from app.database.automation_models import (
    AuditEvent,
    PublishAttempt,
    PublishAttemptOutcome,
    PublishJob,
    PublishJobStatus,
)
from app.services.publishing_queue import claim_next_publish_job


@dataclass(frozen=True, slots=True)
class PublishPayload:
    job_id: str
    destination_chat_id: int
    content_id: str
    title: str | None
    text: str


class Publisher(Protocol):
    async def publish(self, payload: PublishPayload) -> int:
        """Send a post and return Telegram's resulting message ID."""


class RetryablePublishError(Exception):
    """The transport has confirmed that Telegram did not accept the post."""


class PermanentPublishError(Exception):
    """The request is invalid or cannot succeed without operator changes."""


class UncertainPublishError(Exception):
    """The send may have succeeded; automatic retry could create a duplicate."""


class PublishingWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: Publisher,
        *,
        poll_interval_seconds: float = 2.0,
        retry_base_seconds: int = 15,
        retry_max_seconds: int = 900,
    ) -> None:
        if poll_interval_seconds <= 0 or retry_base_seconds <= 0 or retry_max_seconds <= 0:
            raise ValueError("Worker intervals and retry limits must be positive.")
        self.session_factory = session_factory
        self.publisher = publisher
        self.poll_interval_seconds = poll_interval_seconds
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds

    async def run_once(self) -> bool:
        """Claim and process one due job. Returns False when the queue is empty."""
        async with self.session_factory() as session:
            job = await claim_next_publish_job(session)
            if job is None:
                await session.rollback()
                return False

            loaded = await session.scalar(
                select(PublishJob)
                .options(
                    joinedload(PublishJob.content),
                    joinedload(PublishJob.target_channel),
                )
                .where(PublishJob.id == job.id)
            )
            if loaded is None:
                await session.rollback()
                return False

            attempt = PublishAttempt(
                publish_job_id=loaded.id,
                attempt_number=loaded.attempts,
                outcome=PublishAttemptOutcome.PROCESSING.value,
            )
            session.add(attempt)
            payload = PublishPayload(
                job_id=loaded.id,
                destination_chat_id=loaded.target_channel.telegram_chat_id,
                content_id=loaded.content.id,
                title=loaded.content.title,
                text=loaded.content.caption or loaded.content.body_text or loaded.content.title or "",
            )
            await session.flush()
            attempt_id = attempt.id
            job_id = loaded.id
            attempt_number = loaded.attempts
            max_attempts = loaded.max_attempts
            permission_verified = loaded.target_channel.posting_permission_status == "verified"
            await session.commit()

        if not permission_verified:
            await self._record_permanent_failure(
                job_id, attempt_id,
                PermanentPublishError("Target channel posting permission is not verified."),
            )
            return True

        try:
            message_id = await self.publisher.publish(payload)
        except RetryablePublishError as exc:
            await self._record_retryable_failure(
                job_id, attempt_id, attempt_number, max_attempts, exc
            )
        except PermanentPublishError as exc:
            await self._record_permanent_failure(job_id, attempt_id, exc)
        except (UncertainPublishError, asyncio.TimeoutError, OSError) as exc:
            await self._record_uncertain(job_id, attempt_id, exc)
        except asyncio.CancelledError:
            # A cancelled task may have been interrupted during the external send.
            # Leave a durable processing lock for explicit stale-job recovery.
            raise
        except Exception as exc:
            # Unknown exceptions are conservative: do not risk an automatic duplicate.
            await self._record_uncertain(job_id, attempt_id, exc)
        else:
            await self._record_success(job_id, attempt_id, message_id)
        return True

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        """Poll continuously until stop_event is set."""
        while not stop_event.is_set():
            processed = await self.run_once()
            if processed:
                continue
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=self.poll_interval_seconds
                )
            except asyncio.TimeoutError:
                pass

    async def _record_success(self, job_id: str, attempt_id: str, message_id: int) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            job = await session.get(PublishJob, job_id)
            attempt = await session.get(PublishAttempt, attempt_id)
            if job is None or attempt is None:
                raise RuntimeError("Publish job or attempt disappeared before result persistence.")
            job.status = PublishJobStatus.PUBLISHED.value
            job.telegram_message_id = message_id
            job.locked_at = None
            job.last_error = None
            job.updated_at = now
            attempt.outcome = PublishAttemptOutcome.PUBLISHED.value
            attempt.telegram_message_id = message_id
            attempt.finished_at = now
            await session.commit()

    async def _record_retryable_failure(
        self, job_id: str, attempt_id: str, attempt_number: int,
        max_attempts: int, error: Exception,
    ) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            job = await session.get(PublishJob, job_id)
            attempt = await session.get(PublishAttempt, attempt_id)
            if job is None or attempt is None:
                raise RuntimeError("Publish job or attempt disappeared before failure persistence.")
            attempt.outcome = PublishAttemptOutcome.RETRYABLE_FAILURE.value
            attempt.error_code = type(error).__name__[:100]
            attempt.error_message = str(error)[:4000]
            attempt.finished_at = now
            job.last_error = str(error)[:4000]
            job.locked_at = None
            job.updated_at = now
            if attempt_number < max_attempts:
                delay = min(self.retry_base_seconds * (2 ** (attempt_number - 1)), self.retry_max_seconds)
                job.status = PublishJobStatus.QUEUED.value
                job.run_at = now + timedelta(seconds=delay)
            else:
                job.status = PublishJobStatus.FAILED.value
            await session.commit()

    async def _record_permanent_failure(
        self, job_id: str, attempt_id: str, error: Exception
    ) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            job = await session.get(PublishJob, job_id)
            attempt = await session.get(PublishAttempt, attempt_id)
            if job is None or attempt is None:
                raise RuntimeError("Publish job or attempt disappeared before failure persistence.")
            job.status = PublishJobStatus.FAILED.value
            job.last_error = str(error)[:4000]
            job.locked_at = None
            job.updated_at = now
            attempt.outcome = PublishAttemptOutcome.PERMANENT_FAILURE.value
            attempt.error_code = type(error).__name__[:100]
            attempt.error_message = str(error)[:4000]
            attempt.finished_at = now
            await session.commit()

    async def _record_uncertain(
        self, job_id: str, attempt_id: str, error: Exception
    ) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            job = await session.get(PublishJob, job_id)
            attempt = await session.get(PublishAttempt, attempt_id)
            if job is None or attempt is None:
                raise RuntimeError("Publish job or attempt disappeared before uncertainty persistence.")
            job.status = PublishJobStatus.UNCERTAIN.value
            job.last_error = str(error)[:4000]
            job.locked_at = None
            job.updated_at = now
            attempt.outcome = PublishAttemptOutcome.UNCERTAIN.value
            attempt.error_code = type(error).__name__[:100]
            attempt.error_message = str(error)[:4000]
            attempt.finished_at = now
            await session.commit()


async def retry_uncertain_publish_job(
    session: AsyncSession,
    job_id: str,
    *,
    operator_admin_id: int,
) -> PublishJob:
    """Explicitly requeue an uncertain job after an operator checks Telegram."""
    job = await session.get(PublishJob, job_id)
    if job is None:
        raise LookupError(f"Publish job {job_id} was not found.")
    if job.status != PublishJobStatus.UNCERTAIN.value:
        raise ValueError("Only uncertain publish jobs can be manually recovered.")
    now = datetime.now(UTC)
    previous_error = job.last_error
    job.status = PublishJobStatus.QUEUED.value
    job.run_at = now
    job.locked_at = None
    job.last_error = None
    job.updated_at = now
    session.add(AuditEvent(
        actor_admin_id=operator_admin_id,
        action="publish_job.manual_retry",
        entity_type="publish_job",
        entity_id=job.id,
        details_json=json.dumps({"previous_error": previous_error}),
    ))
    await session.flush()
    return job
