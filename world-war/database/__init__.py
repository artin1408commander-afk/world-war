"""Database factory — PostgreSQL only at runtime."""
from __future__ import annotations

from config.settings import Settings
from database.interface import Database
from database.postgres import PostgresDatabase


async def create_database(settings: Settings) -> Database:
    """Create the production database connection.

    WORLD WAR uses Railway PostgreSQL exclusively.
    SQLite is not available at runtime (see tools/ for offline migration).
    """
    if not (settings.database_url or "").strip():
        raise RuntimeError(
            "DATABASE_URL is empty. Refusing to start without PostgreSQL."
        )
    mode = (settings.database_mode or "postgres").lower()
    if mode not in ("postgres", "postgresql", "pg"):
        raise RuntimeError(
            f"Unsupported DATABASE_MODE={settings.database_mode!r}. PostgreSQL only."
        )
    db = PostgresDatabase(
        settings.database_url,
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
        connect_timeout=settings.database_connect_timeout,
        command_timeout=settings.database_command_timeout,
    )
    await db.connect()
    await db.migrate()
    return db
