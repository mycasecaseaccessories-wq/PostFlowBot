"""Async SQLAlchemy database lifecycle."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import Settings
from app.core.logger import get_logger

from .migration import require_compatible_schema, require_migration_tracking
from .models import Base

logger = get_logger(__name__)


class Database:
    """Owns the engine and session factory; handlers never access the engine directly."""

    def __init__(self, settings: Settings) -> None:
        self.url = settings.database_url
        self.schema_mode = settings.database_schema_mode
        self.engine: AsyncEngine = create_async_engine(self.url, future=True)
        if self.url.startswith("sqlite"):
            event.listen(self.engine.sync_engine, "connect", self._enable_sqlite_foreign_keys)
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.initialized = False

    async def initialize(self) -> None:
        path = self._sqlite_path()
        if path is not None and self.schema_mode == "bootstrap":
            path.parent.mkdir(parents=True, exist_ok=True)
        async with self.engine.begin() as connection:
            if self.schema_mode == "bootstrap":
                await connection.run_sync(Base.metadata.create_all)
            else:
                await connection.execute(text("SELECT 1"))
        if self.schema_mode == "migrations":
            await require_compatible_schema(self.engine)
            await require_migration_tracking(self.engine)
        self.initialized = True
        logger.info("Database initialized with schema mode: %s", self.schema_mode)

    @staticmethod
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def session(self) -> AsyncSession:
        return self.session_factory()

    async def close(self) -> None:
        await self.engine.dispose()
        self.initialized = False
        logger.info("Database connection closed")

    def _sqlite_path(self) -> Path | None:
        prefix = "sqlite+aiosqlite:///"
        if not self.url.startswith(prefix):
            return None
        return Path(self.url.removeprefix(prefix))