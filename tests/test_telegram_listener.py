from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import app.telegram.listener as listener_module
from app.config.settings import load_settings
from app.core.status import StatusService
from app.database import Content, ContentMedia, Media, PublishJob, RepostRule, SourceChannel, TargetChannel
from app.database.database import Database
from app.services.media_storage import LocalMediaStorage
from app.services.message_intake import MessageIntakeService
from app.telegram.listener import MessageListenerService


def settings_for(path: Path):
    return load_settings({
        "BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
        "API_ID": "12345",
        "API_HASH": "0123456789abcdef0123456789abcdef",
        "TELEGRAM_SESSION": "test-session",
        "ADMIN_USER_IDS": "42",
        "DATABASE_URL": f"sqlite+aiosqlite:///{path}",
    }, dotenv_path=None)


class FakeTelegramClient:
    async def download_media(self, message, file):
        Path(file).write_bytes(f"media-{message.id}".encode())
        return file


def media_message(message_id: int, text: str = "", grouped_id: int | None = None):
    photo = SimpleNamespace(id=message_id + 10000, size=128)
    return SimpleNamespace(
        id=message_id, message=text, photo=photo, document=None,
        grouped_id=grouped_id, entities=[],
    )


async def setup_listener(tmp_path: Path, database_name: str, chat_id: int):
    database = Database(settings_for(tmp_path / database_name))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=chat_id, title="Source")
        target = TargetChannel(
            telegram_chat_id=chat_id - 1, title="Target",
            posting_permission_status="verified",
        )
        session.add_all([source, target])
        await session.flush()
        session.add(RepostRule(source_channel_id=source.id, target_channel_id=target.id))
        await session.commit()
    intake = MessageIntakeService(
        database.session_factory,
        LocalMediaStorage(tmp_path / f"{database_name}-media"),
    )
    telegram = FakeTelegramClient()
    service = MessageListenerService(telegram, StatusService(), intake)
    return database, service


@pytest.mark.asyncio
async def test_listener_new_edit_and_delete_media_message(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        listener_module.utils, "pack_bot_file_id",
        lambda media: f"packed:{media.id}",
    )
    chat_id = -1001234500701
    database, service = await setup_listener(tmp_path, "listener-single.db", chat_id)
    try:
        message = media_message(1101, "Original caption")
        await service._on_new_message(SimpleNamespace(chat_id=chat_id, message=message))
        async with database.session() as session:
            content = await session.scalar(select(Content))
            media = await session.scalar(select(Media))
            job = await session.scalar(select(PublishJob))
            assert content.caption == "Original caption"
            assert media.storage_status == "stored"
            assert media.storage_key is not None
            assert job.status == "queued"

        edited = media_message(1101, "Edited caption")
        await service._on_message_edited(SimpleNamespace(chat_id=chat_id, message=edited))
        async with database.session() as session:
            content = await session.scalar(select(Content))
            assert content.caption == "Edited caption"

        await service._on_message_deleted(
            SimpleNamespace(chat_id=chat_id, deleted_ids=[1101])
        )
        async with database.session() as session:
            content = await session.scalar(select(Content))
            job = await session.scalar(select(PublishJob))
            assert content.is_archived is True
            assert job.status == "cancelled"
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_listener_album_events_keep_content_until_last_item_deleted(
    tmp_path: Path, monkeypatch,
):
    monkeypatch.setattr(
        listener_module.utils, "pack_bot_file_id",
        lambda media: f"packed:{media.id}",
    )
    chat_id = -1001234500801
    database, service = await setup_listener(tmp_path, "listener-album.db", chat_id)
    try:
        first = media_message(1201, "Album caption", grouped_id=9911)
        second = media_message(1202, grouped_id=9911)
        await service._on_new_message(SimpleNamespace(chat_id=chat_id, message=first))
        await service._on_new_message(SimpleNamespace(chat_id=chat_id, message=second))

        async with database.session() as session:
            contents = list((await session.scalars(select(Content))).all())
            links = list((await session.scalars(select(ContentMedia))).all())
            jobs = list((await session.scalars(select(PublishJob))).all())
            assert len(contents) == 1
            assert contents[0].content_type == "album"
            assert len(links) == 2
            assert len(jobs) == 1

        await service._on_message_deleted(
            SimpleNamespace(chat_id=chat_id, deleted_ids=[1201])
        )
        async with database.session() as session:
            content = await session.scalar(select(Content))
            links = list((await session.scalars(select(ContentMedia))).all())
            assert content.is_archived is False
            assert len(links) == 1

        await service._on_message_deleted(
            SimpleNamespace(chat_id=chat_id, deleted_ids=[1202])
        )
        async with database.session() as session:
            content = await session.scalar(select(Content))
            job = await session.scalar(select(PublishJob))
            assert content.is_archived is True
            assert job.status == "cancelled"
    finally:
        await database.close()
