"""Admin commands for source/target channel and route management."""
from __future__ import annotations

from typing import Any

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from app.core.status import StatusService
from app.services.content_transform import transform_text

FOUNDATION_NOTICE = "This feature is not available yet."
CMS_PLACEHOLDER_BUTTONS = {
    "🏠 Dashboard", "📝 Content", "📅 Scheduler", "📚 Library",
    "📊 Analytics", "⚙️ Settings",
}


def admin_keyboard() -> ReplyKeyboardMarkup:
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
    permission_service: Any | None = None,
) -> Router:
    router = Router(name="admin")

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        status_service.admin_bot_online = True
        await message.answer(
            "PostFlow Bot\n\n"
            f"{'🟢' if status_service.database_connected else '🔴'} Database: "
            f"{'Connected' if status_service.database_connected else 'Disconnected'}\n"
            f"{'🟢' if status_service.telethon_connected else '🔴'} Telethon: "
            f"{'Connected' if status_service.telethon_connected else 'Disconnected'}\n"
            f"{'🟢' if status_service.listener_running else '🔴'} Listener: "
            f"{'Running' if status_service.listener_running else 'Stopped'}\n\n"
            "Channel commands: /sources /targets /routes\n"
            "/source_add @username\n/target_add @username\n"
            "/route_add SOURCE_ID TARGET_ID\n/target_check TARGET_ID",
            reply_markup=admin_keyboard(),
        )

    @router.message(Command("status"))
    async def status_handler(message: Message) -> None:
        await message.answer(status_service.snapshot().as_message())

    @router.message(Command("sources"))
    async def sources_handler(message: Message) -> None:
        if source_service is None:
            await message.answer("Source channel service is unavailable.")
            return
        rows = await source_service.list_sources(limit=100)
        await message.answer("\n".join(
            f"#{row.id} · {row.title or row.telegram_chat_id} · "
            f"{'ON' if row.is_active else 'OFF'}"
            for row in rows
        ) or "No source channels registered.")

    @router.message(Command("targets"))
    async def targets_handler(message: Message) -> None:
        if target_service is None:
            await message.answer("Target channel service is unavailable.")
            return
        rows = await target_service.list_targets(limit=100)
        await message.answer("\n".join(
            f"#{row.id} · {row.title or row.telegram_chat_id} · "
            f"{row.posting_permission_status} · {'ON' if row.is_active else 'OFF'}"
            for row in rows
        ) or "No target channels registered.")

    @router.message(Command("routes"))
    async def routes_handler(message: Message) -> None:
        if routing_service is None:
            await message.answer("Routing service is unavailable.")
            return
        rows = await routing_service.list_routes(limit=100)
        await message.answer("\n".join(
            f"#{row.id} · source {row.source_channel_id} → target {row.target_channel_id} · "
            f"{'ON' if row.is_active else 'OFF'}"
            for row in rows
        ) or "No routes configured.")

    @router.message(Command("source_add"))
    async def source_add_handler(message: Message) -> None:
        if source_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /source_add @channelusername")
            return
        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            await message.answer("Usage: /source_add @channelusername")
            return
        try:
            resolved = await source_service.resolve(parts[1])
            result = await source_service.add_source(resolved, message.from_user.id)
            await message.answer(f"Source saved: #{result.channel.id} · {result.channel.title}")
        except Exception as exc:
            await message.answer(f"Could not add source: {str(exc)[:500]}")

    @router.message(Command("target_add"))
    async def target_add_handler(message: Message) -> None:
        if target_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /target_add @channelusername")
            return
        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            await message.answer("Usage: /target_add @channelusername")
            return
        try:
            resolved = await target_service.resolve(parts[1])
            result = await target_service.add_target(resolved, message.from_user.id)
            await message.answer(
                f"Target saved: #{result.channel.id} · {result.channel.title}\n"
                "Run /target_check before creating an active route."
            )
        except Exception as exc:
            await message.answer(f"Could not add target: {str(exc)[:500]}")

    @router.message(Command("route_add"))
    async def route_add_handler(message: Message) -> None:
        if routing_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /route_add SOURCE_ID TARGET_ID")
            return
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("Usage: /route_add SOURCE_ID TARGET_ID")
            return
        try:
            route = await routing_service.create_route(
                int(parts[1]), int(parts[2]), message.from_user.id
            )
            await message.answer(
                f"Route saved: #{route.id} · {route.source_channel_id} → {route.target_channel_id}"
            )
        except Exception as exc:
            await message.answer(f"Could not create route: {str(exc)[:500]}")

    @router.message(Command("route_filters"))
    async def route_filters_handler(message: Message) -> None:
        if routing_service is None or not message.from_user or not message.text:
            await message.answer(
                "Usage: /route_filters ROUTE_ID usernames=on links=off keywords=spam,scam"
            )
            return
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer(
                "Usage: /route_filters ROUTE_ID usernames=on links=off keywords=spam,scam\n"
                "Use keywords=none to clear keyword filters."
            )
            return
        try:
            route_id = int(parts[1])
            updates: dict[str, Any] = {}
            update_keywords = False
            keywords: str | None = None
            for token in parts[2].split():
                if "=" not in token:
                    raise ValueError(f"Invalid filter setting: {token}")
                key, value = token.split("=", 1)
                value = value.strip()
                if key in {"usernames", "links"}:
                    normalized = value.lower()
                    if normalized not in {"on", "off", "true", "false", "1", "0"}:
                        raise ValueError(f"{key} must be on or off.")
                    updates["remove_usernames" if key == "usernames" else "remove_links"] = (
                        normalized in {"on", "true", "1"}
                    )
                elif key == "keywords":
                    update_keywords = True
                    keywords = None if value.lower() in {"none", "off"} else value
                else:
                    raise ValueError(f"Unknown filter: {key}")
            route = await routing_service.update_route_filters(
                route_id, message.from_user.id,
                remove_usernames=updates.get("remove_usernames"),
                remove_links=updates.get("remove_links"),
                remove_keywords=keywords,
                update_keywords=update_keywords,
            )
            await message.answer(
                f"Route #{route.id} filters saved\n"
                f"Remove usernames: {'ON' if route.remove_usernames else 'OFF'}\n"
                f"Remove links: {'ON' if route.remove_links else 'OFF'}\n"
                f"Remove keywords: {route.remove_keywords or 'none'}"
            )
        except Exception as exc:
            await message.answer(f"Could not update route filters: {str(exc)[:500]}")

    @router.message(Command("route_preview"))
    async def route_preview_handler(message: Message) -> None:
        if routing_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /route_preview ROUTE_ID text to preview")
            return
        parts = message.text.split(maxsplit=2)
        if len(parts) != 3:
            await message.answer("Usage: /route_preview ROUTE_ID text to preview")
            return
        try:
            route = await routing_service.get_route(int(parts[1]))
            preview = transform_text(
                parts[2],
                remove_usernames=route.remove_usernames,
                remove_links=route.remove_links,
                remove_keywords=route.remove_keywords,
            )
            await message.answer(f"Preview for route #{route.id}:\n\n{preview[:3500] or '(empty)'}")
        except Exception as exc:
            await message.answer(f"Could not preview route: {str(exc)[:500]}")

    @router.message(Command("target_check"))
    async def target_check_handler(message: Message) -> None:
        if permission_service is None or not message.text:
            await message.answer("Permission verification is unavailable.")
            return
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: /target_check TARGET_ID")
            return
        try:
            allowed, detail = await permission_service.verify(int(parts[1]))
            await message.answer(("🟢 " if allowed else "🔴 ") + detail)
        except Exception as exc:
            await message.answer(f"Permission check failed: {str(exc)[:500]}")

    @router.message(Command("source_refresh"))
    async def source_refresh_handler(message: Message) -> None:
        if source_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /source_refresh SOURCE_ID")
            return
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: /source_refresh SOURCE_ID")
            return
        try:
            source = await source_service.refresh_source(int(parts[1]), message.from_user.id)
            await message.answer(f"Source refreshed: {source.title or source.telegram_chat_id}")
        except Exception as exc:
            await message.answer(f"Could not refresh source: {str(exc)[:500]}")

    @router.message(Command("target_refresh"))
    async def target_refresh_handler(message: Message) -> None:
        if target_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /target_refresh TARGET_ID")
            return
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: /target_refresh TARGET_ID")
            return
        try:
            target = await target_service.refresh_target(int(parts[1]), message.from_user.id)
            await message.answer(
                f"Target refreshed: {target.title or target.telegram_chat_id}. "
                "Run /target_check again to verify current posting permission."
            )
        except Exception as exc:
            await message.answer(f"Could not refresh target: {str(exc)[:500]}")

    @router.message(Command("source_on"))
    async def source_on_handler(message: Message) -> None:
        if source_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /source_on SOURCE_ID")
            return
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: /source_on SOURCE_ID")
            return
        try:
            await source_service.enable_source(int(parts[1]), message.from_user.id)
            await message.answer("Source enabled. Re-enable its routes separately with /route_on.")
        except Exception as exc:
            await message.answer(f"Could not enable source: {str(exc)[:500]}")

    @router.message(Command("target_on"))
    async def target_on_handler(message: Message) -> None:
        if target_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /target_on TARGET_ID")
            return
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: /target_on TARGET_ID")
            return
        try:
            await target_service.enable_target(int(parts[1]), message.from_user.id)
            await message.answer("Target enabled. Run /target_check before enabling routes.")
        except Exception as exc:
            await message.answer(f"Could not enable target: {str(exc)[:500]}")

    @router.message(Command("source_off"))
    async def source_off_handler(message: Message) -> None:
        if source_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /source_off SOURCE_ID")
            return
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: /source_off SOURCE_ID")
            return
        try:
            await source_service.remove_source(int(parts[1]), message.from_user.id)
            await message.answer("Source disabled; its routes are disabled too.")
        except Exception as exc:
            await message.answer(f"Could not disable source: {str(exc)[:500]}")

    @router.message(Command("target_off"))
    async def target_off_handler(message: Message) -> None:
        if target_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /target_off TARGET_ID")
            return
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: /target_off TARGET_ID")
            return
        try:
            await target_service.remove_target(int(parts[1]), message.from_user.id)
            await message.answer("Target disabled; its routes are disabled too.")
        except Exception as exc:
            await message.answer(f"Could not disable target: {str(exc)[:500]}")

    @router.message(Command("route_off"))
    async def route_off_handler(message: Message) -> None:
        if routing_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /route_off ROUTE_ID")
            return
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: /route_off ROUTE_ID")
            return
        try:
            await routing_service.disable_route(int(parts[1]), message.from_user.id)
            await message.answer("Route disabled.")
        except Exception as exc:
            await message.answer(f"Could not disable route: {str(exc)[:500]}")

    @router.message(Command("route_on"))
    async def route_on_handler(message: Message) -> None:
        if routing_service is None or not message.from_user or not message.text:
            await message.answer("Usage: /route_on ROUTE_ID")
            return
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: /route_on ROUTE_ID")
            return
        try:
            await routing_service.enable_route(int(parts[1]), message.from_user.id)
            await message.answer("Route enabled; ensure both channels are active and target permission is verified.")
        except Exception as exc:
            await message.answer(f"Could not enable route: {str(exc)[:500]}")

    @router.message(Command("help"))
    async def help_handler(message: Message) -> None:
        await message.answer(
            "/start /status /help\n/sources /targets /routes\n"
            "/source_add @username\n/target_add @username\n"
            "/source_refresh SOURCE_ID\n/target_refresh TARGET_ID\n"
            "/route_add SOURCE_ID TARGET_ID\n/route_on ROUTE_ID\n/route_off ROUTE_ID\n"
            "/target_check TARGET_ID\n/source_on SOURCE_ID\n/source_off SOURCE_ID\n"
            "/target_on TARGET_ID\n/target_off TARGET_ID"
        )

    @router.message(lambda message: message.text in CMS_PLACEHOLDER_BUTTONS or message.text == "📢 Channels")
    async def navigation_handler(message: Message) -> None:
        if message.text == "📢 Channels":
            await message.answer("Channel management commands: /sources /targets /routes")
        else:
            await message.answer(FOUNDATION_NOTICE)

    return router
