"""Source and target channel management services."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logger import get_logger
from app.database.models import SourceChannel, TargetChannel
from app.database.repositories.channels import ChannelRepository
from app.database.repositories.routing import RoutingRepository
from app.telegram.resolver import ChannelResolver, ResolvedChannel

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ChannelOperationResult:
    channel: SourceChannel | TargetChannel
    reactivated: bool = False


class SourceChannelService:
    def __init__(
        self,
        repository: ChannelRepository,
        resolver: ChannelResolver,
        routing_repository: RoutingRepository,
    ) -> None:
        self.repository = repository
        self.resolver = resolver
        self.routing_repository = routing_repository

    async def resolve(self, value: str) -> ResolvedChannel:
        return await self.resolver.resolve(value)

    async def get_source(self, source_id: int) -> SourceChannel:
        source = await self.repository.get_source(source_id)
        if source is None:
            raise NotFoundError("Source channel was not found.")
        return source

    async def list_sources(self, limit: int = 20, offset: int = 0) -> list[SourceChannel]:
        return await self.repository.list_sources(limit, offset)

    async def add_source(self, resolved: ResolvedChannel, admin_id: int) -> ChannelOperationResult:
        existing = await self.repository.get_source_by_chat_id(resolved.chat_id)
        values = {
            "telegram_chat_id": resolved.chat_id,
            "username": resolved.username,
            "title": resolved.title,
            "channel_type": resolved.channel_type,
            "is_active": True,
        }
        if existing is not None:
            source = await self.repository.save_source(values, existing.id)
            logger.info("Admin %s added or re-enabled source channel %s", admin_id, source.id)
            return ChannelOperationResult(source, reactivated=True)
        try:
            source = await self.repository.save_source(values)
        except Exception as exc:
            raise ConflictError("This source channel is already registered.") from exc
        logger.info("Admin %s added source channel %s", admin_id, source.id)
        return ChannelOperationResult(source)

    async def enable_source(self, source_id: int, admin_id: int) -> SourceChannel:
        source = await self.get_source(source_id)
        source = await self.repository.save_source({"is_active": True}, source.id)
        logger.info("Admin %s enabled source channel %s", admin_id, source_id)
        return source

    async def disable_source(self, source_id: int, admin_id: int) -> SourceChannel:
        source = await self.get_source(source_id)
        source = await self.repository.save_source({"is_active": False}, source.id)
        logger.info("Admin %s disabled source channel %s", admin_id, source_id)
        return source

    async def remove_source(self, source_id: int, admin_id: int) -> SourceChannel:
        source = await self.disable_source(source_id, admin_id)
        await self.routing_repository.disable_for_source(source_id)
        logger.info("Admin %s removed source channel %s", admin_id, source_id)
        return source

    async def refresh_source(self, source_id: int, admin_id: int) -> SourceChannel:
        source = await self.get_source(source_id)
        resolved = await self.resolver.resolve(source.username or str(source.telegram_chat_id))
        refreshed = await self.repository.save_source(
            {
                "telegram_chat_id": resolved.chat_id,
                "username": resolved.username,
                "title": resolved.title,
                "channel_type": resolved.channel_type,
            },
            source.id,
        )
        logger.info("Admin %s refreshed source channel %s", admin_id, source_id)
        return refreshed


class TargetChannelService:
    def __init__(
        self,
        repository: ChannelRepository,
        resolver: ChannelResolver,
        routing_repository: RoutingRepository,
    ) -> None:
        self.repository = repository
        self.resolver = resolver
        self.routing_repository = routing_repository

    async def resolve(self, value: str) -> ResolvedChannel:
        return await self.resolver.resolve(value, target=True)

    async def get_target(self, target_id: int) -> TargetChannel:
        target = await self.repository.get_target(target_id)
        if target is None:
            raise NotFoundError("Target channel was not found.")
        return target

    async def list_targets(self, limit: int = 20, offset: int = 0) -> list[TargetChannel]:
        return await self.repository.list_targets(limit, offset)

    async def add_target(self, resolved: ResolvedChannel, admin_id: int) -> ChannelOperationResult:
        existing = await self.repository.get_target_by_chat_id(resolved.chat_id)
        values = {
            "telegram_chat_id": resolved.chat_id,
            "username": resolved.username,
            "title": resolved.title,
            "channel_type": resolved.channel_type,
            "publishing_permission_confirmed": None,
            "posting_permission_status": "unknown",
            "permission_checked_at": None,
            "permission_error": None,
            "is_active": True,
        }
        if existing is not None:
            target = await self.repository.save_target(values, existing.id)
            logger.info("Admin %s added or re-enabled target channel %s", admin_id, target.id)
            return ChannelOperationResult(target, reactivated=True)
        try:
            target = await self.repository.save_target(values)
        except Exception as exc:
            raise ConflictError("This target channel is already registered.") from exc
        logger.info("Admin %s added target channel %s", admin_id, target.id)
        return ChannelOperationResult(target)

    async def enable_target(self, target_id: int, admin_id: int) -> TargetChannel:
        await self.get_target(target_id)
        target = await self.repository.save_target({
            "is_active": True,
            "publishing_permission_confirmed": None,
            "posting_permission_status": "unknown",
            "permission_checked_at": None,
            "permission_error": None,
        }, target_id)
        logger.info("Admin %s enabled target channel %s", admin_id, target_id)
        return target

    async def disable_target(self, target_id: int, admin_id: int) -> TargetChannel:
        await self.get_target(target_id)
        target = await self.repository.save_target({"is_active": False}, target_id)
        logger.info("Admin %s disabled target channel %s", admin_id, target_id)
        return target

    async def remove_target(self, target_id: int, admin_id: int) -> TargetChannel:
        target = await self.disable_target(target_id, admin_id)
        await self.routing_repository.disable_for_target(target_id)
        logger.info("Admin %s removed target channel %s", admin_id, target_id)
        return target

    async def refresh_target(self, target_id: int, admin_id: int) -> TargetChannel:
        target = await self.get_target(target_id)
        resolved = await self.resolver.resolve(
            target.username or str(target.telegram_chat_id), target=True
        )
        refreshed = await self.repository.save_target(
            {
                "telegram_chat_id": resolved.chat_id,
                "username": resolved.username,
                "title": resolved.title,
                "channel_type": resolved.channel_type,
                "publishing_permission_confirmed": None,
                "posting_permission_status": "unknown",
                "permission_checked_at": None,
                "permission_error": "Target details refreshed; run /target_check to verify current posting rights.",
            },
            target.id,
        )
        logger.info("Admin %s refreshed target channel %s", admin_id, target_id)
        return refreshed