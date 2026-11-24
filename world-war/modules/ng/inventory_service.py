"""Inventory display and whole-unit helpers (does not mutate historical data)."""
from __future__ import annotations

from typing import Any, Callable, Awaitable

CAT_TITLE = {
    "ground": "⚔️ نیروی زمینی",
    "air": "✈️ نیروی هوایی",
    "sea": "🚢 نیروی دریایی",
    "defense": "🛡 پدافند",
    "missile": "🚀 موشک‌ها",
    "specialist": "🧠 متخصصان",
    "cyber": "💻 فناوری/سایبر",
    "nuclear": "☢️ هسته‌ای",
    "mine": "⛏ منابع",
    "infra": "🏗 زیرساخت",
    "other": "📦 سایر تجهیزات",
}

ORDER = [
    "ground", "air", "sea", "missile", "defense", "specialist",
    "cyber", "nuclear", "mine", "infra", "other",
]


def whole_qty(qty: Any) -> int:
    """Normalize countable purchase/transfer quantities to non-negative integers."""
    try:
        q = float(qty)
    except (TypeError, ValueError):
        return 0
    if q <= 0:
        return 0
    return int(q)  # truncate fractional component for new operations


def format_qty_display(q: float) -> str:
    if q >= 1:
        return f"{int(q):,} عدد"
    if q > 0:
        return "کمتر از ۱ عدد"
    return "۰"


async def build_inventory_text(
    db,
    code: str,
    *,
    cat_lookup: Callable[[str], dict | None],
    oil_stock: float | None = None,
    cat_fa: dict | None = None,
) -> str:
    rows = await db.fetch(
        "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0 ORDER BY item_code",
        (code,),
    )
    lines = ["📦 انبار کشور", ""]
    if oil_stock is not None:
        lines.append(f"🛢 نفت ذخیره‌شده: {int(oil_stock):,} بشکه")
        lines.append("")
    if not rows:
        lines.append("خالی است.")
        return "\n".join(lines)
    by_cat: dict[str, list] = {}
    for r in rows:
        meta = cat_lookup(r["item_code"]) or {
            "name_fa": r["item_code"],
            "category": "other",
        }
        cat = meta.get("category") or "other"
        by_cat.setdefault(cat, []).append((meta, r))
    for cat in ORDER:
        items = by_cat.get(cat)
        if not items:
            continue
        title = CAT_TITLE.get(cat) or (cat_fa or {}).get(cat, cat)
        lines.append(title)
        for meta, r in items:
            q = float(r["quantity"] or 0)
            if q <= 0:
                continue
            name = meta.get("name_fa") or r["item_code"]
            lines.append(f"• {name}: {format_qty_display(q)}")
        lines.append("")
    return "\n".join(lines).rstrip()
