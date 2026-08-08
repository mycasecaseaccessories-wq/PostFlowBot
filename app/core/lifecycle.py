"""Application startup and graceful shutdown orchestration."""

from __future__ import annotations

import asyncio
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.bot import AdminBotService
from app.config.settings import Settings
from app.database.database import Database
from app.telegram.client import TelethonClientService
from app.telegram.listener import MessageListenerService

from .logger import get_logger
from .status import StatusService

logger = get_logger(__name__)


class Application:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.status_service = StatusService()
        self.database = Database(settings)
        self.telethon = TelethonClientService(settings)
        self.listener = MessageListenerService(
            self.telethon.get_client(), self.status_service
        )
        self.bot = AdminBotService(settings, self.status_service)
        self.scheduler = AsyncIOScheduler(timezone=settings.timezone)
        self._shutdown_event = asyncio.Event()
        self._started = False

    async def run(self) -> None:
        self._install_signal_handlers()
        await self.startup()
        bot_task = asyncio.create_task(self.bot.start_polling(), name="admin-bot-polling")
        try:
            await self._shutdown_event.wait()
        finally:
            bot_task.cancel()
            await asyncio.gather(bot_task, return_exceptions=True)
            await self.shutdown()

    async def startup(self) -> None:
        logger.info("Application startup sequence beginning")
        await self.database.initialize()
        self.status_service.database_connected = True
        await self.telethon.connect()
        self.status_service.telethon_connected = self.telethon.is_connected()
        self.status_service.telethon_authorized = self.telethon.is_authorized()
        await self.listener.start()
        self._started = True
        logger.info("Application startup sequence complete")

    async def shutdown(self) -> None:
        if not self._started and not self.database.initialized:
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
        logger.info("Application shutdown sequence complete")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, self.request_shutdown)
            except (NotImplementedError, RuntimeError):
                logger.debug("Signal handlers unavailable for %s", signum.name)