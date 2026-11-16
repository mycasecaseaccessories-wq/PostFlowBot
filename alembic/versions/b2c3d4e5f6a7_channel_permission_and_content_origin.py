"""Record channel posting permission checks and content source origins.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "target_channels",
        sa.Column("posting_permission_status", sa.String(32), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "target_channels",
        sa.Column("permission_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "target_channels",
        sa.Column("permission_error", sa.Text(), nullable=True),
    )

    op.add_column(
        "contents",
        sa.Column("origin", sa.String(32), nullable=False, server_default="manual"),
    )
    op.add_column(
        "contents",
        sa.Column("source_channel_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "contents",
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_contents_source_channel_id_source_channels",
        "contents",
        "source_channels",
        ["source_channel_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_contents_source_message",
        "contents",
        ["source_channel_id", "source_message_id"],
    )
    op.create_index(
        "ix_contents_source_origin",
        "contents",
        ["origin", "source_channel_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_contents_source_origin", table_name="contents")
    op.drop_constraint("uq_contents_source_message", "contents", type_="unique")
    op.drop_constraint(
        "fk_contents_source_channel_id_source_channels",
        "contents",
        type_="foreignkey",
    )
    op.drop_column("contents", "source_message_id")
    op.drop_column("contents", "source_channel_id")
    op.drop_column("contents", "origin")
    op.drop_column("target_channels", "permission_error")
    op.drop_column("target_channels", "permission_checked_at")
    op.drop_column("target_channels", "posting_permission_status")
