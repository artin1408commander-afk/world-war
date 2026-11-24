"""Persistent oil stock + daily refinery production (idempotent per Tehran day)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")

# هر پالایشگاه / میدان نفتی = ۱۲۰ بشکه در روز (ساعت ۱۲ شب تهران)
BARRELS_PER_REFINERY = 120.0
REFINERY_CODES = (
    "b_refinery_s",
    "b_refinery_m",
    "b_refinery_l",
    "b_oil_field",
)
# legacy alias kept for any old imports
REFINERY_OIL_OUTPUT = {c: BARRELS_PER_REFINERY for c in REFINERY_CODES}

BASE_OIL_UNIT_PRICE = 84_000
RES_OIL_ITEM = "res_oil"


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
    stock = float(row["barrels"] or 0) if row else 0.0
    # Heal: oil bought earlier only sat in inventory — promote to stock once
    try:
        inv = await db.fetchrow(
            "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
            (code, RES_OIL_ITEM),
        )
        inv_q = float(inv["quantity"] or 0) if inv else 0.0
        if inv_q > stock + 1e-6:
            now = datetime.now(TEHRAN).isoformat()
            if row:
                await db.execute(
                    "UPDATE ng_oil_stock SET barrels=$1, updated_at=$2 WHERE country_code=$3",
                    (inv_q, now, code),
                )
            else:
                await db.execute(
                    "INSERT INTO ng_oil_stock (country_code, barrels, updated_at) VALUES ($1,$2,$3)",
                    (code, inv_q, now),
                )
            stock = inv_q
    except Exception:
        pass
    return stock


async def _sync_inventory_res_oil(db, code: str, barrels: float) -> None:
    """Keep ng_inventory.res_oil aligned with oil stock (assets display)."""
    barrels = max(0.0, float(barrels))
    inv = await db.fetchrow(
        "SELECT quantity FROM ng_inventory WHERE country_code=$1 AND item_code=$2",
        (code, RES_OIL_ITEM),
    )
    if inv:
        await db.execute(
            "UPDATE ng_inventory SET quantity=$1 WHERE country_code=$2 AND item_code=$3",
            (barrels, code, RES_OIL_ITEM),
        )
    else:
        if barrels > 0:
            await db.execute(
                "INSERT INTO ng_inventory (country_code, item_code, quantity) VALUES ($1,$2,$3)",
                (code, RES_OIL_ITEM, barrels),
            )


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
    try:
        await _sync_inventory_res_oil(db, code, new)
    except Exception:
        pass
    return new


def count_refineries(inventory_rows: list[dict]) -> float:
    total = 0.0
    for r in inventory_rows:
        ic = r.get("item_code")
        if ic in REFINERY_CODES:
            total += max(0.0, float(r.get("quantity") or 0))
    return total


def daily_production_from_inventory(inventory_rows: list[dict]) -> float:
    """Barrels per Tehran-day from owned refineries/fields."""
    return count_refineries(inventory_rows) * BARRELS_PER_REFINERY


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
    produced = daily_production_from_inventory(inventory_rows)
    if produced <= 0:
        # mark day so we don't re-scan endlessly without stock write
        await db.execute(
            "INSERT INTO ng_oil_daily (country_code, day, produced) VALUES ($1,$2,$3)",
            (code, day, 0.0),
        )
        return 0.0
    await add_stock(db, code, produced)
    await db.execute(
        "INSERT INTO ng_oil_daily (country_code, day, produced) VALUES ($1,$2,$3)",
        (code, day, produced),
    )
    return produced
