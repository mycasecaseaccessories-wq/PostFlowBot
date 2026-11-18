"""Telegram source listener; imported messages enter the durable intake pipeline."""
from __future__ import annotations

from telethon import TelegramClient, events

from app.core.logger import get_logger
from app.core.status import StatusService
from app.services.message_intake import MessageIntakeService

logger = get_logger(__name__)


class MessageListenerService:
    def __init__(self, client: TelegramClient, status_service: StatusService,
                 intake_service: MessageIntakeService | None = None) -> None:
        self.client = client
        self.status_service = status_service
        self.intake_service = intake_service
        self.running = False

    async def start(self) -> None:
        if self.running:
            return
        if not self.client.is_connected() or not await self.client.is_user_authorized():
            logger.warning("Listener not started: Telethon is not connected and authorized")
            return
        self.client.add_event_handler(self._on_new_message, events.NewMessage)
        self.client.add_event_handler(self._on_message_edited, events.MessageEdited)
        self.client.add_event_handler(self._on_message_deleted, events.MessageDeleted)
        self.running = True
        self.status_service.listener_running = True
        logger.info("Message listener started")

    async def stop(self) -> None:
        if not self.running:
            return
        self.client.remove_event_handler(self._on_new_message, events.NewMessage)
        self.client.remove_event_handler(self._on_message_edited, events.MessageEdited)
        self.client.remove_event_handler(self._on_message_deleted, events.MessageDeleted)
        self.running = False
        self.status_service.listener_running = False
        logger.info("Message listener stopped")

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        if self.intake_service is None or event.message is None:
            return
        message = event.message
        media = getattr(message, "media", None)
        if media is not None:
            logger.info("Media source message %s deferred; media and album intake adapter is not enabled", message.id)
            return
        result = await self.intake_service.ingest(
            source_chat_id=int(event.chat_id),
            message_id=int(message.id),
            text=message.message,
            content_type="text",
            grouped_id=getattr(message, "grouped_id", None),
        )
        if result.accepted:
            logger.info("Imported source message %s; queued %s target jobs", message.id, result.queued_jobs)
        elif result.duplicate:
            logger.debug("Ignored duplicate source message %s", message.id)

    async def _on_message_edited(self, event: events.MessageEdited.Event) -> None:
        if self.intake_service is None or event.message is None or event.chat_id is None:
            return
        updated = await self.intake_service.update_source_message(
            source_chat_id=int(event.chat_id),
            message_id=int(event.message.id),
            text=event.message.message,
        )
        if updated:
            logger.info("Synchronized edited source message %s", event.message.id)

    async def _on_message_deleted(self, event: events.MessageDeleted.Event) -> None:
        if self.intake_service is None or event.chat_id is None:
            logger.debug("Deleted message event has no channel context; skipping source sync")
            return
        for message_id in event.deleted_ids:
            archived = await self.intake_service.delete_source_message(
                source_chat_id=int(event.chat_id),
                message_id=int(message_id),
            )
            if archived:
                logger.info("Archived deleted source message %s", message_id)
