"""Per-day receiving limits for aid (money + equipment)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")

MAX_MONEY_RECEIVE = 120_000_000.0
MAX_EQUIP_RECEIVE = 120.0


def today_key() -> str:
    return datetime.now(TEHRAN).date().isoformat()


async def ensure_table(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ng_aid_received_daily (
            country_code TEXT NOT NULL,
            day TEXT NOT NULL,
            money REAL NOT NULL DEFAULT 0,
            equipment REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (country_code, day)
        )
        """
    )


async def get_received(db, country_code: str) -> tuple[float, float]:
    await ensure_table(db)
    row = await db.fetchrow(
        "SELECT money, equipment FROM ng_aid_received_daily WHERE country_code=$1 AND day=$2",
        (country_code, today_key()),
    )
    if not row:
        return 0.0, 0.0
    return float(row["money"] or 0), float(row["equipment"] or 0)


async def assert_can_receive_money(db, country_code: str, amount: float) -> None:
    got, _ = await get_received(db, country_code)
    if got + float(amount) > MAX_MONEY_RECEIVE + 1e-6:
        left = max(0.0, MAX_MONEY_RECEIVE - got)
        raise ValueError(
            f"سقف دریافت کمک مالی امروز پر است.\n"
            f"سقف روزانه: {int(MAX_MONEY_RECEIVE):,}\n"
            f"باقیمانده قابل دریافت: {int(left):,}"
        )


async def assert_can_receive_equip(db, country_code: str, qty: float) -> None:
    _, got = await get_received(db, country_code)
    if got + float(qty) > MAX_EQUIP_RECEIVE + 1e-6:
        left = max(0.0, MAX_EQUIP_RECEIVE - got)
        raise ValueError(
            f"سقف دریافت تجهیزات امروز پر است.\n"
            f"سقف روزانه: {int(MAX_EQUIP_RECEIVE)} واحد\n"
            f"باقیمانده: {int(left)} واحد"
        )


async def add_received_money(db, country_code: str, amount: float) -> None:
    await ensure_table(db)
    day = today_key()
    row = await db.fetchrow(
        "SELECT money, equipment FROM ng_aid_received_daily WHERE country_code=$1 AND day=$2",
        (country_code, day),
    )
    if row:
        await db.execute(
            "UPDATE ng_aid_received_daily SET money=$1 WHERE country_code=$2 AND day=$3",
            (float(row["money"] or 0) + float(amount), country_code, day),
        )
    else:
        await db.execute(
            "INSERT INTO ng_aid_received_daily (country_code, day, money, equipment) VALUES ($1,$2,$3,0)",
            (country_code, day, float(amount)),
        )


async def add_received_equip(db, country_code: str, qty: float) -> None:
    await ensure_table(db)
    day = today_key()
    row = await db.fetchrow(
        "SELECT money, equipment FROM ng_aid_received_daily WHERE country_code=$1 AND day=$2",
        (country_code, day),
    )
    if row:
        await db.execute(
            "UPDATE ng_aid_received_daily SET equipment=$1 WHERE country_code=$2 AND day=$3",
            (float(row["equipment"] or 0) + float(qty), country_code, day),
        )
    else:
        await db.execute(
            "INSERT INTO ng_aid_received_daily (country_code, day, money, equipment) VALUES ($1,$2,0,$3)",
            (country_code, day, float(qty)),
        )
