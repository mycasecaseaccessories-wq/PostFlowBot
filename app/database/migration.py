"""Helpers for validating and adopting existing databases into Alembic."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from . import cms_models as _cms_models  # noqa: F401  # register CMS tables
from .models import Base


class SchemaCompatibilityError(RuntimeError):
    """Raised when an existing database cannot safely adopt the baseline."""


@dataclass(frozen=True, slots=True)
class SchemaValidation:
    missing_tables: tuple[str, ...]
    missing_columns: dict[str, tuple[str, ...]]

    @property
    def compatible(self) -> bool:
        return not self.missing_tables and not self.missing_columns


async def validate_existing_schema(engine: AsyncEngine) -> SchemaValidation:
    """Check that every model table and column exists before Alembic stamping."""

    def inspect_schema(connection) -> SchemaValidation:
        database_inspector = inspect(connection)
        actual_tables = set(database_inspector.get_table_names())
        expected_tables = set(Base.metadata.tables)
        missing_tables = tuple(sorted(expected_tables - actual_tables))
        missing_columns: dict[str, tuple[str, ...]] = {}
        for table_name in sorted(expected_tables & actual_tables):
            actual_columns = {
                column["name"] for column in database_inspector.get_columns(table_name)
            }
            expected_columns = {
                column.name for column in Base.metadata.tables[table_name].columns
            }
            missing = tuple(sorted(expected_columns - actual_columns))
            if missing:
                missing_columns[table_name] = missing
        return SchemaValidation(missing_tables, missing_columns)

    async with engine.connect() as connection:
        return await connection.run_sync(inspect_schema)


async def require_migration_tracking(engine: AsyncEngine) -> None:
    """Require Alembic to have recorded a revision before managed startup."""

    def has_tracking_table(connection) -> bool:
        return "alembic_version" in inspect(connection).get_table_names()

    async with engine.connect() as connection:
        tracked = await connection.run_sync(has_tracking_table)
    if not tracked:
        raise SchemaCompatibilityError(
            "alembic_version is missing; run 'alembic upgrade head' or adopt_database.py first."
        )


async def require_compatible_schema(engine: AsyncEngine) -> SchemaValidation:
    """Validate an existing database and raise instead of silently stamping drift."""
    validation = await validate_existing_schema(engine)
    if not validation.compatible:
        details = [f"missing tables: {validation.missing_tables}"]
        if validation.missing_columns:
            details.append(f"missing columns: {validation.missing_columns}")
        raise SchemaCompatibilityError("; ".join(details))
    return validation
