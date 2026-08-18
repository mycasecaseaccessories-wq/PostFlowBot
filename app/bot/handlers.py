"""Admin command and Phase 0 CMS navigation handlers."""
from __future__ import annotations

from typing import Any

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from app.core.status import StatusService

FOUNDATION_NOTICE = "🚧 This feature will be available in the next phase."
CMS_PLACEHOLDER_BUTTONS = {
    "🏠 Dashboard",
    "📝 Content",
    "📢 Channels",
    "📅 Scheduler",
    "📚 Library",
    "📊 Analytics",
    "⚙️ Settings",
}


def admin_keyboard() -> ReplyKeyboardMarkup:
    """Build the Phase 0 CMS roadmap navigation."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Dashboard"), KeyboardButton(text="📝 Content")],
            [KeyboardButton(text="📢 Channels"), KeyboardButton(text="📅 Scheduler")],
            [KeyboardButton(text="📚 Library"), KeyboardButton(text="📊 Analytics")],
            [KeyboardButton(text="⚙️ Settings")],
        ],
        resize_keyboard=True,
    )


def build_router(
    status_service: StatusService,
    source_service: Any | None = None,
    target_service: Any | None = None,
    routing_service: Any | None = None,
) -> Router:
    """Build the admin router with stable Phase 0 dependency wiring.

    The service arguments intentionally remain optional and unused in Phase 0. They
    preserve the modular service boundary for future channel/routing handlers while
    keeping the core admin router limited to foundation functionality.
    """
    del source_service, target_service, routing_service
    router = Router(name="admin")

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        status_service.admin_bot_online = True
        await message.answer(
            "PostFlow Bot\n\n"
            "System Status\n"
            "🟢 Admin Bot: Online\n"
            f"{'🟢' if status_service.database_connected else '🔴'} Database: "
            f"{'Connected' if status_service.database_connected else 'Disconnected'}\n"
            f"{'🟢' if status_service.telethon_connected else '🔴'} Telethon: "
            f"{'Connected' if status_service.telethon_connected else 'Disconnected'}\n"
            f"{'🟢' if status_service.listener_running else '🔴'} Listener: "
            f"{'Running' if status_service.listener_running else 'Stopped'}",
            reply_markup=admin_keyboard(),
        )

    @router.message(Command("status"))
    @router.message(lambda message: message.text == "🔧 System Status")
    async def status_handler(message: Message) -> None:
        await message.answer(status_service.snapshot().as_message())

    @router.message(Command("help"))
    async def help_handler(message: Message) -> None:
        await message.answer(
            "Available commands:\n"
            "/start — open the admin interface\n"
            "/status — show service health\n"
            "/help — show this help\n\n"
            "CMS navigation items are Phase 0 placeholders."
        )

    @router.message(lambda message: message.text in CMS_PLACEHOLDER_BUTTONS)
    async def future_feature_handler(message: Message) -> None:
        await message.answer(FOUNDATION_NOTICE)

    return router
