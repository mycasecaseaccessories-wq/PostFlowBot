from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.settings import load_settings
from app.database.database import Database
from app.database.migration import require_compatible_schema, validate_existing_schema
from app.database.models import Admin, Base

BASELINE_REVISION = "38ec41931a62"
CMS_HEAD_REVISION = "e5f6a7b8c9d0"
CMS_TABLES = {
    "categories",
    "collections",
    "contents",
    "media",
    "content_media",
    "tags",
    "content_tags",
}
AUTOMATION_TABLES = {
    "workspaces",
    "workspace_members",
    "content_approvals",
    "schedules",
    "publish_jobs",
    "publish_attempts",
    "publish_delivery_receipts",
    "audit_events",
}
EXPECTED_TABLES = {
    "admins",
    "source_channels",
    "target_channels",
    "repost_rules",
    "repost_history",
    "system_settings",
}


def environment(database_url: str, schema_mode: str = "bootstrap") -> dict[str, str]:
    return {
        "BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
        "API_ID": "12345",
        "API_HASH": "0123456789abcdef0123456789abcdef",
        "TELEGRAM_SESSION": "test-session",
        "ADMIN_USER_IDS": "42",
        "DATABASE_URL": database_url,
        "DATABASE_SCHEMA_MODE": schema_mode,
    }


def run_alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.asyncio
async def test_model_metadata_contains_expected_tables() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


@pytest.mark.asyncio
async def test_fresh_database_upgrade_creates_expected_schema(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}"
    run_alembic(database_url, "upgrade", "head")

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            contents_columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in inspect(sync_connection).get_columns("contents")
                }
            )
            media_columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in inspect(sync_connection).get_columns("media")
                }
            )
            content_media_columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in inspect(sync_connection).get_columns("content_media")
                }
            )
            target_columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in inspect(sync_connection).get_columns("target_channels")
                }
            )
            contents_foreign_keys = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_foreign_keys("contents")
            )
            contents_uniques = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_unique_constraints("contents")
            )
    finally:
        await engine.dispose()

    assert EXPECTED_TABLES <= tables
    assert CMS_TABLES <= tables
    assert AUTOMATION_TABLES <= tables
    assert revision == CMS_HEAD_REVISION
    assert {"origin", "source_channel_id", "source_message_id", "caption_source_message_id", "formatting_entities"} <= contents_columns
    assert {"storage_backend", "storage_key", "sha256", "stored_size", "storage_status", "storage_attempts", "storage_error"} <= media_columns
    assert {"source_message_id"} <= content_media_columns
    assert {
        "posting_permission_status",
        "permission_checked_at",
        "permission_error",
    } <= target_columns
    assert any(
        fk["referred_table"] == "source_channels"
        and fk["constrained_columns"] == ["source_channel_id"]
        for fk in contents_foreign_keys
    )
    assert any(
        constraint["column_names"] == ["source_channel_id", "source_message_id"]
        for constraint in contents_uniques
    )


@pytest.mark.asyncio
async def test_migration_managed_database_initialization_verifies_existing_schema(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'managed.db'}"
    run_alembic(database_url, "upgrade", "head")
    database = Database(
        load_settings(environment(database_url, schema_mode="migrations"), dotenv_path=None)
    )
    await database.initialize()
    assert database.initialized is True
    await database.close()


@pytest.mark.asyncio
async def test_transaction_rollback_leaves_no_partial_row(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'rollback.db'}"
    database = Database(
        load_settings(environment(database_url), dotenv_path=None)
    )
    await database.initialize()
    async with database.session() as session:
        session.add(Admin(telegram_user_id=999))
        await session.rollback()

    async with database.session() as session:
        result = await session.scalar(select(Admin).where(Admin.telegram_user_id == 999))
    await database.close()
    assert result is None


@pytest.mark.asyncio
async def test_schema_drift_is_reported_before_adoption(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'drift.db'}"
    engine = create_async_engine(database_url)
    try:
        validation = await validate_existing_schema(engine)
        assert validation.compatible is False
        with pytest.raises(RuntimeError, match="missing tables"):
            await require_compatible_schema(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_baseline_downgrade_and_upgrade_round_trip(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'roundtrip.db'}"
    run_alembic(database_url, "upgrade", "head")
    run_alembic(database_url, "downgrade", "base")
    run_alembic(database_url, "upgrade", "head")

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()
    assert revision == CMS_HEAD_REVISION


@pytest.mark.asyncio
async def test_sqlite_foreign_keys_are_enabled(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'foreign_keys.db'}"
    database = Database(load_settings(environment(database_url), dotenv_path=None))
    await database.initialize()
    async with database.engine.connect() as connection:
        enabled = await connection.scalar(text("PRAGMA foreign_keys"))
    await database.close()
    assert enabled == 1


@pytest.mark.asyncio
async def test_migration_mode_rejects_untracked_schema(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'untracked.db'}"
    bootstrap = Database(
        load_settings(environment(database_url, schema_mode="bootstrap"), dotenv_path=None)
    )
    await bootstrap.initialize()
    await bootstrap.close()

    managed = Database(
        load_settings(environment(database_url, schema_mode="migrations"), dotenv_path=None)
    )
    with pytest.raises(RuntimeError, match="alembic_version"):
        await managed.initialize()
    await managed.close()


@pytest.mark.asyncio
async def test_phase_one_point_one_round_trip_preserves_phase_zero_data(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase_roundtrip.db'}"
    run_alembic(database_url, "upgrade", BASELINE_REVISION)

    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO admins (telegram_user_id, is_active, created_at, updated_at) "
                     "VALUES (777, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
            )
    finally:
        await engine.dispose()

    run_alembic(database_url, "upgrade", "head")
    run_alembic(database_url, "downgrade", BASELINE_REVISION)

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            admin_id = await connection.scalar(
                text("SELECT telegram_user_id FROM admins WHERE telegram_user_id = 777")
            )
            tables_after_downgrade = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )
    finally:
        await engine.dispose()
    assert admin_id == 777
    assert "contents" not in tables_after_downgrade
    assert "categories" not in tables_after_downgrade

    run_alembic(database_url, "upgrade", "head")
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            admin_id_after_upgrade = await connection.scalar(
                text("SELECT telegram_user_id FROM admins WHERE telegram_user_id = 777")
            )
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()
    assert admin_id_after_upgrade == 777
    assert revision == CMS_HEAD_REVISION
