"""Source-to-target routing management service."""

from __future__ import annotations

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logger import get_logger
from app.database.models import RepostRule
from app.database.repositories.routing import RoutingRepository
from app.services.channel_service import SourceChannelService, TargetChannelService

logger = get_logger(__name__)


class RoutingService:
    def __init__(
        self,
        repository: RoutingRepository,
        source_service: SourceChannelService,
        target_service: TargetChannelService,
    ) -> None:
        self.repository = repository
        self.source_service = source_service
        self.target_service = target_service

    async def get_route(self, route_id: int) -> RepostRule:
        route = await self.repository.get(route_id)
        if route is None:
            raise NotFoundError("Routing rule was not found.")
        return route

    async def list_routes(self, limit: int = 20, offset: int = 0) -> list[RepostRule]:
        return await self.repository.list(limit, offset)

    async def validate_route(self, source_id: int, target_id: int) -> None:
        source = await self.source_service.get_source(source_id)
        target = await self.target_service.get_target(target_id)
        if source.telegram_chat_id == target.telegram_chat_id:
            raise ConflictError("A source channel cannot route to itself.")
        if not source.is_active:
            raise ConflictError("Enable the source channel before creating a route.")
        if not target.is_active:
            raise ConflictError("Enable the target channel before creating a route.")
        if target.posting_permission_status != "verified":
            raise ConflictError("Verify target posting permission with /target_check before creating or enabling a route.")

    async def create_route(self, source_id: int, target_id: int, admin_id: int) -> RepostRule:
        await self.validate_route(source_id, target_id)
        existing = await self.repository.find_pair(source_id, target_id)
        values = {
            "source_channel_id": source_id,
            "target_channel_id": target_id,
            "is_active": True,
            "remove_usernames": False,
            "remove_links": False,
            "remove_keywords": None,
            "delay_seconds": 0,
        }
        if existing is not None:
            route = await self.repository.save(values, existing.id)
            logger.info("Admin %s re-enabled route %s", admin_id, route.id)
            return route
        try:
            route = await self.repository.save(values)
        except Exception as exc:
            raise ConflictError("This source-to-target route already exists.") from exc
        logger.info("Admin %s created route %s", admin_id, route.id)
        return route

    async def enable_route(self, route_id: int, admin_id: int) -> RepostRule:
        existing = await self.get_route(route_id)
        await self.validate_route(existing.source_channel_id, existing.target_channel_id)
        route = await self.repository.save({"is_active": True}, route_id)
        logger.info("Admin %s enabled route %s", admin_id, route_id)
        return route

    async def disable_route(self, route_id: int, admin_id: int) -> RepostRule:
        await self.get_route(route_id)
        route = await self.repository.save({"is_active": False}, route_id)
        logger.info("Admin %s disabled route %s", admin_id, route_id)
        return route

    async def remove_route(self, route_id: int, admin_id: int) -> RepostRule:
        route = await self.disable_route(route_id, admin_id)
        logger.info("Admin %s removed route %s", admin_id, route_id)
        return route