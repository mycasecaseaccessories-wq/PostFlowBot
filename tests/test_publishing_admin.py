from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config.settings import load_settings
from app.database import Admin, Content, PublishAttempt, PublishJob, TargetChannel
from app.database.automation_models import AuditEvent, PublishDeliveryReceipt, PublishJobStatus
from app.database.database import Database
from app.services.publishing_admin import PublishJobAdminService


def make_settings(path: Path):
    return load_settings(
        {
            "BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            "API_ID": "12345",
            "API_HASH": "0123456789abcdef0123456789abcdef",
            "TELEGRAM_SESSION": "test-session",
            "ADMIN_USER_IDS": "42",
            "DATABASE_URL": f"sqlite+aiosqlite:///{path}",
        },
        dotenv_path=None,
    )


async def create_job(database: Database) -> str:
    async with database.session() as session:
        target = TargetChannel(
            telegram_chat_id=-100123456,
            title="Test destination",
            posting_permission_status="verified",
        )
        content = Content(title="Test announcement", caption="Hello")
        session.add_all([target, content])
        await session.flush()
        job = PublishJob(
            content=content,
            target_channel=target,
            idempotency_key=f"admin-test-{datetime.now(UTC).timestamp()}",
            run_at=datetime.now(UTC),
            max_attempts=3,
        )
        session.add(job)
        await session.commit()
        return job.id


@pytest.mark.asyncio
async def test_admin_can_list_and_inspect_jobs_with_all_receipts(tmp_path: Path):
    database = Database(make_settings(tmp_path / "publish-admin-list.db"))
    await database.initialize()
    job_id = await create_job(database)
    async with database.session() as session:
        job = await session.get(PublishJob, job_id)
        job.status = PublishJobStatus.PUBLISHED.value
        attempt = PublishAttempt(
            publish_job_id=job_id, attempt_number=1, outcome="published",
            telegram_message_id=501, finished_at=datetime.now(UTC),
        )
        session.add(attempt)
        await session.flush()
        session.add_all([
            PublishDeliveryReceipt(
                publish_job_id=job_id, attempt_id=attempt.id,
                telegram_message_id=501, message_ordinal=0,
            ),
            PublishDeliveryReceipt(
                publish_job_id=job_id, attempt_id=attempt.id,
                telegram_message_id=502, message_ordinal=1,
            ),
        ])
        await session.commit()

    service = PublishJobAdminService(database.session_factory)
    rows = await service.list_jobs(status="published")
    detail = await service.get_job(job_id)
    assert rows[0]["id"] == job_id
    assert detail["status"] == "published"
    assert [item["message_id"] for item in detail["receipts"]] == [501, 502]
    await database.close()


@pytest.mark.asyncio
async def test_admin_retry_is_limited_to_failed_or_uncertain_and_audited(tmp_path: Path):
    database = Database(make_settings(tmp_path / "publish-admin-retry.db"))
    await database.initialize()
    job_id = await create_job(database)
    async with database.session() as session:
        job = await session.get(PublishJob, job_id)
        job.status = PublishJobStatus.UNCERTAIN.value
        job.attempts = 1
        job.last_error = "Transport outcome unknown"
        await session.commit()

    service = PublishJobAdminService(database.session_factory)
    job = await service.retry_job(job_id, operator_telegram_user_id=42)
    assert job.status == PublishJobStatus.QUEUED.value
    async with database.session() as session:
        event = await session.scalar(select(AuditEvent).where(
            AuditEvent.action == "publish_job.manual_retry",
            AuditEvent.entity_id == job_id,
        ))
        assert event is not None
        assert '"operator_confirmed_no_existing_delivery": true' in event.details_json
    await database.close()


@pytest.mark.asyncio
async def test_admin_cannot_retry_job_that_is_not_failed_or_uncertain(tmp_path: Path):
    database = Database(make_settings(tmp_path / "publish-admin-retry-invalid.db"))
    await database.initialize()
    job_id = await create_job(database)
    service = PublishJobAdminService(database.session_factory)
    with pytest.raises(ValueError, match="Only failed or uncertain"):
        await service.retry_job(job_id, operator_telegram_user_id=42)
    await database.close()


@pytest.mark.asyncio
async def test_admin_recovers_only_stale_processing_jobs_to_uncertain(tmp_path: Path):
    database = Database(make_settings(tmp_path / "publish-admin-recover.db"))
    await database.initialize()
    job_id = await create_job(database)
    async with database.session() as session:
        job = await session.get(PublishJob, job_id)
        job.status = PublishJobStatus.PROCESSING.value
        job.attempts = 1
        job.locked_at = datetime.now(UTC) - timedelta(minutes=20)
        session.add(PublishAttempt(
            publish_job_id=job_id, attempt_number=1, outcome="processing",
        ))
        await session.commit()

    service = PublishJobAdminService(database.session_factory)
    job = await service.recover_stale_job(job_id, operator_telegram_user_id=42)
    assert job.status == PublishJobStatus.UNCERTAIN.value
    async with database.session() as session:
        event = await session.scalar(select(AuditEvent).where(
            AuditEvent.action == "publish_job.mark_uncertain",
            AuditEvent.entity_id == job_id,
        ))
        assert event is not None
    await database.close()


@pytest.mark.asyncio
async def test_admin_cannot_recover_a_fresh_processing_lock(tmp_path: Path):
    database = Database(make_settings(tmp_path / "publish-admin-fresh.db"))
    await database.initialize()
    job_id = await create_job(database)
    async with database.session() as session:
        job = await session.get(PublishJob, job_id)
        job.status = PublishJobStatus.PROCESSING.value
        job.attempts = 1
        job.locked_at = datetime.now(UTC)
        await session.commit()

    service = PublishJobAdminService(database.session_factory)
    with pytest.raises(ValueError, match="not stale"):
        await service.recover_stale_job(job_id, operator_telegram_user_id=42)
    await database.close()
