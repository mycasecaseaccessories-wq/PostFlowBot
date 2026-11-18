"""Persist incoming source messages and fan them out to active routes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.automation_models import PublishJob, PublishJobStatus
from app.database.cms_models import Content, ContentOrigin, ContentStatus, ContentType
from app.database.models import RepostRule, SourceChannel, TargetChannel


@dataclass(frozen=True, slots=True)
class IntakeResult:
    accepted: bool
    duplicate: bool = False
    content_id: str | None = None
    queued_jobs: int = 0
    reason: str | None = None


class MessageIntakeService:
    """Idempotently import a source message and create one queue job per route."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def ingest(self, *, source_chat_id: int, message_id: int,
                     text: str | None, content_type: str = ContentType.TEXT.value,
                     grouped_id: int | None = None) -> IntakeResult:
        body = (text or "").strip()
        if not body:
            return IntakeResult(False, reason="empty_or_media_only")
        async with self.session_factory() as session:
            source = await session.scalar(select(SourceChannel).where(
                SourceChannel.telegram_chat_id == source_chat_id,
                SourceChannel.is_active.is_(True)))
            if source is None:
                return IntakeResult(False, reason="source_not_registered")
            existing = await session.scalar(select(Content).where(
                Content.source_channel_id == source.id,
                Content.source_message_id == message_id))
            if existing is not None:
                return IntakeResult(False, duplicate=True, content_id=existing.id,
                                    reason="already_imported")
            content = Content(
                title=body[:255], caption=body, body_text=body,
                content_type=content_type,
                origin=ContentOrigin.CHANNEL_IMPORT.value,
                source_channel_id=source.id, source_message_id=message_id,
                status=ContentStatus.READY.value,
            )
            session.add(content)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                return IntakeResult(False, duplicate=True, reason="duplicate_source_message")

            routes = list((await session.scalars(
                select(RepostRule).join(TargetChannel,
                    TargetChannel.id == RepostRule.target_channel_id).where(
                    RepostRule.source_channel_id == source.id,
                    RepostRule.is_active.is_(True),
                    TargetChannel.is_active.is_(True),
                    TargetChannel.posting_permission_status == "verified")
            )).all())
            now = datetime.now(UTC)
            queued = 0
            for route in routes:
                key = f"source:{source.id}:message:{message_id}:target:{route.target_channel_id}"
                session.add(PublishJob(
                    content_id=content.id,
                    target_channel_id=route.target_channel_id,
                    idempotency_key=key,
                    status=PublishJobStatus.QUEUED.value,
                    run_at=now + timedelta(seconds=max(0, int(route.delay_seconds or 0))),
                ))
                queued += 1
            await session.commit()
            return IntakeResult(True, content_id=content.id, queued_jobs=queued)

    async def update_source_message(self, *, source_chat_id: int,
                                    message_id: int, text: str | None) -> bool:
        """Synchronize an edited source caption/text without creating new jobs."""
        body = (text or "").strip()
        async with self.session_factory() as session:
            source = await session.scalar(select(SourceChannel).where(
                SourceChannel.telegram_chat_id == source_chat_id))
            if source is None:
                return False
            content = await session.scalar(select(Content).where(
                Content.source_channel_id == source.id,
                Content.source_message_id == message_id))
            if content is None or content.is_archived:
                return False
            content.title = body[:255] or None
            content.caption = body or None
            content.body_text = body or None
            content.updated_at = datetime.now(UTC)
            await session.commit()
            return True

    async def delete_source_message(self, *, source_chat_id: int,
                                    message_id: int) -> bool:
        """Archive deleted source content and cancel jobs not yet claimed."""
        async with self.session_factory() as session:
            source = await session.scalar(select(SourceChannel).where(
                SourceChannel.telegram_chat_id == source_chat_id))
            if source is None:
                return False
            content = await session.scalar(select(Content).where(
                Content.source_channel_id == source.id,
                Content.source_message_id == message_id))
            if content is None:
                return False
            now = datetime.now(UTC)
            content.is_active = False
            content.is_archived = True
            content.archived_at = now
            content.deleted_at = now
            content.status = ContentStatus.ARCHIVED.value
            jobs = list((await session.scalars(select(PublishJob).where(
                PublishJob.content_id == content.id,
                PublishJob.status == PublishJobStatus.QUEUED.value,
            ))).all())
            for job in jobs:
                job.status = PublishJobStatus.CANCELLED.value
                job.last_error = "Source message was deleted before publication."
                job.updated_at = now
            await session.commit()
            return True
