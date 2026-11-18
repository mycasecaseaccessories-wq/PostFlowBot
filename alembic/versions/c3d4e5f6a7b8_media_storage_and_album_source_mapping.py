"""Add durable media storage metadata and album source message mapping.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media", sa.Column("storage_backend", sa.String(length=32), nullable=True))
    op.add_column("media", sa.Column("storage_key", sa.String(length=1024), nullable=True))
    op.add_column("media", sa.Column("sha256", sa.String(length=64), nullable=True))
    op.add_column("media", sa.Column("stored_size", sa.BigInteger(), nullable=True))
    op.add_column("media", sa.Column("storage_status", sa.String(length=24), nullable=False, server_default="pending"))
    op.add_column("media", sa.Column("storage_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("media", sa.Column("storage_error", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_media_storage_key", "media", ["storage_key"])

    op.add_column(
        "contents",
        sa.Column("caption_source_message_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "content_media",
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_content_media_source_message",
        "content_media",
        ["content_id", "source_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_media_source_message", table_name="content_media")
    op.drop_column("content_media", "source_message_id")
    op.drop_column("contents", "caption_source_message_id")
    op.drop_constraint("uq_media_storage_key", "media", type_="unique")
    op.drop_column("media", "storage_error")
    op.drop_column("media", "storage_attempts")
    op.drop_column("media", "storage_status")
    op.drop_column("media", "stored_size")
    op.drop_column("media", "sha256")
    op.drop_column("media", "storage_key")
    op.drop_column("media", "storage_backend")
