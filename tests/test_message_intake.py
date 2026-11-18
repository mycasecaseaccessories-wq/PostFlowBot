from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.config.settings import load_settings
from app.database import Content, PublishJob, RepostRule, SourceChannel, TargetChannel
from app.database.database import Database
from app.services.message_intake import MessageIntakeService


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
async def test_source_intake_routes_once_and_ignores_duplicates(tmp_path: Path):
    database = Database(settings_for(tmp_path / "intake.db"))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=-1001234500001, title="Source")
        target = TargetChannel(
            telegram_chat_id=-1001234500002, title="Target",
            posting_permission_status="verified",
        )
        session.add_all([source, target])
        await session.flush()
        session.add(RepostRule(source_channel_id=source.id, target_channel_id=target.id))
        await session.commit()
        source_chat_id = source.telegram_chat_id

    intake = MessageIntakeService(database.session_factory)
    first = await intake.ingest(
        source_chat_id=source_chat_id, message_id=77, text="A new post"
    )
    assert first.accepted is True
    assert first.queued_jobs == 1

    duplicate = await intake.ingest(
        source_chat_id=source_chat_id, message_id=77, text="A new post"
    )
    assert duplicate.duplicate is True

    async with database.session() as session:
        contents = list((await session.scalars(select(Content))).all())
        jobs = list((await session.scalars(select(PublishJob))).all())
        assert len(contents) == 1
        assert len(jobs) == 1
        assert contents[0].source_message_id == 77
    await database.close()


@pytest.mark.asyncio
async def test_intake_does_not_queue_unverified_or_inactive_targets(tmp_path: Path):
    database = Database(settings_for(tmp_path / "permission.db"))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=-1001234500011, title="Source")
        target = TargetChannel(
            telegram_chat_id=-1001234500012, title="Target",
            posting_permission_status="unknown",
        )
        session.add_all([source, target])
        await session.flush()
        session.add(RepostRule(source_channel_id=source.id, target_channel_id=target.id))
        await session.commit()
        chat_id = source.telegram_chat_id

    result = await MessageIntakeService(database.session_factory).ingest(
        source_chat_id=chat_id, message_id=88, text="Pending target"
    )
    assert result.accepted is True
    assert result.queued_jobs == 0
    await database.close()


@pytest.mark.asyncio
async def test_route_delay_is_applied_to_publish_job(tmp_path: Path):
    from datetime import UTC, datetime, timedelta

    database = Database(settings_for(tmp_path / "delay.db"))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=-1001234500021, title="Source")
        target = TargetChannel(
            telegram_chat_id=-1001234500022, title="Target",
            posting_permission_status="verified",
        )
        session.add_all([source, target])
        await session.flush()
        session.add(RepostRule(
            source_channel_id=source.id, target_channel_id=target.id,
            delay_seconds=120,
        ))
        await session.commit()
        chat_id = source.telegram_chat_id

    before = datetime.now(UTC)
    result = await MessageIntakeService(database.session_factory).ingest(
        source_chat_id=chat_id, message_id=99, text="Delayed post"
    )
    after = datetime.now(UTC)
    assert result.queued_jobs == 1
    async with database.session() as session:
        job = await session.scalar(select(PublishJob))
        assert before + timedelta(seconds=120) <= job.run_at
        assert job.run_at <= after + timedelta(seconds=120)
    await database.close()


@pytest.mark.asyncio
async def test_edit_updates_imported_content_and_delete_cancels_queued_jobs(tmp_path: Path):
    from app.database.automation_models import PublishJobStatus
    from app.database.cms_models import ContentStatus

    database = Database(settings_for(tmp_path / "edit-delete.db"))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=-1001234500031, title="Source")
        target = TargetChannel(
            telegram_chat_id=-1001234500032, title="Target",
            posting_permission_status="verified",
        )
        session.add_all([source, target])
        await session.flush()
        session.add(RepostRule(source_channel_id=source.id, target_channel_id=target.id))
        await session.commit()
        chat_id = source.telegram_chat_id

    intake = MessageIntakeService(database.session_factory)
    created = await intake.ingest(
        source_chat_id=chat_id, message_id=111, text="Original"
    )
    assert created.accepted
    assert await intake.update_source_message(
        source_chat_id=chat_id, message_id=111, text="Edited text"
    )
    async with database.session() as session:
        content = await session.get(Content, created.content_id)
        job = await session.scalar(select(PublishJob))
        assert content.caption == "Edited text"
        assert job.status == PublishJobStatus.QUEUED.value

    assert await intake.delete_source_message(
        source_chat_id=chat_id, message_id=111
    )
    async with database.session() as session:
        content = await session.get(Content, created.content_id)
        job = await session.scalar(select(PublishJob))
        assert content.status == ContentStatus.ARCHIVED.value
        assert content.is_archived is True
        assert job.status == PublishJobStatus.CANCELLED.value
    await database.close()
