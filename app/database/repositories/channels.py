"""Repositories for source and target channel records."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import SourceChannel, TargetChannel


class ChannelRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_source(self, channel_id: int) -> SourceChannel | None:
        async with self.session_factory() as session:
            return await session.get(SourceChannel, channel_id)

    async def list_sources(self, limit: int = 20, offset: int = 0) -> list[SourceChannel]:
        async with self.session_factory() as session:
            result = await session.scalars(
                select(SourceChannel)
                .order_by(SourceChannel.title, SourceChannel.id)
                .limit(limit)
                .offset(offset)
            )
            return list(result)

    async def get_source_by_chat_id(self, chat_id: int) -> SourceChannel | None:
        async with self.session_factory() as session:
            return await session.scalar(
                select(SourceChannel).where(SourceChannel.telegram_chat_id == chat_id)
            )

    async def save_source(self, values: dict[str, object], channel_id: int | None = None) -> SourceChannel:
        async with self.session_factory() as session:
            channel = await session.get(SourceChannel, channel_id) if channel_id else None
            if channel is None:
                channel = SourceChannel(**values)
                session.add(channel)
            else:
                for key, value in values.items():
                    setattr(channel, key, value)
            await session.commit()
            await session.refresh(channel)
            return channel

    async def get_target(self, channel_id: int) -> TargetChannel | None:
        async with self.session_factory() as session:
            return await session.get(TargetChannel, channel_id)

    async def list_targets(self, limit: int = 20, offset: int = 0) -> list[TargetChannel]:
        async with self.session_factory() as session:
            result = await session.scalars(
                select(TargetChannel)
                .order_by(TargetChannel.title, TargetChannel.id)
                .limit(limit)
                .offset(offset)
            )
            return list(result)

    async def get_target_by_chat_id(self, chat_id: int) -> TargetChannel | None:
        async with self.session_factory() as session:
            return await session.scalar(
                select(TargetChannel).where(TargetChannel.telegram_chat_id == chat_id)
            )

    async def save_target(self, values: dict[str, object], channel_id: int | None = None) -> TargetChannel:
        async with self.session_factory() as session:
            channel = await session.get(TargetChannel, channel_id) if channel_id else None
            if channel is None:
                channel = TargetChannel(**values)
                session.add(channel)
            else:
                for key, value in values.items():
                    setattr(channel, key, value)
            await session.commit()
            await session.refresh(channel)
            return channel