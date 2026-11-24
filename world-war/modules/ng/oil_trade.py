"""Player-to-player oil trading — single atomic database transaction."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from modules.ng.oil_resource import ensure_tables

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
            created_at TEXT NOT NULL,
            client_key TEXT
        )
        """
    )
    # Best-effort unique index for dedup keys (ignore if unsupported)
    try:
        await db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ng_oil_trades_client_key_uq
            ON ng_oil_trades(client_key)
            WHERE client_key IS NOT NULL
            """
        )
    except Exception:
        pass


async def _tx_get_stock(tx, code: str) -> float:
    row = await tx.fetchrow(
        "SELECT barrels FROM ng_oil_stock WHERE country_code=$1", (code,)
    )
    return float(row["barrels"] or 0) if row else 0.0


async def _tx_set_stock(tx, code: str, barrels: float) -> None:
    now = datetime.now(TEHRAN).isoformat()
    barrels = max(0.0, float(barrels))
    exists = await tx.fetchrow(
        "SELECT 1 AS x FROM ng_oil_stock WHERE country_code=$1", (code,)
    )
    if exists:
        await tx.execute(
            "UPDATE ng_oil_stock SET barrels=$1, updated_at=$2 WHERE country_code=$3",
            (barrels, now, code),
        )
    else:
        await tx.execute(
            "INSERT INTO ng_oil_stock (country_code, barrels, updated_at) VALUES ($1,$2,$3)",
            (code, barrels, now),
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
    client_key: str | None = None,
) -> str:
    """Atomic oil trade: money + oil + log in one transaction. Full rollback on failure."""
    await ensure_trade_table(db)
    barrels = float(int(barrels))
    unit_price = float(unit_price)
    if barrels <= 0 or unit_price < 0:
        raise ValueError("مقدار یا قیمت نامعتبر است.")
    if seller_code == buyer_code:
        raise ValueError("فروشنده و خریدار یکسان هستند.")
    total = barrels * unit_price
    ck = (client_key or "").strip() or None

    async with db.transaction() as tx:
        if ck:
            dup = await tx.fetchrow(
                "SELECT id FROM ng_oil_trades WHERE client_key=$1", (ck,)
            )
            if dup:
                raise ValueError("این معامله قبلاً ثبت شده است.")

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

        stock = await _tx_get_stock(tx, seller_code)
        if stock + 1e-9 < barrels:
            raise ValueError(f"نفت کافی نیست. موجودی: {int(stock):,} بشکه")

        # Money
        await tx.execute(
            "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
            (float(b["treasury"]) - total, buyer_code),
        )
        await tx.execute(
            "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
            (float(s["treasury"]) + total, seller_code),
        )
        # Oil
        await _tx_set_stock(tx, seller_code, stock - barrels)
        buyer_stock = await _tx_get_stock(tx, buyer_code)
        await _tx_set_stock(tx, buyer_code, buyer_stock + barrels)
        # Log
        nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_oil_trades")
        try:
            await tx.execute(
                """
                INSERT INTO ng_oil_trades
                (id, seller_code, buyer_code, barrels, unit_price, total, seller_pid, buyer_pid, created_at, client_key)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
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
                    ck,
                ),
            )
        except Exception:
            # schema without client_key column
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

    return (
        f"✅ معامله نفت انجام شد\n"
        f"🛢 مقدار: {int(barrels):,} بشکه\n"
        f"💵 قیمت واحد: {int(unit_price):,}\n"
        f"💰 مبلغ کل: {int(total):,}\n"
        f"از {seller_code} → {buyer_code}"
    )
