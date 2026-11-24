"""Reusable purchase safeguards (dedup + whole units)."""
from __future__ import annotations

import time
import uuid
from typing import Any

from modules.ng.inventory_service import whole_qty
from modules.ng.store_service import acquire_checkout_lock, to_whole_qty

# DB-backed dedup for checkouts (table created on demand)
_CHECKOUT_KEYS: dict[str, float] = {}


async def ensure_purchase_tables(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ng_purchase_dedup (
            client_key TEXT PRIMARY KEY,
            player_id INTEGER NOT NULL,
            country_code TEXT,
            total REAL,
            created_at TEXT NOT NULL
        )
        """
    )


def new_client_key(prefix: str = "p") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def normalize_buy_qty(qty: Any) -> int:
    q = to_whole_qty(qty)
    if q <= 0:
        return 0
    return whole_qty(q)


async def begin_checkout(db, pid: int, client_key: str | None = None) -> str:
    """Acquire soft lock + optional dedup key. Returns client_key."""
    if not acquire_checkout_lock(pid):
        raise ValueError("⏳ درخواست خرید قبلی هنوز در حال پردازش است. چند لحظه صبر کنید.")
    key = (client_key or "").strip() or new_client_key("checkout")
    await ensure_purchase_tables(db)
    exists = await db.fetchrow(
        "SELECT client_key FROM ng_purchase_dedup WHERE client_key=$1", (key,)
    )
    if exists:
        raise ValueError("این خرید قبلاً ثبت شده است.")
    return key


async def finalize_checkout_dedup(
    db, *, client_key: str, pid: int, country_code: str, total: float
) -> None:
    from datetime import datetime, timezone

    await ensure_purchase_tables(db)
    await db.execute(
        """
        INSERT INTO ng_purchase_dedup (client_key, player_id, country_code, total, created_at)
        VALUES ($1,$2,$3,$4,$5)
        """,
        (
            client_key,
            int(pid),
            country_code,
            float(total),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
