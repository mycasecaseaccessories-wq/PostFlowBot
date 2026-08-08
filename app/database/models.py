"""SQLAlchemy models for Phase 0 and future reposting phases."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    repost_rules: Mapped[list["RepostRule"]] = relationship(
        back_populates="target_channel", cascade="all, delete-orphan"
    )
    history: Mapped[list["RepostHistory"]] = relationship(
        back_populates="target_channel", cascade="all, delete-orphan"
    )


class RepostRule(TimestampMixin, Base):
    __tablename__ = "repost_rules"

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
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    source_channel: Mapped[SourceChannel] = relationship(back_populates="history")
    target_channel: Mapped[TargetChannel] = relationship(back_populates="history")


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )