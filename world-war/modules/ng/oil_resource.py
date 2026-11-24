"""Persistent oil stock + daily oil-building production (Tehran midnight / daily payout)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")

# فقط این ساختمان‌ها نفت می‌دهند (نه درآمد دلاری اصلی)
REFINERY_OIL_OUTPUT = {
    "b_refinery_s": 120.0,   # پالایشگاه نفت کوچک
    "b_refinery_m": 240.0,   # پالایشگاه نفت متوسط
    "b_refinery_l": 400.0,   # پالایشگاه نفت بزرگ
    "b_oil_field": 180.0,    # میدان نفتی
}
REFINERY_CODES = tuple(REFINERY_OIL_OUTPUT.keys())
BARRELS_PER_REFINERY = 120.0  # مرجع پایه (کوچک)

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
    elif barrels > 0:
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
        if ic in REFINERY_OIL_OUTPUT:
            total += max(0.0, float(r.get("quantity") or 0))
    return total


def daily_production_from_inventory(inventory_rows: list[dict]) -> float:
    produced = 0.0
    for r in inventory_rows:
        ic = r.get("item_code")
        q = max(0.0, float(r.get("quantity") or 0))
        if ic in REFINERY_OIL_OUTPUT and q > 0:
            produced += q * float(REFINERY_OIL_OUTPUT[ic])
    return produced


async def produce_daily_for_country(db, code: str, inventory_rows: list[dict]) -> float:
    await ensure_tables(db)
    day = today_key()
    done = await db.fetchrow(
        "SELECT produced FROM ng_oil_daily WHERE country_code=$1 AND day=$2",
        (code, day),
    )
    if done:
        return 0.0
    produced = daily_production_from_inventory(inventory_rows)
    await db.execute(
        "INSERT INTO ng_oil_daily (country_code, day, produced) VALUES ($1,$2,$3)",
        (code, day, produced),
    )
    if produced > 0:
        await add_stock(db, code, produced)
    return produced
