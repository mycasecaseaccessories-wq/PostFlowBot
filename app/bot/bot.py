"""aiogram admin bot lifecycle."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.token import TokenValidationError, validate_token

from app.config.settings import ConfigurationError, Settings
from app.core.logger import get_logger
from app.core.status import StatusService
from app.services.channel_service import SourceChannelService, TargetChannelService
from app.services.routing_service import RoutingService

from .auth import AdminAccessMiddleware
from .handlers import build_router

logger = get_logger(__name__)


class AdminBotService:
    def __init__(
        self,
        settings: Settings,
        status_service: StatusService,
        source_service: SourceChannelService,
        target_service: TargetChannelService,
        routing_service: RoutingService,
    ) -> None:
        try:
            validate_token(settings.bot_token)
        except TokenValidationError as exc:
            raise ConfigurationError(
                "Environment variable BOT_TOKEN has an invalid format."
            ) from exc
        self.bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.dispatcher = Dispatcher()
        self.dispatcher.message.outer_middleware(
            AdminAccessMiddleware(settings.admin_user_ids)
        )
        self.dispatcher.callback_query.outer_middleware(
            AdminAccessMiddleware(settings.admin_user_ids)
        )
        self.dispatcher.include_router(
            build_router(status_service, source_service, target_service, routing_service)
        )
        self.status_service = status_service
        self.running = False

    async def start_polling(self) -> None:
        self.running = True
        self.status_service.admin_bot_online = True
        logger.info("Admin bot polling started")
        try:
            await self.dispatcher.start_polling(self.bot)
        finally:
            self.running = False
            self.status_service.admin_bot_online = False

    async def stop(self) -> None:
        if self.running:
            await self.dispatcher.stop_polling()
        await self.bot.session.close()
        self.status_service.admin_bot_online = False
        logger.info("Admin bot stopped")