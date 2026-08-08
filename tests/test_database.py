from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config.settings import load_settings
from app.database.database import Database
from app.database.models import Admin, RepostHistory, SourceChannel, TargetChannel


def environment(database_url: str) -> dict[str, str]:
    return {
        "BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
        "API_ID": "12345",
        "API_HASH": "0123456789abcdef0123456789abcdef",
        "TELEGRAM_SESSION": "test-session",
        "ADMIN_USER_IDS": "42",
        "DATABASE_URL": database_url,
    }


@pytest.mark.asyncio
async def test_database_initialization_and_model_creation(tmp_path: Path) -> None:
    database = Database(load_settings(environment(f"sqlite+aiosqlite:///{tmp_path}/nested/db.sqlite"), dotenv_path=None))
    await database.initialize()
    async with database.session() as session:
        session.add(Admin(telegram_user_id=42))
        await session.commit()
        result = await session.scalar(select(Admin).where(Admin.telegram_user_id == 42))
        assert result is not None
    await database.close()
    assert (tmp_path / "nested" / "db.sqlite").exists()


@pytest.mark.asyncio
async def test_duplicate_history_constraint(tmp_path: Path) -> None:
    database = Database(load_settings(environment(f"sqlite+aiosqlite:///{tmp_path}/db.sqlite"), dotenv_path=None))
    await database.initialize()
    async with database.session() as session:
        source = SourceChannel(telegram_chat_id=-1001)
        target = TargetChannel(telegram_chat_id=-2001)
        session.add_all([source, target])
        await session.flush()
        session.add_all(
            [
                RepostHistory(
                    source_channel_id=source.id,
                    target_channel_id=target.id,
                    source_message_id=99,
                    status="pending",
                ),
                RepostHistory(
                    source_channel_id=source.id,
                    target_channel_id=target.id,
                    source_message_id=99,
                    status="pending",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    await database.close()