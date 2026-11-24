"""Player-to-player oil trading with confirmation and daily safety."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from modules.ng.oil_resource import ensure_tables, get_stock, add_stock

TEHRAN = ZoneInfo("Asia/Tehran")


async def ensure_trade_table(db) -> None:
    await ensure_tables(db)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ng_oil_trades (
            id INTEGER PRIMARY KEY,
            seller_code TEXT NOT NULL,
            buyer_code TEXT NOT NULL,
            barrels REAL NOT NULL,
            unit_price REAL NOT NULL,
            total REAL NOT NULL,
            seller_pid INTEGER,
            buyer_pid INTEGER,
            created_at TEXT NOT NULL
        )
        """
    )


async def execute_oil_trade(
    db,
    *,
    seller_code: str,
    buyer_code: str,
    barrels: float,
    unit_price: float,
    seller_pid: int,
    buyer_pid: int,
) -> str:
    """Atomic-ish oil trade: oil seller -> buyer, money buyer -> seller."""
    await ensure_trade_table(db)
    barrels = float(int(barrels))
    unit_price = float(unit_price)
    if barrels <= 0 or unit_price < 0:
        raise ValueError("مقدار یا قیمت نامعتبر است.")
    if seller_code == buyer_code:
        raise ValueError("فروشنده و خریدار یکسان هستند.")
    total = barrels * unit_price
    stock = await get_stock(db, seller_code)
    if stock + 1e-9 < barrels:
        raise ValueError(f"نفت کافی نیست. موجودی: {int(stock):,} بشکه")

    async with db.transaction() as tx:
        b = await tx.fetchrow(
            "SELECT treasury FROM ng_countries WHERE country_code=$1", (buyer_code,)
        )
        s = await tx.fetchrow(
            "SELECT treasury FROM ng_countries WHERE country_code=$1", (seller_code,)
        )
        if not b or not s:
            raise ValueError("کشور یافت نشد.")
        if float(b["treasury"] or 0) + 1e-9 < total:
            raise ValueError("موجودی مالی خریدار کافی نیست.")
        # re-check oil stock inside tx path via shared helper after money move
        await tx.execute(
            "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
            (float(b["treasury"]) - total, buyer_code),
        )
        await tx.execute(
            "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
            (float(s["treasury"]) + total, seller_code),
        )
        nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_oil_trades")
        await tx.execute(
            """
            INSERT INTO ng_oil_trades
            (id, seller_code, buyer_code, barrels, unit_price, total, seller_pid, buyer_pid, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            """,
            (
                int(nid["id"]),
                seller_code,
                buyer_code,
                barrels,
                unit_price,
                total,
                seller_pid,
                buyer_pid,
                datetime.now(TEHRAN).isoformat(),
            ),
        )
    # oil stock outside tx helper (same DB); still ordered after money commit
    # Verify stock again before deduct
    stock2 = await get_stock(db, seller_code)
    if stock2 + 1e-9 < barrels:
        # compensate money (best-effort)
        async with db.transaction() as tx:
            b = await tx.fetchrow(
                "SELECT treasury FROM ng_countries WHERE country_code=$1", (buyer_code,)
            )
            s = await tx.fetchrow(
                "SELECT treasury FROM ng_countries WHERE country_code=$1", (seller_code,)
            )
            if b and s:
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (float(b["treasury"]) + total, buyer_code),
                )
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (float(s["treasury"]) - total, seller_code),
                )
        raise ValueError("موجودی نفت در لحظه معامله کافی نبود؛ تراکنش لغو شد.")
    await add_stock(db, seller_code, -barrels)
    await add_stock(db, buyer_code, barrels)
    return (
        f"✅ معامله نفت انجام شد\n"
        f"🛢 مقدار: {int(barrels):,} بشکه\n"
        f"💵 قیمت واحد: {int(unit_price):,}\n"
        f"💰 مبلغ کل: {int(total):,}\n"
        f"از {seller_code} → {buyer_code}"
    )
