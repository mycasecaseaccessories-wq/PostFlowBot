"""Phase 1 workspace, approvals, schedules, publishing queue, and audit trail.

Revision ID: a1b2c3d4e5f6
Revises: f344c4272a80
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f344c4272a80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False, unique=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admins.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_workspaces_name_nonempty"),
    )
    op.create_index("ix_workspaces_active", "workspaces", ["is_active"])

    op.create_table(
        "workspace_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(24), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "admin_id", name="uq_workspace_members_workspace_admin"),
    )
    op.create_index("ix_workspace_members_admin", "workspace_members", ["admin_id"])

    op.create_table(
        "content_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("content_id", sa.String(36), sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("admins.id", ondelete="SET NULL")),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("admins.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("review_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_content_approvals_status_created", "content_approvals", ["status", "created_at"])
    op.create_index("ix_content_approvals_content", "content_approvals", ["content_id"])

    op.create_table(
        "schedules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("content_id", sa.String(36), sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_channel_id", sa.Integer(), sa.ForeignKey("target_channels.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admins.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("interval_seconds", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("interval_seconds IS NULL OR interval_seconds > 0", name="ck_schedules_interval_positive"),
    )
    op.create_index("ix_schedules_due", "schedules", ["status", "scheduled_at"])
    op.create_index("ix_schedules_content", "schedules", ["content_id"])

    op.create_table(
        "publish_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schedule_id", sa.String(36), sa.ForeignKey("schedules.id", ondelete="SET NULL")),
        sa.Column("content_id", sa.String(36), sa.ForeignKey("contents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_channel_id", sa.Integer(), sa.ForeignKey("target_channels.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("telegram_message_id", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_publish_jobs_idempotency_key"),
    )
    op.create_index("ix_publish_jobs_claim", "publish_jobs", ["status", "run_at"])
    op.create_index("ix_publish_jobs_schedule", "publish_jobs", ["schedule_id"])

    op.create_table(
        "publish_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("publish_job_id", sa.String(36), sa.ForeignKey("publish_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("telegram_message_id", sa.BigInteger()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("attempt_number > 0", name="ck_publish_attempts_number_positive"),
        sa.UniqueConstraint("publish_job_id", "attempt_number", name="uq_publish_attempts_job_number"),
    )
    op.create_index("ix_publish_attempts_started", "publish_attempts", ["started_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_admin_id", sa.Integer(), sa.ForeignKey("admins.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(100)),
        sa.Column("details_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])
    op.create_index("ix_audit_events_created", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created", table_name="audit_events")
    op.drop_index("ix_audit_events_entity", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_publish_attempts_started", table_name="publish_attempts")
    op.drop_table("publish_attempts")
    op.drop_index("ix_publish_jobs_schedule", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_claim", table_name="publish_jobs")
    op.drop_table("publish_jobs")
    op.drop_index("ix_schedules_content", table_name="schedules")
    op.drop_index("ix_schedules_due", table_name="schedules")
    op.drop_table("schedules")
    op.drop_index("ix_content_approvals_content", table_name="content_approvals")
    op.drop_index("ix_content_approvals_status_created", table_name="content_approvals")
    op.drop_table("content_approvals")
    op.drop_index("ix_workspace_members_admin", table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_index("ix_workspaces_active", table_name="workspaces")
    op.drop_table("workspaces")
