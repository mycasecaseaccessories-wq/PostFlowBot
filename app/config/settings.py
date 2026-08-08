"""Validated, environment-driven application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from aiogram.utils.token import TokenValidationError, validate_token
from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    telegram_session: str
    admin_user_ids: frozenset[int]
    database_url: str = "sqlite+aiosqlite:///./data/postflow.db"
    log_level: str = "INFO"
    timezone: str = "UTC"

    @property
    def database_path(self) -> Path | None:
        """Return the local SQLite file path, if this is a SQLite URL."""
        prefix = "sqlite+aiosqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        return Path(self.database_url.removeprefix(prefix))


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Required environment variable {name} is missing.")
    return value


def _parse_api_id(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError("Environment variable API_ID must be an integer.") from exc
    if value <= 0:
        raise ConfigurationError("Environment variable API_ID must be greater than zero.")
    return value


def _parse_api_hash(raw: str) -> str:
    if len(raw) != 32 or any(
        character not in "0123456789abcdefABCDEF" for character in raw
    ):
        raise ConfigurationError(
            "Environment variable API_HASH must be a 32-character hexadecimal value."
        )
    return raw


def _validate_bot_token(raw: str) -> str:
    try:
        validate_token(raw)
    except TokenValidationError as exc:
        raise ConfigurationError(
            "Environment variable BOT_TOKEN has an invalid format."
        ) from exc
    return raw


def _parse_admin_ids(raw: str) -> frozenset[int]:
    values: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            user_id = int(item)
        except ValueError as exc:
            raise ConfigurationError("ADMIN_USER_IDS must contain comma-separated integers.") from exc
        if user_id <= 0:
            raise ConfigurationError("ADMIN_USER_IDS must contain positive Telegram user IDs.")
        values.add(user_id)
    if not values:
        raise ConfigurationError("Required environment variable ADMIN_USER_IDS is missing.")
    return frozenset(values)


def load_settings(
    environ: Mapping[str, str] | None = None,
    dotenv_path: str | os.PathLike[str] | None = ".env",
) -> Settings:
    """Load and validate settings without ever logging secret values."""
    if dotenv_path is not None:
        load_dotenv(dotenv_path=dotenv_path, override=False)
    source = os.environ if environ is None else environ
    return Settings(
        bot_token=_validate_bot_token(_required(source, "BOT_TOKEN")),
        api_id=_parse_api_id(_required(source, "API_ID")),
        api_hash=_parse_api_hash(_required(source, "API_HASH")),
        telegram_session=_required(source, "TELEGRAM_SESSION"),
        admin_user_ids=_parse_admin_ids(_required(source, "ADMIN_USER_IDS")),
        database_url=source.get("DATABASE_URL", "sqlite+aiosqlite:///./data/postflow.db").strip()
        or "sqlite+aiosqlite:///./data/postflow.db",
        log_level=source.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        timezone=source.get("TIMEZONE", "UTC").strip() or "UTC",
    )