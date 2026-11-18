"""Persist Telegram text/media intake and fan it out to active routes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.automation_models import PublishJob, PublishJobStatus
from app.database.cms_models import (
    Content, ContentMedia, ContentOrigin, ContentStatus, ContentType, Media,
)
from app.database.models import RepostRule, SourceChannel, TargetChannel
from app.services.content_transform import transform_text


@dataclass(frozen=True, slots=True)
class MediaDescriptor:
    telegram_file_id: str
    telegram_file_unique_id: str | None
    media_type: str
    original_file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None


@dataclass(frozen=True, slots=True)
class PublishPayload:
    content_id: str
    content_type: str
    text: str
    media: tuple[MediaDescriptor, ...]


@dataclass(frozen=True, slots=True)
class IntakeResult:
    accepted: bool
    duplicate: bool = False
    content_id: str | None = None
    queued_jobs: int = 0
    reason: str | None = None


class MessageIntakeService:
    """Idempotently import source messages, including grouped Telegram albums."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def ingest(
        self, *, source_chat_id: int, message_id: int, text: str | None,
        content_type: str = ContentType.TEXT.value, grouped_id: int | None = None,
        media_items: list[MediaDescriptor] | None = None,
    ) -> IntakeResult:
        body = (text or "").strip()
        items = media_items or []
        if not body and not items:
            return IntakeResult(False, reason="empty_or_media_only")
        async with self.session_factory() as session:
            source = await session.scalar(select(SourceChannel).where(
                SourceChannel.telegram_chat_id == source_chat_id,
                SourceChannel.is_active.is_(True)))
            if source is None:
                return IntakeResult(False, reason="source_not_registered")
            source_id = source.id
            album_key = str(grouped_id) if grouped_id is not None else None
            content = None
            if album_key is not None:
                content = await session.scalar(
                    select(Content).join(ContentMedia).where(
                        Content.source_channel_id == source_id,
                        ContentMedia.album_group_key == album_key,
                        Content.is_archived.is_(False),
                    ).limit(1)
                )
            if content is None:
                content = await session.scalar(select(Content).where(
                    Content.source_channel_id == source_id,
                    Content.source_message_id == message_id))
            created = content is None
            if created:
                resolved_type = ContentType.ALBUM.value if grouped_id is not None else content_type
                content = Content(
                    title=body[:255] or None, caption=body or None, body_text=body or None,
                    content_type=resolved_type,
                    origin=ContentOrigin.CHANNEL_IMPORT.value,
                    source_channel_id=source_id, source_message_id=message_id,
                    status=ContentStatus.READY.value,
                )
                session.add(content)
                try:
                    await session.flush()
                except IntegrityError:
                    await session.rollback()
                    duplicate_id = await session.scalar(select(Content.id).where(
                        Content.source_channel_id == source_id,
                        Content.source_message_id == message_id,
                    ))
                    if duplicate_id is not None:
                        return IntakeResult(False, duplicate=True, content_id=duplicate_id,
                                            reason="duplicate_source_message")
                    raise
            elif body and not content.caption:
                # Telegram albums commonly put the caption on only one item.
                content.caption = body
                content.body_text = body
                content.title = body[:255]

            attached = 0
            for item in items:
                media = None
                if item.telegram_file_unique_id:
                    media = await session.scalar(select(Media).where(
                        Media.telegram_file_unique_id == item.telegram_file_unique_id))
                if media is None:
                    media = await session.scalar(select(Media).where(
                        Media.telegram_file_id == item.telegram_file_id))
                if media is None:
                    media = Media(
                        telegram_file_id=item.telegram_file_id,
                        telegram_file_unique_id=item.telegram_file_unique_id,
                        media_type=item.media_type,
                        original_file_name=item.original_file_name,
                        mime_type=item.mime_type,
                        file_size=item.file_size,
                        width=item.width,
                        height=item.height,
                        duration=item.duration,
                    )
                    session.add(media)
                    await session.flush()
                link = await session.get(ContentMedia, (content.id, media.id))
                if link is None:
                    session.add(ContentMedia(
                        content_id=content.id, media_id=media.id,
                        display_order=int(await session.scalar(\n                            select(func.count(ContentMedia.media_id)).where(\n                                ContentMedia.content_id == content.id\n                            )\n                        ) or 0),
                        album_group_key=album_key,
                    ))
                    attached += 1

            if not created:
                await session.commit()
                return IntakeResult(attached > 0 or bool(body), content_id=content.id,
                                    reason="album_item_attached" if attached else "album_item_duplicate")

            routes = list((await session.scalars(
                select(RepostRule).join(TargetChannel,
                    TargetChannel.id == RepostRule.target_channel_id).where(
                    RepostRule.source_channel_id == source_id,
                    RepostRule.is_active.is_(True),
                    TargetChannel.is_active.is_(True),
                    TargetChannel.posting_permission_status == "verified")
            )).all())
            now = datetime.now(UTC)
            queued = 0
            for route in routes:
                key = f"source:{source_id}:message:{message_id}:target:{route.target_channel_id}"
                delay = max(0, int(route.delay_seconds or 0))
                # Allow Telegram's grouped messages to arrive before a queued album is eligible.
                if grouped_id is not None:
                    delay = max(delay, 3)
                session.add(PublishJob(
                    content_id=content.id, target_channel_id=route.target_channel_id,
                    idempotency_key=key, status=PublishJobStatus.QUEUED.value,
                    run_at=now + timedelta(seconds=delay),
                ))
                queued += 1
            await session.commit()
            return IntakeResult(True, content_id=content.id, queued_jobs=queued)


    async def build_publish_payload(
        self, *, content_id: str, target_channel_id: int,
    ) -> PublishPayload | None:
        """Build a route-specific, transformed payload without mutating source content.

        The future publisher consumes this method so each target receives its own
        text and ordered media list while the canonical CMS content stays intact.
        """
        async with self.session_factory() as session:
            row = (await session.execute(
                select(Content, RepostRule)
                .join(RepostRule, RepostRule.source_channel_id == Content.source_channel_id)
                .where(
                    Content.id == content_id,
                    Content.is_archived.is_(False),
                    RepostRule.target_channel_id == target_channel_id,
                    RepostRule.is_active.is_(True),
                )
            )).one_or_none()
            if row is None:
                return None
            content, route = row
            transformed = transform_text(
                content.caption or content.body_text,
                remove_usernames=route.remove_usernames,
                remove_links=route.remove_links,
                remove_keywords=route.remove_keywords,
            )
            media_rows = list((await session.scalars(
                select(Media)
                .join(ContentMedia, ContentMedia.media_id == Media.id)
                .where(ContentMedia.content_id == content.id, Media.is_active.is_(True))
                .order_by(ContentMedia.display_order.asc())
            )).all())
            media = tuple(MediaDescriptor(
                telegram_file_id=item.telegram_file_id,
                telegram_file_unique_id=item.telegram_file_unique_id,
                media_type=item.media_type,
                original_file_name=item.original_file_name,
                mime_type=item.mime_type,
                file_size=item.file_size,
                width=item.width,
                height=item.height,
                duration=item.duration,
            ) for item in media_rows)
            return PublishPayload(
                content_id=content.id,
                content_type=content.content_type,
                text=transformed,
                media=media,
            )

    async def update_source_message(self, *, source_chat_id: int,
                                    message_id: int, text: str | None) -> bool:
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
