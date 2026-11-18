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
