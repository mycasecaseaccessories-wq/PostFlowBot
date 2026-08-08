"""Admin-only access control for aiogram events."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class AdminAccessMiddleware(BaseMiddleware):
    def __init__(self, admin_user_ids: frozenset[int]) -> None:
        self.admin_user_ids = admin_user_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = event.from_user
        if user is None or user.id not in self.admin_user_ids:
            if isinstance(event, Message):
                await event.answer("Access denied.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Access denied.", show_alert=True)
            return None
        return await handler(event, data)