"""Application entry point for the Telegram Content Reposter Bot."""

from __future__ import annotations

import asyncio

from app.config.settings import ConfigurationError, load_settings
from app.core.lifecycle import Application
from app.core.logger import configure_logging, get_logger


async def async_main() -> None:
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        logger = get_logger(__name__)
        logger.info("Starting Telegram Content Reposter Bot")
        application = Application(settings)
        await application.run()
    except ConfigurationError as exc:
        configure_logging("ERROR")
        get_logger(__name__).critical("Configuration invalid: %s", exc)
        raise SystemExit(2) from exc


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        get_logger(__name__).info("Shutdown requested")


if __name__ == "__main__":
    main()
