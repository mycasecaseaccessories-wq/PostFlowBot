"""Telegram publisher backed by the authorized Telethon user client.

Only media already persisted in the configured storage volume is published.
The publisher does not re-download source Telegram media or use Bot API tokens.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError

from app.services.publishing_worker import (
    PermanentPublishError,
    RetryablePublishError,
    UncertainPublishError,
)


class TelegramPublisher:
    """Send text, single media, and media albums through the listener account."""

    def __init__(self, client: TelegramClient, media_storage: Any) -> None:
        self.client = client
        self.media_storage = media_storage

    async def publish(self, payload: Any) -> int:
        if not self.client.is_connected() or not await self.client.is_user_authorized():
            raise PermanentPublishError("Telegram publishing account is not connected and authorized.")

        media_items = tuple(getattr(payload, "media", ()) or ())
        text = (getattr(payload, "text", "") or "").strip()
        try:
            if not media_items:
                if not text:
                    raise PermanentPublishError("Cannot publish an empty text post.")
                message = await self.client.send_message(
                    payload.destination_chat_id, text, parse_mode=None,
                )
                return int(message.id)

            paths: list[str] = []
            for item in media_items:
                if item.storage_backend != "local" or not item.storage_key:
                    raise PermanentPublishError("Media is not available in persistent local storage.")
                path = self.media_storage.resolve(item.storage_key)
                if not path.is_file():
                    raise PermanentPublishError("A stored media file is missing; operator recovery is required.")
                paths.append(str(path))

            # Telethon sends a list as one album. The caption is attached to the
            # first item, matching Telegram's album caption behavior.
            sent = await self.client.send_file(
                payload.destination_chat_id,
                paths if len(paths) > 1 else paths[0],
                caption=text or None,
                parse_mode=None,
            )
            if isinstance(sent, (list, tuple)):
                if not sent:
                    raise UncertainPublishError("Telegram returned no message IDs after media send.")
                return int(sent[0].id)
            return int(sent.id)
        except (PermanentPublishError, RetryablePublishError, UncertainPublishError):
            raise
        except FloodWaitError as exc:
            # Telegram explicitly rejected/deferred this request; a delayed retry is safe.
            raise RetryablePublishError(f"Telegram rate limit: wait {exc.seconds} seconds.") from exc
        except RPCError as exc:
            # Telegram's RPC response is definitive; do not retry invalid permissions/content.
            raise PermanentPublishError(f"Telegram rejected the publish request: {type(exc).__name__}.") from exc
        except (TimeoutError, OSError, ConnectionError) as exc:
            # The server may have accepted the request before the connection failed.
            raise UncertainPublishError(f"Telegram delivery outcome is unknown: {type(exc).__name__}.") from exc
