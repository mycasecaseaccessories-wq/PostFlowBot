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

    # SQLite cannot ALTER TABLE to add named constraints. Batch mode uses a
    # safe copy-and-recreate strategy on SQLite and ordinary ALTER on PostgreSQL.
    with op.batch_alter_table("contents") as batch_op:
        batch_op.create_foreign_key(
            "fk_contents_source_channel_id_source_channels",
            "source_channels",
            ["source_channel_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_contents_source_message",
            ["source_channel_id", "source_message_id"],
        )

    op.create_index(
        "ix_contents_source_origin",
        "contents",
        ["origin", "source_channel_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_contents_source_origin", table_name="contents")

    with op.batch_alter_table("contents") as batch_op:
        batch_op.drop_constraint("uq_contents_source_message", type_="unique")
        batch_op.drop_constraint(
            "fk_contents_source_channel_id_source_channels",
            type_="foreignkey",
        )
        batch_op.drop_column("source_message_id")
        batch_op.drop_column("source_channel_id")
        batch_op.drop_column("origin")

    with op.batch_alter_table("target_channels") as batch_op:
        batch_op.drop_column("permission_error")
        batch_op.drop_column("permission_checked_at")
        batch_op.drop_column("posting_permission_status")
