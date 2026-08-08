"""Single-owner Telethon client service."""

from __future__ import annotations

from pathlib import Path

from telethon import TelegramClient

from app.config.settings import Settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class TelethonClientService:
    def __init__(self, settings: Settings) -> None:
        session_path = Path(settings.telegram_session)
        if session_path.parent != Path("."):
            session_path.parent.mkdir(parents=True, exist_ok=True)
        self.client = TelegramClient(
            settings.telegram_session,
            settings.api_id,
            settings.api_hash,
        )
        self.connected = False
        self.authorized = False

    async def connect(self) -> None:
        try:
            await self.client.connect()
            self.connected = self.client.is_connected()
            if self.connected:
                self.authorized = await self.client.is_user_authorized()
                if self.authorized:
                    logger.info("Telethon client connected and authorized")
                else:
                    logger.warning(
                        "Telethon client connected but the session is unauthorized"
                    )
            else:
                logger.warning("Telethon client did not establish a connection")
        except Exception as exc:
            self.connected = False
            self.authorized = False
            logger.warning("Telethon connection could not be established: %s", type(exc).__name__)

    async def disconnect(self) -> None:
        if self.client.is_connected():
            await self.client.disconnect()
        self.connected = False
        self.authorized = False
        logger.info("Telethon client disconnected")

    def is_connected(self) -> bool:
        return self.connected and self.client.is_connected()

    def is_authorized(self) -> bool:
        return self.authorized

    def get_client(self) -> TelegramClient:
        return self.client