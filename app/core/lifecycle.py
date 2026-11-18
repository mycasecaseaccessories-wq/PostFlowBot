"""Application startup and graceful shutdown orchestration."""

from __future__ import annotations

import asyncio
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.bot import AdminBotService
from app.config.settings import Settings
from app.database.database import Database
from app.database.repositories.channels import ChannelRepository
from app.database.repositories.routing import RoutingRepository
from app.services.channel_service import SourceChannelService, TargetChannelService
from app.services.routing_service import RoutingService
from app.services.message_intake import MessageIntakeService
from app.services.media_storage import LocalMediaStorage
from app.services.channel_permission import ChannelPermissionService
from app.telegram.client import TelethonClientService
from app.telegram.listener import MessageListenerService
from app.telegram.resolver import ChannelResolver

from .logger import get_logger
from .status import StatusService

logger = get_logger(__name__)


class Application:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.status_service = StatusService()
        self.database = Database(settings)
        self.telethon = TelethonClientService(settings)
        self.channel_repository = ChannelRepository(self.database.session_factory)
        self.routing_repository = RoutingRepository(self.database.session_factory)
        self.channel_resolver = ChannelResolver(self.telethon)
        self.source_service = SourceChannelService(
            self.channel_repository,
            self.channel_resolver,
            self.routing_repository,
        )
        self.target_service = TargetChannelService(
            self.channel_repository,
            self.channel_resolver,
            self.routing_repository,
        )
        self.routing_service = RoutingService(
            self.routing_repository,
            self.source_service,
            self.target_service,
        )
        self.media_storage = LocalMediaStorage(
            settings.media_storage_dir, max_bytes=settings.media_max_bytes
        )
        self.message_intake = MessageIntakeService(
            self.database.session_factory, self.media_storage,
            media_retry_max_attempts=settings.media_retry_max_attempts,
        )
        self.permission_service = ChannelPermissionService(self.database.session_factory, self.telethon)
        self.listener = MessageListenerService(
            self.telethon.get_client(), self.status_service, self.message_intake
        )
        self.bot = AdminBotService(
            settings,
            self.status_service,
            self.source_service,
            self.target_service,
            self.routing_service,
            self.permission_service,
            self.message_intake,
        )
        self.scheduler = AsyncIOScheduler(timezone=settings.timezone)
        self._shutdown_event = asyncio.Event()
        self._started = False
        self._shutdown_complete = True

    async def run(self) -> None:
        self._install_signal_handlers()
        bot_task: asyncio.Task[None] | None = None
        try:
            await self.startup()
            bot_task = asyncio.create_task(self._run_bot(), name="admin-bot-polling")
            await self._shutdown_event.wait()
        finally:
            if bot_task is not None:
                bot_task.cancel()
                await asyncio.gather(bot_task, return_exceptions=True)
            await self.shutdown()

    async def startup(self) -> None:
        logger.info("Application startup sequence beginning")
        self._shutdown_complete = False
        try:
            await self.database.initialize()
            self.status_service.database_connected = True
            await self.telethon.connect()
            self.status_service.telethon_connected = self.telethon.is_connected()
            self.status_service.telethon_authorized = self.telethon.is_authorized()
            await self.listener.start()
            if self.telethon.is_authorized():
                self.scheduler.add_job(
                    self.message_intake.retry_pending_media,
                    "interval",
                    minutes=self.settings.media_retry_interval_minutes,
                    kwargs={"client": self.telethon.get_client(), "limit": 20},
                    id="pending-media-recovery",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )
                if not self.scheduler.running:
                    self.scheduler.start()
            self._started = True
            logger.info("Application startup sequence complete")
        except Exception:
            logger.exception("Application startup failed")
            await self.shutdown()
            raise

    async def shutdown(self) -> None:
        if self._shutdown_complete:
            return
        logger.info("Application shutdown sequence beginning")
        await self.listener.stop()
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await self.bot.stop()
        await self.telethon.disconnect()
        await self.database.close()
        self.status_service.database_connected = False
        self._started = False
        self._shutdown_complete = True
        logger.info("Application shutdown sequence complete")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    async def _run_bot(self) -> None:
        try:
            await self.bot.start_polling()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Admin bot polling failed")
            self.request_shutdown()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, self.request_shutdown)
            except (NotImplementedError, RuntimeError):
                logger.debug("Signal handlers unavailable for %s", signum.name)