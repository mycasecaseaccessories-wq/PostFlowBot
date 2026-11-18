"""SQLAlchemy models for the PostFlow foundation and channel management."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )


class Admin(TimestampMixin, Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SourceChannel(TimestampMixin, Base):
    __tablename__ = "source_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel_type: Mapped[str] = mapped_column(String(32), default="channel", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    repost_rules: Mapped[list["RepostRule"]] = relationship(
        back_populates="source_channel", cascade="all, delete-orphan"
    )
    history: Mapped[list["RepostHistory"]] = relationship(
        back_populates="source_channel", cascade="all, delete-orphan"
    )


class TargetChannel(TimestampMixin, Base):
    __tablename__ = "target_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel_type: Mapped[str] = mapped_column(String(32), default="channel", nullable=False)
    publishing_permission_confirmed: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    posting_permission_status: Mapped[str] = mapped_column(
        String(32), default="unknown", nullable=False
    )
    permission_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    permission_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    repost_rules: Mapped[list["RepostRule"]] = relationship(
        back_populates="target_channel", cascade="all, delete-orphan"
    )
    history: Mapped[list["RepostHistory"]] = relationship(
        back_populates="target_channel", cascade="all, delete-orphan"
    )


class RepostRule(TimestampMixin, Base):
    __tablename__ = "repost_rules"
    __table_args__ = (
        UniqueConstraint(
            "source_channel_id",
            "target_channel_id",
            name="uq_repost_rule_source_target",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_channel_id: Mapped[int] = mapped_column(
        ForeignKey("source_channels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_channel_id: Mapped[int] = mapped_column(
        ForeignKey("target_channels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    remove_usernames: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remove_links: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remove_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_channel: Mapped[SourceChannel] = relationship(back_populates="repost_rules")
    target_channel: Mapped[TargetChannel] = relationship(back_populates="repost_rules")


class RepostHistory(Base):
    __tablename__ = "repost_history"
    __table_args__ = (
        UniqueConstraint(
            "source_channel_id",
            "target_channel_id",
            "source_message_id",
            name="uq_repost_source_target_message",
        ),
        Index("ix_repost_history_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_channel_id: Mapped[int] = mapped_column(
        ForeignKey("source_channels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_channel_id: Mapped[int] = mapped_column(
        ForeignKey("target_channels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    source_channel: Mapped[SourceChannel] = relationship(back_populates="history")
    target_channel: Mapped[TargetChannel] = relationship(back_populates="history")


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )