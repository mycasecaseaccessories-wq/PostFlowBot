from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config.settings import load_settings
from app.database import TargetChannel
from app.database.database import Database
from app.services.channel_permission import ChannelPermissionService


def settings_for(path: Path):
    return load_settings({
        "BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
        "API_ID": "12345",
        "API_HASH": "0123456789abcdef0123456789abcdef",
        "TELEGRAM_SESSION": "test-session",
        "ADMIN_USER_IDS": "42",
        "DATABASE_URL": f"sqlite+aiosqlite:///{path}",
    }, dotenv_path=None)


class FakeClient:
    async def get_entity(self, chat_id):
        return SimpleNamespace(id=chat_id)

    async def get_participant(self, entity, participant):
        return SimpleNamespace(admin_rights=SimpleNamespace(post_messages=True))


class FakeTelethon:
    def is_connected(self):
        return True

    def is_authorized(self):
        return True

    def get_client(self):
        return FakeClient()


@pytest.mark.asyncio
async def test_permission_check_persists_verified_state(tmp_path: Path):
    database = Database(settings_for(tmp_path / "permission-verified.db"))
    await database.initialize()
    async with database.session() as session:
        target = TargetChannel(telegram_chat_id=-1001234500101, title="Target")
        session.add(target)
        await session.commit()
        target_id = target.id

    allowed, detail = await ChannelPermissionService(
        database.session_factory, FakeTelethon()
    ).verify(target_id)
    assert allowed is True
    assert "verified" in detail.lower()
    async with database.session() as session:
        target = await session.get(TargetChannel, target_id)
        assert target.posting_permission_status == "verified"
        assert target.publishing_permission_confirmed is True
        assert target.permission_checked_at is not None
        assert target.permission_error is None
    await database.close()


@pytest.mark.asyncio
async def test_permission_check_denies_unavailable_telethon_account(tmp_path: Path):
    database = Database(settings_for(tmp_path / "permission-denied.db"))
    await database.initialize()
    async with database.session() as session:
        target = TargetChannel(telegram_chat_id=-1001234500102, title="Target")
        session.add(target)
        await session.commit()
        target_id = target.id

    class OfflineTelethon(FakeTelethon):
        def is_connected(self):
            return False

    allowed, detail = await ChannelPermissionService(
        database.session_factory, OfflineTelethon()
    ).verify(target_id)
    assert allowed is False
    assert "not connected" in detail.lower()
    async with database.session() as session:
        target = await session.get(TargetChannel, target_id)
        assert target.posting_permission_status == "denied"
        assert target.publishing_permission_confirmed is False
        assert target.permission_checked_at is not None
        assert target.permission_error
    await database.close()
