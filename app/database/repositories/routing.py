"""Repository for source-to-target routing rules."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from app.database.models import RepostRule


class RoutingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get(self, route_id: int) -> RepostRule | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(RepostRule)
                .options(joinedload(RepostRule.source_channel), joinedload(RepostRule.target_channel))
                .where(RepostRule.id == route_id)
            )
            return result.scalar_one_or_none()

    async def list(self, limit: int = 20, offset: int = 0) -> list[RepostRule]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(RepostRule)
                .options(joinedload(RepostRule.source_channel), joinedload(RepostRule.target_channel))
                .order_by(RepostRule.id)
                .limit(limit)
                .offset(offset)
            )
            return list(result.unique().scalars())

    async def find_pair(self, source_id: int, target_id: int) -> RepostRule | None:
        async with self.session_factory() as session:
            return await session.scalar(
                select(RepostRule).where(
                    RepostRule.source_channel_id == source_id,
                    RepostRule.target_channel_id == target_id,
                )
            )

    async def save(self, values: dict[str, object], route_id: int | None = None) -> RepostRule:
        async with self.session_factory() as session:
            route = await session.get(RepostRule, route_id) if route_id else None
            if route is None:
                route = RepostRule(**values)
                session.add(route)
            else:
                for key, value in values.items():
                    setattr(route, key, value)
            await session.commit()
            await session.refresh(route)
            return route

    async def disable_for_source(self, source_id: int) -> None:
        async with self.session_factory() as session:
            routes = list(
                await session.scalars(
                    select(RepostRule).where(RepostRule.source_channel_id == source_id)
                )
            )
            for route in routes:
                route.is_active = False
            await session.commit()

    async def disable_for_target(self, target_id: int) -> None:
        async with self.session_factory() as session:
            routes = list(
                await session.scalars(
                    select(RepostRule).where(RepostRule.target_channel_id == target_id)
                )
            )
            for route in routes:
                route.is_active = False
            await session.commit()