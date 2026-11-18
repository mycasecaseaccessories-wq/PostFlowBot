"""Telegram source listener; text and media enter the durable intake pipeline."""
from __future__ import annotations

from telethon import TelegramClient, events, utils
from telethon.tl.types import (
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
)

from app.core.logger import get_logger
from app.core.status import StatusService
from app.services.message_intake import MediaDescriptor, MessageIntakeService

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
        if self.intake_service is not None:
            try:
                recovered = await self.intake_service.retry_pending_media(
                    client=self.client, limit=20
                )
                if recovered:
                    logger.info("Recovered %s pending Telegram media objects", recovered)
            except Exception as exc:
                logger.warning("Pending media recovery skipped (%s)", type(exc).__name__)
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

    @staticmethod
    def _formatting_entities(message) -> list[dict]:
        entities = getattr(message, "entities", None) or ()
        return [entity.to_dict() for entity in entities if hasattr(entity, "to_dict")]

    @staticmethod
    def _media_descriptor(message) -> MediaDescriptor | None:
        media = getattr(message, "photo", None) or getattr(message, "document", None)
        if media is None:
            return None
        document = getattr(message, "document", None)
        attributes = getattr(document, "attributes", ()) if document else ()
        filename = next((a.file_name for a in attributes
                         if isinstance(a, DocumentAttributeFilename)), None)
        video = next((a for a in attributes if isinstance(a, DocumentAttributeVideo)), None)
        audio = next((a for a in attributes if isinstance(a, DocumentAttributeAudio)), None)
        if getattr(message, "photo", None) is not None:
            kind = "photo"
            sizes = getattr(media, "sizes", ())
            largest = max(sizes, key=lambda item: getattr(item, "size", 0), default=None)
            width = getattr(largest, "w", None)
            height = getattr(largest, "h", None)
            duration = None
            mime_type = "image/jpeg"
        elif video is not None:
            kind, width, height, duration = "video", video.w, video.h, int(video.duration)
            mime_type = getattr(document, "mime_type", None)
        elif audio is not None:
            kind, width, height, duration = ("voice" if audio.voice else "audio"), None, None, int(audio.duration)
            mime_type = getattr(document, "mime_type", None)
        elif (getattr(document, "mime_type", "") or "").startswith("image/"):
            kind, width, height, duration = "photo", None, None, None
            mime_type = getattr(document, "mime_type", None)
        else:
            kind, width, height, duration = "document", None, None, None
            mime_type = getattr(document, "mime_type", None)
        try:
            packed_id = utils.pack_bot_file_id(media)
        except (TypeError, ValueError, AttributeError):
            logger.warning("Skipping unsupported Telegram media object on message %s", message.id)
            return None
        media_id = getattr(media, "id", None)
        unique_id = f"telethon:{kind}:{media_id}" if media_id is not None else None
        return MediaDescriptor(
            telegram_file_id=packed_id,
            telegram_file_unique_id=unique_id,
            media_type=kind,
            original_file_name=filename,
            mime_type=mime_type,
            file_size=getattr(media, "size", None),
            width=width,
            height=height,
            duration=duration,
        )

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        if self.intake_service is None or event.message is None or event.chat_id is None:
            return
        message = event.message
        descriptor = self._media_descriptor(message)
        media_items = [descriptor] if descriptor is not None else []
        result = await self.intake_service.ingest(
            source_chat_id=int(event.chat_id),
            message_id=int(message.id),
            text=message.message,
            content_type="text" if not media_items else media_items[0].media_type,
            grouped_id=getattr(message, "grouped_id", None),
            media_items=media_items,
            formatting_entities=self._formatting_entities(message),
        )
        if result.content_id and descriptor is not None:
            try:
                await self.intake_service.store_telegram_media(
                    client=self.client, message=message, descriptor=descriptor
                )
            except Exception as exc:
                logger.warning(
                    "Media storage pending for source message %s (%s)",
                    message.id, type(exc).__name__,
                )
        if result.accepted:
            logger.info("Imported source message %s; queued %s target jobs",
                        message.id, result.queued_jobs)
        elif result.duplicate:
            logger.debug("Ignored duplicate source message %s", message.id)
        elif result.reason not in {"source_not_registered", "empty_or_media_only"}:
            logger.warning("Source message %s was not imported: %s", message.id, result.reason)

    async def _on_message_edited(self, event: events.MessageEdited.Event) -> None:
        if self.intake_service is None or event.message is None or event.chat_id is None:
            return
        message = event.message
        updated = await self.intake_service.update_source_message(
            source_chat_id=int(event.chat_id),
            message_id=int(message.id),
            text=message.message,
            formatting_entities=self._formatting_entities(message),
        )
        descriptor = self._media_descriptor(message)
        if descriptor is not None:
            result = await self.intake_service.ingest(
                source_chat_id=int(event.chat_id),
                message_id=int(message.id),
                text=message.message,
                content_type=descriptor.media_type,
                grouped_id=getattr(message, "grouped_id", None),
                media_items=[descriptor],
                formatting_entities=self._formatting_entities(message),
            )
            if result.content_id:
                try:
                    await self.intake_service.store_telegram_media(
                        client=self.client, message=message, descriptor=descriptor
                    )
                except Exception as exc:
                    logger.warning(
                        "Edited media storage pending for source message %s (%s)",
                        message.id, type(exc).__name__,
                    )
        if updated or descriptor is not None:
            logger.info("Synchronized edited source message %s", message.id)

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
