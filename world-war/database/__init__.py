"""Database factory — explicit mode, no silent fallback."""
from __future__ import annotations

from database.interface import Database
from database.postgres import PostgresDatabase
from database.sqlite import SQLiteDatabase
from config.settings import Settings


async def create_database(settings: Settings) -> Database:
    if settings.is_postgres:
        db: Database = PostgresDatabase(
            settings.database_url,
            min_size=settings.database_pool_min_size,
            max_size=settings.database_pool_max_size,
            command_timeout=settings.database_command_timeout,
            connect_timeout=settings.database_connect_timeout,
        )
    elif settings.is_sqlite:
        db = SQLiteDatabase(settings.sqlite_path)
    else:
        raise ValueError(f"Unknown DATABASE_MODE={settings.database_mode}")
    await db.connect()
    await db.migrate()
    return db
