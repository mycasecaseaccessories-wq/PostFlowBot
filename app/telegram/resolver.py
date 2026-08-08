"""Telethon-backed channel resolution for admin management flows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from telethon.tl.types import Channel

from app.core.exceptions import TelegramServiceError
from app.core.logger import get_logger

from .client import TelethonClientService

logger = get_logger(__name__)

_USERNAME_RE = re.compile(r"^@?[A-Za-z0-9_]{5,32}$")


@dataclass(frozen=True, slots=True)
class ResolvedChannel:
    chat_id: int
    username: str | None
    title: str
    channel_type: str
    publishing_permission_confirmed: bool | None = None


class ChannelResolver:
    """Resolves and normalizes channels through the shared Telethon client."""

    def __init__(self, client_service: TelethonClientService) -> None:
        self.client_service = client_service

    @staticmethod
    def validate_input(value: str) -> str | int:
        candidate = value.strip()
        if not candidate:
            raise TelegramServiceError("Please send a channel username or numeric channel ID.")
        if candidate.lstrip("-").isdigit():
            try:
                return int(candidate)
            except ValueError as exc:
                raise TelegramServiceError("That channel ID is invalid.") from exc
        if not _USERNAME_RE.fullmatch(candidate):
            raise TelegramServiceError("That channel username is invalid.")
        return candidate.removeprefix("@")

    async def resolve(self, value: str, *, target: bool = False) -> ResolvedChannel:
        if not self.client_service.is_connected() or not self.client_service.is_authorized():
            raise TelegramServiceError(
                "The Telethon user account is not connected or authorized."
            )
        entity_input = self.validate_input(value)
        try:
            entity: Any = await self.client_service.get_client().get_entity(entity_input)
        except Exception as exc:
            logger.warning("Channel resolution failed: %s", type(exc).__name__)
            raise TelegramServiceError(
                "Could not access this channel. Please verify the username or ID and "
                "that the Telethon account has access."
            ) from exc
        if not isinstance(entity, Channel):
            raise TelegramServiceError("This Telegram entity is not a supported channel.")
        username = getattr(entity, "username", None)
        permission = self._publishing_permission(entity) if target else None
        return ResolvedChannel(
            chat_id=int(entity.id) if int(entity.id) < 0 else int(f"-100{entity.id}"),
            username=f"@{username}" if username else None,
            title=getattr(entity, "title", None) or "Untitled channel",
            channel_type="broadcast" if getattr(entity, "broadcast", False) else "megagroup",
            publishing_permission_confirmed=permission,
        )

    @staticmethod
    def _publishing_permission(entity: Channel) -> bool | None:
        admin_rights = getattr(entity, "admin_rights", None)
        if admin_rights is None:
            return None
        post_messages = getattr(admin_rights, "post_messages", None)
        return bool(post_messages) if post_messages is not None else None