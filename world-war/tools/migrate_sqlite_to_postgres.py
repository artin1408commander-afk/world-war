#!/usr/bin/env python3
"""OFFLINE tool: copy data from a local SQLite file into Railway PostgreSQL.

This is NOT used by the running bot. Runtime is PostgreSQL-only.

Usage:
  export DATABASE_URL='postgresql://...'
  python tools/migrate_sqlite_to_postgres.py /path/to/world_war.db

Requires: asyncpg, aiosqlite
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def main(sqlite_path: Path, database_url: str) -> None:
    import aiosqlite
    import asyncpg

    if not sqlite_path.is_file():
        raise SystemExit(f"SQLite file not found: {sqlite_path}")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    src = await aiosqlite.connect(str(sqlite_path))
    src.row_factory = aiosqlite.Row
    dst = await asyncpg.connect(database_url)

    tables = [
        r[0]
        for r in await src.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    print(f"Tables in SQLite: {len(tables)}")
    for t in tables:
        rows = await src.execute_fetchall(f"SELECT * FROM {t}")
        print(f"  {t}: {len(rows)} rows (manual review / upsert recommended)")
        # Safe default: do not auto-overwrite production. Print only.
        # Operators should use a controlled upsert script per table after review.
    await src.close()
    await dst.close()
    print(
        "Report complete. For production import, use a reviewed upsert per table. "
        "This tool does not wipe PostgreSQL."
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("sqlite_db", type=Path)
    p.add_argument("--database-url", default="")
    args = p.parse_args()
    import os
    url = args.database_url or os.getenv("DATABASE_URL", "")
    asyncio.run(main(args.sqlite_db, url))
