"""Event listener foundation; it observes events but never reposts in Phase 0."""

from __future__ import annotations

from telethon import TelegramClient, events

from app.core.logger import get_logger
from app.core.status import StatusService

logger = get_logger(__name__)


class MessageListenerService:
    def __init__(self, client: TelegramClient, status_service: StatusService) -> None:
        self.client = client
        self.status_service = status_service
        self.running = False

    async def start(self) -> None:
        if not self.client.is_connected():
            logger.warning("Listener not started because Telethon is disconnected")
            return
        self.client.add_event_handler(self._on_new_message, events.NewMessage)
        self.client.add_event_handler(self._on_message_edited, events.MessageEdited)
        self.client.add_event_handler(self._on_message_deleted, events.MessageDeleted)
        self.running = True
        self.status_service.listener_running = True
        logger.info("Message listener started")

    async def stop(self) -> None:
        self.client.remove_event_handler(self._on_new_message, events.NewMessage)
        self.client.remove_event_handler(self._on_message_edited, events.MessageEdited)
        self.client.remove_event_handler(self._on_message_deleted, events.MessageDeleted)
        self.running = False
        self.status_service.listener_running = False
        logger.info("Message listener stopped")

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        logger.info("New Telegram message detected from configured source")

    async def _on_message_edited(self, event: events.MessageEdited.Event) -> None:
        logger.debug("Telegram message edited event detected")

    async def _on_message_deleted(self, event: events.MessageDeleted.Event) -> None:
        logger.debug("Telegram message deleted event detected")