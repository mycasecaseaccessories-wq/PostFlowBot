from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.config.settings import load_settings
from app.database import Content, ContentMedia, Media, PublishJob, RepostRule, SourceChannel, TargetChannel
from app.database.database import Database
from app.services.message_intake import MediaDescriptor, MessageIntakeService


def settings_for(path: Path):
    return load_settings({
        "BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
        "API_ID": "12345",
        "API_HASH": "0123456789abcdef0123456789abcdef",
        "TELEGRAM_SESSION": "test-session",
        "ADMIN_USER_IDS": "42",
        "DATABASE_URL": f"sqlite+aiosqlite:///{path}",
    }, dotenv_path=None)


@pytest.mark.asyncio
async def test_media_only_message_is_persisted_and_queued(tmp_path: Path):
    database = Database(settings_for(tmp_path / "media.db"))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=-1001234500101, title="Source")
        target = TargetChannel(
            telegram_chat_id=-1001234500102, title="Target",
            posting_permission_status="verified",
        )
        session.add_all([source, target])
        await session.flush()
        session.add(RepostRule(source_channel_id=source.id, target_channel_id=target.id))
        await session.commit()
        chat_id = source.telegram_chat_id

    descriptor = MediaDescriptor(
        telegram_file_id="packed-photo-id",
        telegram_file_unique_id="telethon:photo:9988",
        media_type="photo",
        mime_type="image/jpeg",
        file_size=1024,
        width=800,
        height=600,
    )
    result = await MessageIntakeService(database.session_factory).ingest(
        source_chat_id=chat_id, message_id=501, text=None,
        content_type="photo", media_items=[descriptor],
    )
    assert result.accepted is True
    assert result.queued_jobs == 1
    async with database.session() as session:
        content = await session.get(Content, result.content_id)
        media = await session.scalar(select(Media))
        link = await session.scalar(select(ContentMedia))
        job = await session.scalar(select(PublishJob))
        assert content.content_type == "photo"
        assert content.caption is None
        assert media.telegram_file_id == "packed-photo-id"
        assert media.width == 800 and media.height == 600
        assert link.content_id == content.id
        assert job.content_id == content.id
    await database.close()


@pytest.mark.asyncio
async def test_album_items_share_one_content_and_one_publish_job(tmp_path: Path):
    database = Database(settings_for(tmp_path / "album.db"))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=-1001234500201, title="Source")
        target = TargetChannel(
            telegram_chat_id=-1001234500202, title="Target",
            posting_permission_status="verified",
        )
        session.add_all([source, target])
        await session.flush()
        session.add(RepostRule(source_channel_id=source.id, target_channel_id=target.id))
        await session.commit()
        chat_id = source.telegram_chat_id

    intake = MessageIntakeService(database.session_factory)
    first = await intake.ingest(
        source_chat_id=chat_id, message_id=601, text="Album caption",
        content_type="photo", grouped_id=777,
        media_items=[MediaDescriptor("album-photo-1", "album-unique-1", "photo")],
    )
    second = await intake.ingest(
        source_chat_id=chat_id, message_id=602, text=None,
        content_type="photo", grouped_id=777,
        media_items=[MediaDescriptor("album-photo-2", "album-unique-2", "photo")],
    )
    assert first.accepted and first.queued_jobs == 1
    assert second.accepted and second.queued_jobs == 0
    async with database.session() as session:
        contents = list((await session.scalars(select(Content))).all())
        links = list((await session.scalars(select(ContentMedia))).all())
        jobs = list((await session.scalars(select(PublishJob))).all())
        assert len(contents) == 1
        assert contents[0].content_type == "album"
        assert contents[0].caption == "Album caption"
        assert len(links) == 2
        assert {link.album_group_key for link in links} == {"777"}
        assert len(jobs) == 1
    await database.close()
