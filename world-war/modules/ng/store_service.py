"""Store helpers: categories, pricing display, integer quantities, purchase locks."""
from __future__ import annotations

import time
from typing import Any

# Prevent double-checkout within a short window per player
_CHECKOUT_LOCKS: dict[int, float] = {}
CHECKOUT_COOLDOWN_SEC = 2.5

CAT_ORDER = [
    ("ground", "⚔️ نظامی زمینی"),
    ("air", "✈️ نظامی هوایی"),
    ("sea", "🚢 نظامی دریایی"),
    ("missile", "🚀 موشک‌ها"),
    ("defense", "🛡 پدافند"),
    ("infra", "🏗 زیرساخت"),
    ("mine", "⛏ منابع و نفت"),
    ("nuclear", "☢️ هسته‌ای"),
    ("specialist", "🧠 متخصصان"),
    ("cyber", "💻 سایبر"),
    ("other", "📦 سایر"),
]

CAT_ALIASES = {
    "military": ("ground", "air", "sea", "missile"),
    "oil": ("mine",),
}


def store_categories_present(catalog: dict[str, dict]) -> list[tuple[str, str]]:
    present = {str(m.get("category") or "other") for m in catalog.values()}
    out = []
    for code, title in CAT_ORDER:
        if code in present:
            out.append((code, title))
    return out


def items_in_category(catalog: dict[str, dict], cat: str) -> list[dict]:
    if cat == "military":
        cats = set(CAT_ALIASES["military"])
        return [m for m in catalog.values() if (m.get("category") or "other") in cats]
    if cat == "oil":
        return [
            m
            for m in catalog.values()
            if (m.get("category") == "mine" and "oil" in str(m.get("item_code", "")).lower())
            or "refinery" in str(m.get("item_code", "")).lower()
            or "oil" in str(m.get("item_code", "")).lower()
            or "نفت" in str(m.get("name_fa", ""))
        ]
    return [m for m in catalog.values() if (m.get("category") or "other") == cat]


def format_price(n: float) -> str:
    return f"{int(round(float(n))):,}"


def to_whole_qty(qty: Any) -> int:
    try:
        q = float(qty)
    except (TypeError, ValueError):
        return 0
    if q <= 0:
        return 0
    return max(1, int(q))  # floor toward whole units for purchases


def acquire_checkout_lock(pid: int) -> bool:
    now = time.time()
    last = _CHECKOUT_LOCKS.get(int(pid), 0.0)
    if now - last < CHECKOUT_COOLDOWN_SEC:
        return False
    _CHECKOUT_LOCKS[int(pid)] = now
    return True


def store_home_text() -> str:
    return (
        "🛒 فروشگاه جهانی\n\n"
        "دسته موردنظر را انتخاب کنید.\n"
        "قیمت‌ها ممکن است تحت تأثیر وضعیت کشور، اتحاد و بازار نفت باشند."
    )
