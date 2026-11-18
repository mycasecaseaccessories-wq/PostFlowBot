"""Phase 1.2 persistence-only CMS domain models.

New CMS identifiers are canonical UUID strings (36-character text). This is
portable across SQLite and PostgreSQL without requiring a database-specific
UUID extension or a future application rewrite.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import Admin, Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _uuid_string() -> str:
    return str(uuid4())


class ContentType(StrEnum):
    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    ALBUM = "album"
    ANIMATION = "animation"
    AUDIO = "audio"
    VOICE = "voice"
    DOCUMENT = "document"
    POLL = "poll"
    QUIZ = "quiz"


class ContentOrigin(StrEnum):
    MANUAL = "manual"
    AI = "ai"
    CHANNEL_IMPORT = "channel_import"


class ContentStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    READY = "ready"
    ARCHIVED = "archived"
    DELETED = "deleted"


class MediaType(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"
    ANIMATION = "animation"
    AUDIO = "audio"
    VOICE = "voice"
    DOCUMENT = "document"
    THUMBNAIL = "thumbnail"


class RotationMode(StrEnum):
    SEQUENTIAL = "sequential"
    RANDOM = "random"
    SHUFFLE = "shuffle"
    WEIGHTED = "weighted"


class CmsTimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )


class SoftDeleteMixin:
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Category(CmsTimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_categories_name_nonempty"),
        CheckConstraint("display_order >= 0", name="ck_categories_display_order_nonnegative"),
        Index("ix_categories_active_display_order", "is_active", "display_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_string)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(32))
    icon: Mapped[str | None] = mapped_column(String(64))
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    collections: Mapped[list["Collection"]] = relationship(
        back_populates="category", lazy="select"
    )
    contents: Mapped[list["Content"]] = relationship(
        back_populates="category", lazy="select"
    )


class Collection(CmsTimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "collections"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_collections_name_nonempty"),
        CheckConstraint("display_order >= 0", name="ck_collections_display_order_nonnegative"),
        CheckConstraint("priority >= 0", name="ck_collections_priority_nonnegative"),
        UniqueConstraint("category_id", "slug", name="uq_collections_category_slug"),
        Index("ix_collections_category_active", "category_id", "is_active"),
        Index("ix_collections_priority", "priority"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_string)
    category_id: Mapped[str] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rotation_mode: Mapped[str] = mapped_column(
        String(32), default=RotationMode.SEQUENTIAL.value, nullable=False
    )

    category: Mapped[Category] = relationship(back_populates="collections")
    contents: Mapped[list["Content"]] = relationship(
        back_populates="collection", lazy="select"
    )


class Content(CmsTimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "contents"
    __table_args__ = (
        CheckConstraint("priority >= 0", name="ck_contents_priority_nonnegative"),
        UniqueConstraint("source_channel_id", "source_message_id", name="uq_contents_source_message"),
        Index("ix_contents_source_origin", "origin", "source_channel_id"),
        Index("ix_contents_status_type", "status", "content_type"),
        Index("ix_contents_category_collection", "category_id", "collection_id"),
        Index("ix_contents_created_at", "created_at"),
        Index("ix_contents_updated_at", "updated_at"),
        Index("ix_contents_priority", "priority"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_string)
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    collection_id: Mapped[str | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(
        String(32), default=ContentType.TEXT.value, nullable=False
    )
    origin: Mapped[str] = mapped_column(
        String(32), default=ContentOrigin.MANUAL.value, nullable=False
    )
    source_channel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("source_channels.id", ondelete="SET NULL"), nullable=True
    )
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    caption_source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    formatting_entities: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32), default=ContentStatus.DRAFT.value, nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )

    category: Mapped[Category | None] = relationship(back_populates="contents")
    collection: Mapped[Collection | None] = relationship(back_populates="contents")
    creator: Mapped[Admin | None] = relationship(
        foreign_keys=[created_by], lazy="select"
    )
    media_links: Mapped[list["ContentMedia"]] = relationship(
        back_populates="content", lazy="select", cascade="save-update, merge"
    )
    tag_links: Mapped[list["ContentTag"]] = relationship(
        back_populates="content", lazy="select", cascade="save-update, merge"
    )


class Media(CmsTimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "media"
    __table_args__ = (
        CheckConstraint("file_size IS NULL OR file_size >= 0", name="ck_media_file_size_nonnegative"),
        CheckConstraint("width IS NULL OR width >= 0", name="ck_media_width_nonnegative"),
        CheckConstraint("height IS NULL OR height >= 0", name="ck_media_height_nonnegative"),
        CheckConstraint("duration IS NULL OR duration >= 0", name="ck_media_duration_nonnegative"),
        Index("ix_media_type_active", "media_type", "is_active"),
        Index("ix_media_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_string)
    telegram_file_id: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    telegram_file_unique_id: Mapped[str | None] = mapped_column(
        String(512), unique=True, nullable=True
    )
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_file_name: Mapped[str | None] = mapped_column(String(512))
    mime_type: Mapped[str | None] = mapped_column(String(255))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[int | None] = mapped_column(Integer)
    thumbnail_file_id: Mapped[str | None] = mapped_column(String(512))
    storage_backend: Mapped[str | None] = mapped_column(String(32))
    storage_key: Mapped[str | None] = mapped_column(String(1024), unique=True)
    sha256: Mapped[str | None] = mapped_column(String(64))
    stored_size: Mapped[int | None] = mapped_column(BigInteger)
    storage_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    storage_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_error: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )

    content_links: Mapped[list["ContentMedia"]] = relationship(
        back_populates="media", lazy="select", cascade="save-update, merge"
    )
    uploader: Mapped[Admin | None] = relationship(
        foreign_keys=[uploaded_by], lazy="select"
    )


class ContentMedia(Base):
    __tablename__ = "content_media"
    __table_args__ = (
        CheckConstraint("display_order >= 0", name="ck_content_media_display_order_nonnegative"),
        Index("ix_content_media_display_order", "content_id", "display_order"),
        Index("ix_content_media_media_id", "media_id"),
        Index("ix_content_media_source_message", "content_id", "source_message_id"),
    )

    content_id: Mapped[str] = mapped_column(
        ForeignKey("contents.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[str] = mapped_column(
        ForeignKey("media.id", ondelete="RESTRICT"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    album_group_key: Mapped[str | None] = mapped_column(String(128))
    source_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    content: Mapped[Content] = relationship(back_populates="media_links")
    media: Mapped[Media] = relationship(back_populates="content_links")


class Tag(CmsTimestampMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_tags_name_nonempty"),
        Index("ix_tags_active", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_string)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    content_links: Mapped[list["ContentTag"]] = relationship(
        back_populates="tag", lazy="select", cascade="save-update, merge"
    )


class ContentTag(Base):
    __tablename__ = "content_tags"
    __table_args__ = (
        Index("ix_content_tags_tag_content", "tag_id", "content_id"),
    )

    content_id: Mapped[str] = mapped_column(
        ForeignKey("contents.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    content: Mapped[Content] = relationship(back_populates="tag_links")
    tag: Mapped[Tag] = relationship(back_populates="content_links")


__all__ = [
    "Category",
    "Collection",
    "Content",
    "ContentMedia",
    "ContentOrigin",
    "ContentStatus",
    "ContentTag",
    "ContentType",
    "Media",
    "MediaType",
    "RotationMode",
    "Tag",
]
