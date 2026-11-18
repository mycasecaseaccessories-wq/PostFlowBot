from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config.settings import load_settings
from app.database import Admin, Content, PublishAttempt, PublishJob, TargetChannel
from app.database.automation_models import PublishJobStatus
from app.database.database import Database
from app.services.publishing_worker import (
    PermanentPublishError,
    PublishingWorker,
    RetryablePublishError,
    UncertainPublishError,
    retry_uncertain_publish_job,
    mark_stale_processing_job_uncertain,
)


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


class FakePublisher:
    def __init__(self, result: int = 777, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls = 0

    async def publish(self, payload):
        self.calls += 1
        if self.error:
            raise self.error
        assert payload.destination_chat_id == -1001234500001
        assert payload.text == "Hello from the queue"
        return self.result


async def create_due_job(database: Database) -> str:
    async with database.session() as session:
        target = TargetChannel(
            telegram_chat_id=-1001234500001,
            title="Private test target",
            posting_permission_status="verified",
        )
        content = Content(title="Test post", caption="Hello from the queue")
        session.add_all([target, content])
        await session.flush()
        job = PublishJob(
            content=content,
            target_channel=target,
            idempotency_key=f"worker-test-{datetime.now(UTC).timestamp()}",
            run_at=datetime.now(UTC) - timedelta(seconds=1),
            max_attempts=3,
        )
        session.add(job)
        await session.commit()
        return job.id


@pytest.mark.asyncio
async def test_worker_persists_success_and_message_id(tmp_path: Path):
    database = Database(make_settings(tmp_path / "worker-success.db"))
    await database.initialize()
    job_id = await create_due_job(database)
    publisher = FakePublisher()
    worker = PublishingWorker(database.session_factory, publisher)

    assert await worker.run_once() is True
    assert publisher.calls == 1
    async with database.session() as session:
        job = await session.get(PublishJob, job_id)
        attempts = list((await session.scalars(
            select(PublishAttempt).where(PublishAttempt.publish_job_id == job_id)
        )).all())
        assert job.status == PublishJobStatus.PUBLISHED.value
        assert job.telegram_message_id == 777
        assert len(attempts) == 1
        assert attempts[0].outcome == "published"
        assert attempts[0].telegram_message_id == 777
    await database.close()


@pytest.mark.asyncio
async def test_worker_retries_only_confirmed_retryable_failure(tmp_path: Path):
    database = Database(make_settings(tmp_path / "worker-retry.db"))
    await database.initialize()
    job_id = await create_due_job(database)
    publisher = FakePublisher(error=RetryablePublishError("Telegram rejected before send"))
    worker = PublishingWorker(
        database.session_factory, publisher, retry_base_seconds=30
    )

    assert await worker.run_once() is True
    async with database.session() as session:
        job = await session.get(PublishJob, job_id)
        attempt = await session.scalar(
            select(PublishAttempt).where(PublishAttempt.publish_job_id == job_id)
        )
        assert job.status == PublishJobStatus.QUEUED.value
        assert job.run_at is not None
        assert attempt.outcome == "retryable_failure"
    await database.close()


@pytest.mark.asyncio
async def test_worker_marks_ambiguous_send_uncertain_and_never_retries(tmp_path: Path):
    database = Database(make_settings(tmp_path / "worker-uncertain.db"))
    await database.initialize()
    job_id = await create_due_job(database)
    publisher = FakePublisher(error=UncertainPublishError("Connection dropped after request"))
    worker = PublishingWorker(database.session_factory, publisher)

    assert await worker.run_once() is True
    assert await worker.run_once() is False
    async with database.session() as session:
        job = await session.get(PublishJob, job_id)
        attempts = list((await session.scalars(
            select(PublishAttempt).where(PublishAttempt.publish_job_id == job_id)
        )).all())
        assert job.status == PublishJobStatus.UNCERTAIN.value
        assert len(attempts) == 1
        assert attempts[0].outcome == "uncertain"

        # Requeue is a deliberate operator action, never an automatic retry.
        admin = Admin(telegram_user_id=42)
        session.add(admin)
        await session.flush()
        await retry_uncertain_publish_job(session, job_id, operator_admin_id=admin.id)
        await session.commit()
        assert job.status == PublishJobStatus.QUEUED.value
    await database.close()


@pytest.mark.asyncio
async def test_worker_does_not_send_without_verified_channel_permission(tmp_path: Path):
    database = Database(make_settings(tmp_path / "worker-permission.db"))
    await database.initialize()
    job_id = await create_due_job(database)
    async with database.session() as session:
        target = await session.scalar(select(TargetChannel))
        target.posting_permission_status = "unknown"
        await session.commit()

    publisher = FakePublisher()
    worker = PublishingWorker(database.session_factory, publisher)
    assert await worker.run_once() is True
    assert publisher.calls == 0
    async with database.session() as session:
        job = await session.get(PublishJob, job_id)
        assert job.status == PublishJobStatus.FAILED.value
    await database.close()



@pytest.mark.asyncio
async def test_stale_processing_job_requires_operator_recovery(tmp_path: Path):
    database = Database(make_settings(tmp_path / "worker-stale.db"))
    await database.initialize()
    job_id = await create_due_job(database)
    async with database.session() as session:
        admin = Admin(telegram_user_id=42)
        session.add(admin)
        job = await session.get(PublishJob, job_id)
        job.status = PublishJobStatus.PROCESSING.value
        job.attempts = 1
        job.locked_at = datetime.now(UTC) - timedelta(minutes=20)
        attempt = PublishAttempt(
            publish_job_id=job_id,
            attempt_number=1,
            outcome="processing",
        )
        session.add(attempt)
        await session.flush()
        await mark_stale_processing_job_uncertain(
            session,
            job_id,
            operator_admin_id=admin.id,
            stale_after=timedelta(minutes=10),
        )
        await session.commit()
        assert job.status == PublishJobStatus.UNCERTAIN.value
        assert attempt.outcome == "uncertain"
    await database.close()
