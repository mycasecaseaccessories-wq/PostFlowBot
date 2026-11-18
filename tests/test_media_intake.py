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
    intake = MessageIntakeService(database.session_factory)
    result = await intake.ingest(
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
    payload = await intake.build_publish_payload(
        content_id=result.content_id, target_channel_id=target.id
    )
    assert payload is not None
    assert payload.text == ""
    assert len(payload.media) == 1
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
    payload = await intake.build_publish_payload(
        content_id=first.content_id, target_channel_id=target.id
    )
    assert payload is not None
    assert [item.telegram_file_id for item in payload.media] == [
        "album-photo-1", "album-photo-2"
    ]
    await database.close()


@pytest.mark.asyncio
async def test_route_filter_is_applied_only_to_target_payload(tmp_path: Path):
    database = Database(settings_for(tmp_path / "route-filter.db"))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=-1001234500301, title="Source")
        target_a = TargetChannel(
            telegram_chat_id=-1001234500302, title="A",
            posting_permission_status="verified",
        )
        target_b = TargetChannel(
            telegram_chat_id=-1001234500303, title="B",
            posting_permission_status="verified",
        )
        session.add_all([source, target_a, target_b])
        await session.flush()
        session.add_all([
            RepostRule(
                source_channel_id=source.id, target_channel_id=target_a.id,
                remove_usernames=True, remove_links=True, remove_keywords="sale",
            ),
            RepostRule(source_channel_id=source.id, target_channel_id=target_b.id),
        ])
        await session.commit()
        chat_id = source.telegram_chat_id
        target_a_id, target_b_id = target_a.id, target_b.id

    intake = MessageIntakeService(database.session_factory)
    result = await intake.ingest(
        source_chat_id=chat_id, message_id=701,
        text="Sale from @sample_user https://example.com",
        formatting_entities=[{"_": "MessageEntityBold", "offset": 0, "length": 4}],
    )
    payload_a = await intake.build_publish_payload(
        content_id=result.content_id, target_channel_id=target_a_id
    )
    payload_b = await intake.build_publish_payload(
        content_id=result.content_id, target_channel_id=target_b_id
    )
    assert payload_a is not None and payload_b is not None
    assert payload_a.text == "from"
    assert payload_a.formatting_entities == ()
    assert payload_b.text == "Sale from @sample_user https://example.com"
    assert payload_b.formatting_entities == ({"_": "MessageEntityBold", "offset": 0, "length": 4},)
    async with database.session() as session:
        content = await session.get(Content, result.content_id)
        assert content.caption == "Sale from @sample_user https://example.com"
    await database.close()


@pytest.mark.asyncio
async def test_album_edit_and_delete_reconcile_individual_source_items(tmp_path: Path):
    database = Database(settings_for(tmp_path / "album-edits.db"))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=-1001234500401, title="Source")
        target = TargetChannel(
            telegram_chat_id=-1001234500402, title="Target",
            posting_permission_status="verified",
        )
        session.add_all([source, target])
        await session.flush()
        session.add(RepostRule(source_channel_id=source.id, target_channel_id=target.id))
        await session.commit()
        chat_id, target_id = source.telegram_chat_id, target.id

    intake = MessageIntakeService(database.session_factory)
    first = await intake.ingest(
        source_chat_id=chat_id, message_id=801, text="Original album caption",
        grouped_id=888, media_items=[
            MediaDescriptor("album-edit-1", "album-edit-unique-1", "photo")
        ],
    )
    second = await intake.ingest(
        source_chat_id=chat_id, message_id=802, text=None,
        grouped_id=888, media_items=[
            MediaDescriptor("album-edit-2", "album-edit-unique-2", "photo")
        ],
    )
    assert first.accepted and second.accepted
    replaced = await intake.ingest(
        source_chat_id=chat_id, message_id=802, text=None,
        grouped_id=888, media_items=[
            MediaDescriptor("album-edit-2-new", "album-edit-unique-2-new", "photo")
        ],
    )
    assert replaced.accepted

    async with database.session() as session:
        links_before_delete = list((await session.scalars(
            select(ContentMedia).order_by(ContentMedia.display_order)
        )).all())
        assert [link.display_order for link in links_before_delete] == [0, 1]
        assert links_before_delete[1].source_message_id == 802

    assert await intake.update_source_message(
        source_chat_id=chat_id, message_id=801, text="Updated album caption"
    )
    assert await intake.delete_source_message(source_chat_id=chat_id, message_id=802)
    async with database.session() as session:
        content = await session.get(Content, first.content_id)
        links = list((await session.scalars(select(ContentMedia))).all())
        job = await session.scalar(select(PublishJob))
        assert content.is_archived is False
        assert content.caption == "Updated album caption"
        assert len(links) == 1
        assert links[0].source_message_id == 801
        assert job.status == "queued"

    assert await intake.delete_source_message(source_chat_id=chat_id, message_id=801)
    async with database.session() as session:
        content = await session.get(Content, first.content_id)
        job = await session.scalar(select(PublishJob))
        assert content.is_archived is True
        assert content.caption is None
        assert job.status == "cancelled"
    await database.close()


@pytest.mark.asyncio
async def test_telegram_media_is_downloaded_and_persisted_with_checksum(tmp_path: Path):
    import hashlib

    from app.services.media_storage import LocalMediaStorage

    database = Database(settings_for(tmp_path / "stored-media.db"))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=-1001234500501, title="Source")
        target = TargetChannel(
            telegram_chat_id=-1001234500502, title="Target",
            posting_permission_status="verified",
        )
        session.add_all([source, target])
        await session.flush()
        session.add(RepostRule(source_channel_id=source.id, target_channel_id=target.id))
        await session.commit()
        chat_id, target_id = source.telegram_chat_id, target.id

    descriptor = MediaDescriptor(
        telegram_file_id="stored-file-id",
        telegram_file_unique_id="stored-file-unique-id",
        media_type="document",
        original_file_name="guide.pdf",
        mime_type="application/pdf",
        file_size=14,
    )
    intake = MessageIntakeService(
        database.session_factory,
        LocalMediaStorage(tmp_path / "persistent-volume", max_bytes=1024),
    )
    result = await intake.ingest(
        source_chat_id=chat_id, message_id=901, text="A document",
        content_type="document", media_items=[descriptor],
    )

    class FakeTelegramClient:
        async def download_media(self, message, file):
            Path(file).write_bytes(b"postflow-media")
            return file

    assert await intake.store_telegram_media(
        client=FakeTelegramClient(), message=object(), descriptor=descriptor
    )
    async with database.session() as session:
        media = await session.scalar(select(Media))
        assert media.storage_status == "stored"
        assert media.storage_backend == "local"
        assert media.stored_size == 14
        assert media.sha256 == hashlib.sha256(b"postflow-media").hexdigest()
        stored_path = intake.media_storage.resolve(media.storage_key)
        assert stored_path.read_bytes() == b"postflow-media"

    payload = await intake.build_publish_payload(
        content_id=result.content_id, target_channel_id=target_id
    )
    assert payload is not None
    assert payload.media[0].storage_key is not None
    assert payload.media[0].sha256 == hashlib.sha256(b"postflow-media").hexdigest()
    await database.close()


@pytest.mark.asyncio
async def test_pending_media_is_recovered_from_original_telegram_message(tmp_path: Path):
    from app.services.media_storage import LocalMediaStorage

    database = Database(settings_for(tmp_path / "retry-media.db"))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=-1001234500601, title="Source")
        target = TargetChannel(
            telegram_chat_id=-1001234500602, title="Target",
            posting_permission_status="verified",
        )
        session.add_all([source, target])
        await session.flush()
        session.add(RepostRule(source_channel_id=source.id, target_channel_id=target.id))
        await session.commit()
        chat_id = source.telegram_chat_id

    descriptor = MediaDescriptor(
        telegram_file_id="retry-file-id",
        telegram_file_unique_id="retry-file-unique-id",
        media_type="video",
        original_file_name="clip.mp4",
        file_size=5,
    )
    intake = MessageIntakeService(
        database.session_factory,
        LocalMediaStorage(tmp_path / "retry-volume", max_bytes=1024),
    )
    await intake.ingest(
        source_chat_id=chat_id, message_id=1001, text=None,
        content_type="video", media_items=[descriptor],
    )

    class FailingClient:
        async def download_media(self, message, file):
            raise RuntimeError("temporary Telegram download failure")

    with pytest.raises(RuntimeError, match="temporary Telegram"):
        await intake.store_telegram_media(
            client=FailingClient(), message=object(), descriptor=descriptor
        )

    class RecoveringClient:
        async def get_messages(self, entity, ids):
            assert entity == chat_id and ids == 1001
            return object()

        async def download_media(self, message, file):
            Path(file).write_bytes(b"video")
            return file

    assert await intake.retry_pending_media(client=RecoveringClient(), limit=10) == 1
    async with database.session() as session:
        media = await session.scalar(select(Media))
        assert media.storage_status == "stored"
        assert media.storage_attempts == 2
        assert media.storage_error is None
        assert intake.media_storage.resolve(media.storage_key).read_bytes() == b"video"
    await database.close()
