"""Persistent oil stock + daily refinery production (idempotent per Tehran day)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")

# Oil units produced per refinery unit per day
REFINERY_OIL_OUTPUT = {
    "b_refinery_s": 25.0,
    "b_refinery_m": 55.0,
    "b_refinery_l": 100.0,
    "b_oil_field": 40.0,
}

BASE_OIL_UNIT_PRICE = 84_000  # matches catalog baseline


async def ensure_tables(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ng_oil_stock (
            country_code TEXT PRIMARY KEY,
            barrels REAL NOT NULL DEFAULT 0,
            updated_at TEXT
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ng_oil_daily (
            country_code TEXT NOT NULL,
            day TEXT NOT NULL,
            produced REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (country_code, day)
        )
        """
    )


def today_key() -> str:
    return datetime.now(TEHRAN).date().isoformat()


async def get_stock(db, code: str) -> float:
    await ensure_tables(db)
    row = await db.fetchrow("SELECT barrels FROM ng_oil_stock WHERE country_code=$1", (code,))
    return float(row["barrels"] or 0) if row else 0.0


async def add_stock(db, code: str, amount: float) -> float:
    await ensure_tables(db)
    cur = await get_stock(db, code)
    new = max(0.0, cur + float(amount))
    now = datetime.now(TEHRAN).isoformat()
    exists = await db.fetchrow("SELECT 1 AS x FROM ng_oil_stock WHERE country_code=$1", (code,))
    if exists:
        await db.execute(
            "UPDATE ng_oil_stock SET barrels=$1, updated_at=$2 WHERE country_code=$3",
            (new, now, code),
        )
    else:
        await db.execute(
            "INSERT INTO ng_oil_stock (country_code, barrels, updated_at) VALUES ($1,$2,$3)",
            (code, new, now),
        )
    return new


async def produce_daily_for_country(db, code: str, inventory_rows: list[dict]) -> float:
    """Return barrels produced today (0 if already produced)."""
    await ensure_tables(db)
    day = today_key()
    done = await db.fetchrow(
        "SELECT produced FROM ng_oil_daily WHERE country_code=$1 AND day=$2",
        (code, day),
    )
    if done:
        return 0.0
    produced = 0.0
    for r in inventory_rows:
        ic = r.get("item_code")
        q = float(r.get("quantity") or 0)
        if ic in REFINERY_OIL_OUTPUT and q > 0:
            produced += REFINERY_OIL_OUTPUT[ic] * int(q)
    produced = float(int(produced))  # whole barrels
    if produced > 0:
        await add_stock(db, code, produced)
    await db.execute(
        "INSERT INTO ng_oil_daily (country_code, day, produced) VALUES ($1,$2,$3)",
        (code, day, produced),
    )
    return produced
