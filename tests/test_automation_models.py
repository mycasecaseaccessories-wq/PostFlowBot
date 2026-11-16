from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers

from app.config.settings import load_settings
from app.database import (
    Admin, ApprovalStatus, AuditEvent, Category, Content, ContentApproval,
    PublishAttempt, PublishJob, PublishJobStatus, Schedule, ScheduleStatus,
    TargetChannel, Workspace, WorkspaceMember,
)
from app.database.database import Database
from app.database.models import Base


def settings_for(path: Path):
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


@pytest.mark.asyncio
async def test_phase_one_tables_are_registered_and_mappers_configure(tmp_path: Path):
    expected = {
        "workspaces", "workspace_members", "content_approvals", "schedules",
        "publish_jobs", "publish_attempts", "audit_events",
    }
    assert expected <= set(Base.metadata.tables)
    configure_mappers()

    database = Database(settings_for(tmp_path / "phase1.db"))
    await database.initialize()
    await database.close()


@pytest.mark.asyncio
async def test_workspace_membership_and_content_approval(tmp_path: Path):
    database = Database(settings_for(tmp_path / "workspace.db"))
    await database.initialize()
    async with database.session() as session:
        admin = Admin(telegram_user_id=42)
        category = Category(name="Updates", slug="updates")
        workspace = Workspace(name="Main Workspace", slug="main")
        content = Content(title="Launch announcement", category=category)
        session.add_all([admin, category, workspace, content])
        await session.flush()
        workspace.created_by = admin.id
        membership = WorkspaceMember(workspace=workspace, admin=admin, role="owner")
        approval = ContentApproval(
            content=content, requested_by=admin.id, status=ApprovalStatus.PENDING.value
        )
        session.add_all([membership, approval])
        await session.commit()
        assert membership.workspace_id == workspace.id
        assert approval.content_id == content.id
        assert approval.status == "pending"
    await database.close()


@pytest.mark.asyncio
async def test_schedule_and_publish_job_idempotency(tmp_path: Path):
    database = Database(settings_for(tmp_path / "queue.db"))
    await database.initialize()
    async with database.session() as session:
        target = TargetChannel(telegram_chat_id=-1001234567890, title="Test channel")
        content = Content(title="Scheduled post")
        session.add_all([target, content])
        await session.flush()
        due = datetime.now(UTC) + timedelta(minutes=10)
        schedule = Schedule(
            content=content, target_channel=target, scheduled_at=due,
            timezone="Asia/Yangon", status=ScheduleStatus.SCHEDULED.value,
        )
        session.add(schedule)
        await session.flush()
        job = PublishJob(
            schedule=schedule, content=content, target_channel=target,
            idempotency_key="schedule-content-target-001", run_at=due,
            status=PublishJobStatus.QUEUED.value,
        )
        session.add(job)
        await session.commit()
        assert job.status == "queued"
        assert job.attempts == 0

        duplicate = PublishJob(
            content=content, target_channel=target,
            idempotency_key="schedule-content-target-001", run_at=due,
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
    await database.close()


@pytest.mark.asyncio
async def test_publish_attempt_history_and_audit_event(tmp_path: Path):
    database = Database(settings_for(tmp_path / "history.db"))
    await database.initialize()
    async with database.session() as session:
        admin = Admin(telegram_user_id=42)
        target = TargetChannel(telegram_chat_id=-1001234567891, title="History channel")
        content = Content(title="Post with attempt")
        session.add_all([admin, target, content])
        await session.flush()
        job = PublishJob(
            content=content, target_channel=target,
            idempotency_key="history-job-1", run_at=datetime.now(UTC),
        )
        session.add(job)
        await session.flush()
        attempt = PublishAttempt(
            job=job, attempt_number=1, outcome="failed",
            error_code="NETWORK", error_message="Temporary network issue",
        )
        audit = AuditEvent(
            actor=admin, action="publish.retry", entity_type="publish_job",
            entity_id=job.id, details_json='{"attempt":1}',
        )
        session.add_all([attempt, audit])
        await session.commit()
        saved = await session.scalar(
            select(PublishAttempt).where(PublishAttempt.publish_job_id == job.id)
        )
        assert saved is not None
        assert saved.outcome == "failed"
        assert audit.actor_admin_id == admin.id
    await database.close()
