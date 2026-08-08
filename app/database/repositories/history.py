"""Repository boundary for duplicate-safe repost history operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import RepostHistory


class HistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def already_processed(
        self, source_channel_id: int, target_channel_id: int, source_message_id: int
    ) -> bool:
        statement = select(RepostHistory.id).where(
            RepostHistory.source_channel_id == source_channel_id,
            RepostHistory.target_channel_id == target_channel_id,
            RepostHistory.source_message_id == source_message_id,
        )
        return await self.session.scalar(statement) is not None