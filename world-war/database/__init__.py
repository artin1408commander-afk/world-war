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
    # Opt-in SQLite only for isolated unit tests (never production).
    import os
    if mode in ("sqlite", "sqlite3") and os.getenv("WW_TEST_SQLITE", "").strip() in ("1", "true", "yes"):
        from database.sqlite import SQLiteDatabase
        db = SQLiteDatabase(str(settings.sqlite_path))
        await db.connect()
        await db.migrate()
        return db
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
