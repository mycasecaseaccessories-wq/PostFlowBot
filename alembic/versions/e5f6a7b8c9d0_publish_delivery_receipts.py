"""Persist every Telegram message ID returned by a publish attempt.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "publish_delivery_receipts",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("publish_job_id", sa.String(length=36), sa.ForeignKey("publish_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), sa.ForeignKey("publish_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("message_ordinal", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("attempt_id", "message_ordinal", name="uq_publish_receipts_attempt_ordinal"),
        sa.UniqueConstraint("attempt_id", "telegram_message_id", name="uq_publish_receipts_attempt_message"),
    )
    op.create_index(
        "ix_publish_delivery_receipts_job",
        "publish_delivery_receipts",
        ["publish_job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_publish_delivery_receipts_job", table_name="publish_delivery_receipts")
    op.drop_table("publish_delivery_receipts")
