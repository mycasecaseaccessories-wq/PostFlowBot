"""Safely adopt an existing Phase 0 database into Alembic tracking."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine

from app.database.migration import require_compatible_schema


def _alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


async def _validate(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        await require_compatible_schema(engine)
    finally:
        await engine.dispose()


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    asyncio.run(_validate(database_url))
    command.stamp(_alembic_config(database_url), "head")
    print("Existing schema validated and stamped at Alembic head.")


if __name__ == "__main__":
    main()
