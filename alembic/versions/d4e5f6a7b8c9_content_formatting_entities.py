"""Preserve Telegram formatting entity metadata on imported content.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contents", sa.Column("formatting_entities", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contents", "formatting_entities")
