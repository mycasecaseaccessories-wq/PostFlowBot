"""Safe runtime status snapshot for the admin interface."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    admin_bot: str
    database: str
    telethon: str
    telethon_auth: str
    listener: str

    def as_message(self) -> str:
        return (
            "🤖 Admin Bot: " + self.admin_bot + "\n"
            "🗄 Database: " + self.database + "\n"
            "👤 Telethon: " + self.telethon + "\n"
            "🔐 Telethon Auth: " + self.telethon_auth + "\n"
            "📡 Listener: " + self.listener
        )


class StatusService:
    def __init__(self) -> None:
        self.database_connected = False
        self.admin_bot_online = False
        self.telethon_connected = False
        self.telethon_authorized = False
        self.listener_running = False

    def snapshot(self) -> StatusSnapshot:
        return StatusSnapshot(
            admin_bot="Online" if self.admin_bot_online else "Offline",
            database="Connected" if self.database_connected else "Disconnected",
            telethon="Connected" if self.telethon_connected else "Disconnected",
            telethon_auth="Authorized" if self.telethon_authorized else "Unauthorized",
            listener="Running" if self.listener_running else "Stopped",
        )