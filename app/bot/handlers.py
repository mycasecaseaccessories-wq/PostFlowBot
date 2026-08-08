"""Admin command and foundation button handlers."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from app.core.status import StatusService

FOUNDATION_NOTICE = "🚧 This feature will be available in the next phase."


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📡 Source Channels"), KeyboardButton(text="📤 Target Channels")],
            [KeyboardButton(text="⚙️ Settings"), KeyboardButton(text="📊 History")],
            [KeyboardButton(text="🔧 System Status")],
        ],
        resize_keyboard=True,
    )


def build_router(status_service: StatusService) -> Router:
    router = Router(name="admin")

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        status_service.admin_bot_online = True
        await message.answer(
            "🤖 Telegram Content Reposter\n\n"
            "System Status\n"
            "🟢 Admin Bot: Online\n"
            f"{'🟢' if status_service.database_connected else '🔴'} Database: "
            f"{'Connected' if status_service.database_connected else 'Disconnected'}\n"
            f"{'🟢' if status_service.telethon_connected else '🔴'} Telethon: "
            f"{'Connected' if status_service.telethon_connected else 'Disconnected'}",
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
            "Channel management, settings, and history are foundation placeholders in Phase 0."
        )

    @router.message(
        lambda message: message.text
        in {"📡 Source Channels", "📤 Target Channels", "⚙️ Settings", "📊 History"}
    )
    async def future_feature_handler(message: Message) -> None:
        await message.answer(FOUNDATION_NOTICE)

    return router