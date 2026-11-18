"""Verify Telethon account posting rights and persist the result."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.database.models import TargetChannel
from app.telegram.client import TelethonClientService


class ChannelPermissionService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession],
                 telethon: TelethonClientService) -> None:
        self.session_factory = session_factory
        self.telethon = telethon

    async def verify(self, target_id: int) -> tuple[bool, str]:
        async with self.session_factory() as session:
            target = await session.get(TargetChannel, target_id)
            if target is None:
                raise LookupError("Target channel not found.")
            status, error = "denied", None
            try:
                if not self.telethon.is_connected() or not self.telethon.is_authorized():
                    raise RuntimeError("Telethon user account is not connected and authorized.")
                client = self.telethon.get_client()
                entity = await client.get_entity(target.telegram_chat_id)
                participant = await client.get_participant(entity, "me")
                rights = getattr(participant, "admin_rights", None)
                creator = participant.__class__.__name__.endswith("Creator")
                is_broadcast = bool(getattr(entity, "broadcast", False))
                is_megagroup = bool(getattr(entity, "megagroup", False))
                if creator:
                    status = "verified"
                elif is_broadcast and rights and bool(getattr(rights, "post_messages", False)):
                    status = "verified"
                elif is_megagroup:
                    banned_rights = getattr(participant, "banned_rights", None)
                    if not bool(getattr(banned_rights, "send_messages", False)):
                        status = "verified"
                    else:
                        error = "The connected Telegram account is restricted from sending messages in this group."
                else:
                    error = "The connected Telegram account has no channel posting permission."
            except Exception as exc:
                error = str(exc)[:1000]
            target.posting_permission_status = status
            target.publishing_permission_confirmed = status == "verified"
            target.permission_checked_at = datetime.now(UTC)
            target.permission_error = error
            await session.commit()
            return status == "verified", error or "Posting permission verified."
