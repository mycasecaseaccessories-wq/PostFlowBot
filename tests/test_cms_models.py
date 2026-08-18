from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config.settings import load_settings
from app.database.cms_models import (
    Category,
    Collection,
    Content,
    ContentMedia,
    ContentTag,
    Media,
    Tag,
)
from app.database.database import Database
from app.database.models import Base


def environment(database_url: str) -> dict[str, str]:
    return {
        "BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
        "API_ID": "12345",
        "API_HASH": "0123456789abcdef0123456789abcdef",
        "TELEGRAM_SESSION": "test-session",
        "ADMIN_USER_IDS": "42",
        "DATABASE_URL": database_url,
    }


@pytest.mark.asyncio
async def test_cms_models_import_and_uuid_identifiers(tmp_path: Path) -> None:
    assert {"categories", "collections", "contents", "media", "tags"} <= set(
        Base.metadata.tables
    )
    database = Database(
        load_settings(environment(f"sqlite+aiosqlite:///{tmp_path / 'cms.db'}"), dotenv_path=None)
    )
    await database.initialize()
    async with database.session() as session:
        category = Category(name="News", slug="news")
        session.add(category)
        await session.commit()
        assert category.id is not None
        UUID(category.id)
    await database.close()


@pytest.mark.asyncio
async def test_category_collection_and_content_relationships(tmp_path: Path) -> None:
    database = Database(
        load_settings(environment(f"sqlite+aiosqlite:///{tmp_path / 'relations.db'}"), dotenv_path=None)
    )
    await database.initialize()
    async with database.session() as session:
        category = Category(name="News", slug="news")
        collection = Collection(name="Daily", slug="daily", category=category)
        categorized = Content(title="Categorized", category=category, collection=collection)
        draft = Content(title="Draft without taxonomy")
        session.add_all([collection, categorized, draft])
        await session.commit()
        assert categorized.category_id == category.id
        assert categorized.collection_id == collection.id
        assert draft.category_id is None
        assert draft.collection_id is None
    await database.close()


@pytest.mark.asyncio
async def test_collection_requires_existing_category(tmp_path: Path) -> None:
    database = Database(
        load_settings(environment(f"sqlite+aiosqlite:///{tmp_path / 'fk.db'}"), dotenv_path=None)
    )
    await database.initialize()
    async with database.session() as session:
        session.add(
            Collection(
                category_id="00000000-0000-0000-0000-000000000000",
                name="Invalid",
                slug="invalid",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    await database.close()


@pytest.mark.asyncio
async def test_tag_slug_and_media_unique_identifiers(tmp_path: Path) -> None:
    database = Database(
        load_settings(environment(f"sqlite+aiosqlite:///{tmp_path / 'unique.db'}"), dotenv_path=None)
    )
    await database.initialize()
    async with database.session() as session:
        session.add_all([Tag(name="One", slug="one"), Tag(name="Duplicate", slug="one")])
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        session.add_all(
            [
                Media(
                    telegram_file_id="file-1",
                    telegram_file_unique_id="unique-1",
                    media_type="photo",
                ),
                Media(
                    telegram_file_id="file-2",
                    telegram_file_unique_id="unique-1",
                    media_type="photo",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    await database.close()


@pytest.mark.asyncio
async def test_content_media_and_content_tag_associations(tmp_path: Path) -> None:
    database = Database(
        load_settings(environment(f"sqlite+aiosqlite:///{tmp_path / 'associations.db'}"), dotenv_path=None)
    )
    await database.initialize()
    async with database.session() as session:
        content = Content(title="Album")
        media = Media(
            telegram_file_id="album-file",
            telegram_file_unique_id="album-unique",
            media_type="photo",
        )
        tag = Tag(name="Travel", slug="travel")
        session.add_all([content, media, tag])
        await session.flush()
        session.add(ContentMedia(content=content, media=media, display_order=3, album_group_key="album-1"))
        session.add(ContentTag(content=content, tag=tag))
        await session.commit()

        saved_media = await session.scalar(
            select(ContentMedia).where(ContentMedia.content_id == content.id)
        )
        assert saved_media is not None
        assert saved_media.display_order == 3
        assert saved_media.album_group_key == "album-1"
        content_id = content.id
        media_id = media.id
        tag_id = tag.id

        session.add(ContentTag(content_id=content_id, tag_id=tag_id))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        session.expunge_all()

        session.add(ContentMedia(content_id=content_id, media_id=media_id, display_order=4))
        with pytest.raises(IntegrityError):
            await session.commit()
    await database.close()


@pytest.mark.asyncio
async def test_collection_slug_is_unique_within_category(tmp_path: Path) -> None:
    database = Database(
        load_settings(environment(f"sqlite+aiosqlite:///{tmp_path / 'collection_slug.db'}"), dotenv_path=None)
    )
    await database.initialize()
    async with database.session() as session:
        category_one = Category(name="One", slug="one")
        category_two = Category(name="Two", slug="two")
        session.add_all([category_one, category_two])
        await session.flush()
        session.add_all(
            [
                Collection(name="Promotions", slug="promotions", category_id=category_one.id),
                Collection(name="Promotions", slug="promotions", category_id=category_two.id),
            ]
        )
        await session.commit()
        session.add(Collection(name="Duplicate", slug="promotions", category_id=category_one.id))
        with pytest.raises(IntegrityError):
            await session.commit()
    await database.close()


@pytest.mark.asyncio
async def test_content_defaults_and_nonnegative_checks(tmp_path: Path) -> None:
    database = Database(
        load_settings(environment(f"sqlite+aiosqlite:///{tmp_path / 'checks.db'}"), dotenv_path=None)
    )
    await database.initialize()
    async with database.session() as session:
        content = Content(title="Draft")
        session.add(content)
        await session.flush()
        assert content.status == "draft"
        assert content.content_type == "text"
        session.add(Content(title="Invalid priority", priority=-1))
        with pytest.raises(IntegrityError):
            await session.commit()
    await database.close()


@pytest.mark.asyncio
async def test_category_slug_is_unique(tmp_path: Path) -> None:
    database = Database(
        load_settings(environment(f"sqlite+aiosqlite:///{tmp_path / 'category_slug.db'}"), dotenv_path=None)
    )
    await database.initialize()
    async with database.session() as session:
        session.add_all(
            [
                Category(name="First", slug="same-slug"),
                Category(name="Second", slug="same-slug"),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    await database.close()
