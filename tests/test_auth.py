from __future__ import annotations

import pytest
from aiogram.types import Message, User
from unittest.mock import AsyncMock, MagicMock

from app.bot.auth import AdminAccessMiddleware


@pytest.mark.asyncio
async def test_admin_middleware_allows_authorized_user() -> None:
    middleware = AdminAccessMiddleware(frozenset({42}))
    called = False

    async def handler(event: Message, data: dict[str, object]) -> str:
        nonlocal called
        called = True
        return "ok"

    message = Message.model_construct(from_user=User(id=42, is_bot=False, first_name="Admin"))
    result = await middleware(handler, message, {})
    assert result == "ok"
    assert called


@pytest.mark.asyncio
async def test_admin_middleware_blocks_unauthorized_user() -> None:
    middleware = AdminAccessMiddleware(frozenset({42}))
    called = False

    async def handler(event: Message, data: dict[str, object]) -> None:
        nonlocal called
        called = True

    message = MagicMock(spec=Message)
    message.from_user = User(id=7, is_bot=False, first_name="Guest")
    message.answer = AsyncMock()
    result = await middleware(handler, message, {})
    assert result is None
    assert not called
    message.answer.assert_awaited_once_with("⛔ Access denied.")