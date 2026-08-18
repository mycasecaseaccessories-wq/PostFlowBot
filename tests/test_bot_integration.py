from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import admin_keyboard
from app.config.settings import load_settings
from app.core.lifecycle import Application


def environment(database_url: str) -> dict[str, str]:
    return {
        "BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
        "API_ID": "12345",
        "API_HASH": "0123456789abcdef0123456789abcdef",
        "TELEGRAM_SESSION": "test-session",
        "ADMIN_USER_IDS": "42",
        "DATABASE_URL": database_url,
        "LOG_LEVEL": "INFO",
    }


@pytest.mark.asyncio
async def test_application_constructs_and_starts_without_router_signature_error(
    tmp_path: Path,
) -> None:
    settings = load_settings(
        environment(f"sqlite+aiosqlite:///{tmp_path / 'postflow.db'}"),
        dotenv_path=None,
    )
    application = Application(settings)
    application.telethon.connect = AsyncMock()
    application.telethon.disconnect = AsyncMock()
    application.telethon.is_connected = lambda: True
    application.telethon.is_authorized = lambda: True
    application.listener.start = AsyncMock()
    application.listener.stop = AsyncMock()
    application.bot.stop = AsyncMock()

    await application.startup()
    assert application._started is True
    assert application.status_service.database_connected is True
    assert application.status_service.telethon_connected is True
    assert application.status_service.telethon_authorized is True

    await application.shutdown()
    assert application._started is False
    assert application.database.initialized is False


def test_admin_keyboard_matches_phase_zero_cms_roadmap() -> None:
    labels = {
        button.text
        for row in admin_keyboard().keyboard
        for button in row
    }
    assert labels == {
        "🏠 Dashboard",
        "📝 Content",
        "📢 Channels",
        "📅 Scheduler",
        "📚 Library",
        "📊 Analytics",
        "⚙️ Settings",
    }
