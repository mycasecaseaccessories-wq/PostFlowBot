"""One-time interactive Telethon session setup.

Run this locally after copying the required values into .env. It is intentionally
separate from production startup so the bot never prompts for a phone or OTP.
"""

from __future__ import annotations

import asyncio

from app.config.settings import load_settings
from app.telegram.client import TelethonClientService


async def create_session() -> None:
    settings = load_settings()
    service = TelethonClientService(settings)
    await service.client.start()
    print("Telethon session created and authorized.")
    await service.disconnect()


if __name__ == "__main__":
    asyncio.run(create_session())