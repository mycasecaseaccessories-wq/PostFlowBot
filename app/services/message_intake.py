"""Persist Telegram text/media intake and fan it out to active routes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.automation_models import PublishJob, PublishJobStatus
from app.database.cms_models import (
    Content, ContentMedia, ContentOrigin, ContentStatus, ContentType, Media,
)
from app.database.models import RepostRule, SourceChannel, TargetChannel
from app.services.content_transform import transform_text
from app.services.media_storage import LocalMediaStorage


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
    storage_backend: str | None = None
    storage_key: str | None = None
    sha256: str | None = None
    stored_size: int | None = None


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

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession],
        media_storage: LocalMediaStorage | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.media_storage = media_storage

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
                    caption_source_message_id=message_id if body else None,
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
            caption_added = bool(not created and body and not content.caption)
            if caption_added:
                # Telegram albums commonly put the caption on only one item.
                content.caption = body
                content.body_text = body
                content.title = body[:255]
                content.caption_source_message_id = message_id

            attached = 0
            current_media_ids: set[str] = set()
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
                current_media_ids.add(media.id)
                link = await session.get(ContentMedia, (content.id, media.id))
                if link is None:
                    current_order = await session.scalar(
                        select(func.count(ContentMedia.media_id)).where(
                            ContentMedia.content_id == content.id
                        )
                    )
                    session.add(ContentMedia(
                        content_id=content.id, media_id=media.id,
                        display_order=int(current_order or 0),
                        album_group_key=album_key,
                        source_message_id=message_id,
                    ))
                    attached += 1
            if items:
                previous_links = list((await session.scalars(select(ContentMedia).where(
                    ContentMedia.content_id == content.id,
                    ContentMedia.source_message_id == message_id,
                ))).all())
                for previous in previous_links:
                    if previous.media_id not in current_media_ids:
                        await session.delete(previous)

            if not created:
                if grouped_id is not None:
                    settle_until = datetime.now(UTC) + timedelta(seconds=5)
                    queued_jobs = list((await session.scalars(select(PublishJob).where(
                        PublishJob.content_id == content.id,
                        PublishJob.status == PublishJobStatus.QUEUED.value,
                    ))).all())
                    for queued_job in queued_jobs:
                        existing_run_at = queued_job.run_at
                        if existing_run_at is not None and existing_run_at.tzinfo is None:
                            existing_run_at = existing_run_at.replace(tzinfo=UTC)
                        queued_job.run_at = max(existing_run_at, settle_until) if existing_run_at else settle_until
                        queued_job.updated_at = datetime.now(UTC)
                await session.commit()
                if attached == 0 and not caption_added:
                    return IntakeResult(
                        False, duplicate=True, content_id=content.id,
                        reason="duplicate_source_message",
                    )
                return IntakeResult(
                    True, content_id=content.id,
                    reason="album_item_attached" if attached else "album_caption_updated",
                )

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
                .join(TargetChannel, TargetChannel.id == RepostRule.target_channel_id)
                .where(
                    Content.id == content_id,
                    Content.is_archived.is_(False),
                    RepostRule.target_channel_id == target_channel_id,
                    RepostRule.is_active.is_(True),
                    TargetChannel.is_active.is_(True),
                    TargetChannel.posting_permission_status == "verified",
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
                storage_backend=item.storage_backend,
                storage_key=item.storage_key,
                sha256=item.sha256,
                stored_size=item.stored_size,
            ) for item in media_rows)
            return PublishPayload(
                content_id=content.id,
                content_type=content.content_type,
                text=transformed,
                media=media,
            )

    async def store_telegram_media(
        self, *, client, message, descriptor: MediaDescriptor,
    ) -> bool:
        """Download a source message and atomically persist its media bytes."""
        if self.media_storage is None:
            return False
        async with self.session_factory() as session:
            media_query = [Media.telegram_file_id == descriptor.telegram_file_id]
            if descriptor.telegram_file_unique_id:
                media_query.append(
                    Media.telegram_file_unique_id == descriptor.telegram_file_unique_id
                )
            media = await session.scalar(select(Media).where(or_(*media_query)))
            if media is None:
                return False
            if media.storage_status == "stored" and media.storage_key:
                return True
            media.storage_attempts += 1
            media.storage_error = None
            media_id = media.id
            await session.commit()

        try:
            if descriptor.file_size and descriptor.file_size > self.media_storage.max_bytes:
                raise ValueError(
                    f"Media exceeds configured limit ({descriptor.file_size} bytes)."
                )
            with tempfile.TemporaryDirectory(prefix="postflow-media-") as temp_dir:
                suffix = Path(descriptor.original_file_name or "").suffix[:12]
                download_path = Path(temp_dir) / f"source{suffix}"
                downloaded = await client.download_media(message, file=str(download_path))
                actual_path = Path(downloaded) if isinstance(downloaded, str) else download_path
                stored = await self.media_storage.store_file(
                    actual_path, media_id, descriptor.original_file_name
                )
            async with self.session_factory() as session:
                media = await session.get(Media, media_id)
                if media is None:
                    return False
                media.storage_backend = stored.backend
                media.storage_key = stored.key
                media.sha256 = stored.sha256
                media.stored_size = stored.size
                media.storage_status = "stored"
                media.storage_error = None
                await session.commit()
            return True
        except Exception as exc:
            async with self.session_factory() as session:
                media = await session.get(Media, media_id)
                if media is not None:
                    media.storage_status = "pending"
                    media.storage_error = f"{type(exc).__name__}: {exc}"[:1000]
                    await session.commit()
            raise


    async def retry_pending_media(self, *, client, limit: int = 20) -> int:
        """Retry media downloads using the original channel/message as source."""
        async with self.session_factory() as session:
            rows = (await session.execute(
                select(Media, SourceChannel.telegram_chat_id, ContentMedia.source_message_id)
                .join(ContentMedia, ContentMedia.media_id == Media.id)
                .join(Content, Content.id == ContentMedia.content_id)
                .join(SourceChannel, SourceChannel.id == Content.source_channel_id)
                .where(
                    Media.storage_status == "pending",
                    Content.is_archived.is_(False),
                    ContentMedia.source_message_id.is_not(None),
                )
                .order_by(Media.created_at.asc())
                .limit(max(1, min(int(limit), 100)))
            )).all()
            pending = [
                (
                    int(chat_id), int(message_id),
                    MediaDescriptor(
                        telegram_file_id=media.telegram_file_id,
                        telegram_file_unique_id=media.telegram_file_unique_id,
                        media_type=media.media_type,
                        original_file_name=media.original_file_name,
                        mime_type=media.mime_type,
                        file_size=media.file_size,
                        width=media.width,
                        height=media.height,
                        duration=media.duration,
                        storage_backend=media.storage_backend,
                        storage_key=media.storage_key,
                        sha256=media.sha256,
                        stored_size=media.stored_size,
                    ),
                )
                for media, chat_id, message_id in rows
            ]
        recovered = 0
        seen: set[tuple[str, int, int]] = set()
        for chat_id, message_id, descriptor in pending:
            identity = (descriptor.telegram_file_id, chat_id, message_id)
            if identity in seen:
                continue
            seen.add(identity)
            try:
                message = await client.get_messages(chat_id, ids=message_id)
                if message is not None and await self.store_telegram_media(
                    client=client, message=message, descriptor=descriptor
                ):
                    recovered += 1
            except Exception:
                # Keep the pending status and error detail for the next retry.
                continue
        return recovered

    async def update_source_message(
        self, *, source_chat_id: int, message_id: int, text: str | None,
    ) -> bool:
        body = (text or "").strip()
        async with self.session_factory() as session:
            source = await session.scalar(select(SourceChannel).where(
                SourceChannel.telegram_chat_id == source_chat_id))
            if source is None:
                return False
            content = await session.scalar(select(Content).where(
                Content.source_channel_id == source.id,
                or_(
                    Content.source_message_id == message_id,
                    Content.id.in_(select(ContentMedia.content_id).where(
                        ContentMedia.source_message_id == message_id
                    )),
                ),
            ))
            if content is None or content.is_archived:
                return False
            if content.caption_source_message_id == message_id:
                content.title = body[:255] or None
                content.caption = body or None
                content.body_text = body or None
                if not body:
                    content.caption_source_message_id = None
            elif body and not content.caption:
                content.title = body[:255]
                content.caption = body
                content.body_text = body
                content.caption_source_message_id = message_id
            content.updated_at = datetime.now(UTC)
            await session.commit()
            return True

    async def delete_source_message(
        self, *, source_chat_id: int, message_id: int,
    ) -> bool:
        """Reconcile album item deletion; archive only when no album media remains."""
        async with self.session_factory() as session:
            source = await session.scalar(select(SourceChannel).where(
                SourceChannel.telegram_chat_id == source_chat_id))
            if source is None:
                return False
            content = await session.scalar(select(Content).where(
                Content.source_channel_id == source.id,
                or_(
                    Content.source_message_id == message_id,
                    Content.id.in_(select(ContentMedia.content_id).where(
                        ContentMedia.source_message_id == message_id
                    )),
                ),
            ))
            if content is None:
                return False
            now = datetime.now(UTC)
            if content.content_type == ContentType.ALBUM.value:
                link = await session.scalar(select(ContentMedia).where(
                    ContentMedia.content_id == content.id,
                    ContentMedia.source_message_id == message_id,
                ))
                if link is not None:
                    await session.delete(link)
                if content.caption_source_message_id == message_id:
                    content.caption = None
                    content.body_text = None
                    content.title = None
                    content.caption_source_message_id = None
                remaining = await session.scalar(select(func.count(ContentMedia.media_id)).where(
                    ContentMedia.content_id == content.id
                ))
                if remaining:
                    content.updated_at = now
                    await session.commit()
                    return True
            elif content.source_message_id != message_id:
                return False

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
