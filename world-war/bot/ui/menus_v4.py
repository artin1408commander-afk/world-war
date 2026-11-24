"""Phase 4 UI builders — cleaner menus, category inventory & store."""
from __future__ import annotations

from modules.ng.store_service import store_categories_present, format_price, items_in_category as svc_items

# Reply-keyboard labels (visible change for players)
BTN_HOME = "🏠 خانه"
BTN_COUNTRY = "🏛 کشور"
BTN_ECO = "💰 اقتصاد"
BTN_MIL = "⚔️ نظامی"
BTN_SHOP = "🛒 فروشگاه"
BTN_INV = "📦 انبار"
BTN_WORLD = "🌍 جهان"
BTN_MORE = "📂 بیشتر"
BTN_GUIDE = "📖 راهنما"
BTN_PICK = "🗺 انتخاب کشور"
BTN_OWNER = "🛡 پنل مدیریت"
BTN_ALLY = "🤝 اتحاد"

MAIN_REPLY_BUTTONS = {
    BTN_HOME, BTN_COUNTRY, BTN_ECO, BTN_MIL, BTN_SHOP, BTN_INV,
    BTN_WORLD, BTN_MORE, BTN_GUIDE, BTN_PICK, BTN_OWNER, BTN_ALLY,
}

INV_CATS = [
    ("ground", "⚔️ زمینی"),
    ("air", "✈️ هوایی"),
    ("sea", "🚢 دریایی"),
    ("missile", "🚀 موشکی"),
    ("defense", "🛡 پدافند"),
    ("infra", "🏗 زیرساخت"),
    ("mine", "⛏ منابع/نفت"),
    ("nuclear", "☢️ هسته‌ای"),
    ("cyber", "💻 سایبر"),
    ("specialist", "🧠 متخصص"),
    ("other", "📦 سایر"),
]

SHOP_QTY_PRESETS = [1, 5, 10, 25]


def main_menu_text(has_country: bool, country_label: str | None = None) -> str:
    if has_country and country_label:
        return (
            f"🎮 WORLD WAR\n"
            f"━━━━━━━━━━━━\n"
            f"کشور فعال: {country_label}\n\n"
            f"از منوی پایین یک بخش را انتخاب کنید."
        )
    return (
        "🎮 WORLD WAR\n"
        "━━━━━━━━━━━━\n"
        "هنوز کشوری انتخاب نکرده‌اید.\n"
        "با «🗺 انتخاب کشور» شروع کنید."
    )


def main_rows(is_owner: bool = False) -> list[list[str]]:
    rows = [
        [BTN_COUNTRY, BTN_ECO],
        [BTN_MIL, BTN_SHOP],
        [BTN_INV, BTN_ALLY],
        [BTN_WORLD, BTN_MORE],
        [BTN_GUIDE, BTN_PICK],
    ]
    if is_owner:
        rows.append([BTN_OWNER])
    return rows


def more_hub_text() -> str:
    return (
        "📂 بخش‌های بیشتر\n"
        "━━━━━━━━━━━━\n"
        "یکی از دسته‌ها را باز کنید:"
    )


def more_hub_rows() -> list:
    return [
        [("⚔️ عملیات نظامی", "ng:v4:more:mil"), ("🕊 دیپلماسی", "ng:v4:more:diplo")],
        [("🛢 نفت و انرژی", "ng:v4:more:oil"), ("🏭 صنعت/کارگاه", "ng:v4:more:industry")],
        [("📜 قانون و بیانیه", "ng:v4:more:docs"), ("📊 گزارش و دعوت", "ng:v4:more:info")],
        [("💎 حمایت", "ng:v4:more:support")],
        [("🔙 بازگشت", "ng:back"), ("🏠 خانه", "ng:home")],
    ]


def mil_menu_rows() -> list:
    return [
        [("⚔️ حمله زمینی/هوایی/دریایی", "ng:atkmenu")],
        [("🏛 کنترل کشور", "ng:more:ctrl"), ("☢️ هسته‌ای", "ng:more:npt")],
        [("🔙 بازگشت", "ng:v4:more:hub"), ("🏠 خانه", "ng:home")],
    ]


def diplo_menu_rows() -> list:
    return [
        [("🤝 اتحادها", "ng:go:ally"), ("🤝 روابط خارجی", "ng:more:diplo")],
        [("⚖ پیمان‌ها", "ng:more:treaty")],
        [("🔙 بازگشت", "ng:v4:more:hub"), ("🏠 خانه", "ng:home")],
    ]


def industry_menu_rows() -> list:
    return [
        [("🏭 کارگاه", "ng:more:workshop"), ("🌐 بازار آزاد", "ng:more:mkt")],
        [("🚢 تجارت/کمک", "ng:more:trade")],
        [("🔙 بازگشت", "ng:v4:more:hub"), ("🏠 خانه", "ng:home")],
    ]


def docs_menu_rows() -> list:
    return [
        [("📜 بیانیه", "ng:more:stmt"), ("📋 قوانین کشور", "ng:ctrl:laws")],
        [("پیمان NPT", "ng:more:npt")],
        [("🔙 بازگشت", "ng:v4:more:hub"), ("🏠 خانه", "ng:home")],
    ]


def info_menu_rows() -> list:
    return [
        [("📊 گزارش جهان", "ng:more:report"), ("🎁 دعوت دوستان", "ng:more:ref")],
        [("ℹ️ درباره بازی", "ng:more:about")],
        [("🔙 بازگشت", "ng:v4:more:hub"), ("🏠 خانه", "ng:home")],
    ]


def inv_hub_text() -> str:
    return (
        "📦 انبار تجهیزات\n"
        "━━━━━━━━━━━━\n"
        "دسته را انتخاب کنید تا اقلام همان بخش نمایش داده شود."
    )


def inv_hub_rows() -> list:
    rows = []
    pair = []
    for code, title in INV_CATS:
        pair.append((title, f"ng:v4:inv:{code}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([("📋 همه اقلام", "ng:v4:inv:all")])
    rows.append([("🔙 بازگشت", "ng:back"), ("🏠 خانه", "ng:home")])
    return rows


def shop_hub_text() -> str:
    return (
        "🛒 فروشگاه جهانی\n"
        "━━━━━━━━━━━━\n"
        "۱) دسته را انتخاب کنید\n"
        "۲) کالا را بزنید\n"
        "۳) تعداد را مشخص کنید\n"
        "۴) خرید را تأیید کنید"
    )


def shop_hub_rows(catalog: dict) -> list:
    cats = store_categories_present(catalog)
    rows = []
    pair = []
    for code, title in cats:
        n = sum(1 for m in catalog.values() if (m.get("category") or "other") == code)
        pair.append((f"{title} ({n})", f"ng:v4:shop:{code}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([("🛒 سبد", "ng:cart"), ("✅ تسویه", "ng:checkout")])
    rows.append([("🔙 بازگشت", "ng:back"), ("🏠 خانه", "ng:home")])
    return rows


def shop_item_rows(items: list[dict], cat: str, mult: float = 1.0) -> list:
    rows = []
    for m in sorted(items, key=lambda x: str(x.get("name_fa") or ""))[:40]:
        ic = m.get("item_code")
        name = str(m.get("name_fa") or ic)[:28]
        price = format_price(float(m.get("unit_price") or 0) * mult)
        rows.append([(f"{name} | {price}", f"ng:v4:item:{ic}")])
    rows.append([("⬅️ دسته‌ها", "ng:v4:shophome"), ("🛒 سبد", "ng:cart")])
    rows.append([("🏠 خانه", "ng:home")])
    return rows


def shop_qty_rows(item_code: str) -> list:
    row = [(f"×{q}", f"ng:v4:qty:{item_code}:{q}") for q in SHOP_QTY_PRESETS]
    return [
        row,
        [("✏️ تعداد دلخواه", f"ng:v4:qtyask:{item_code}")],
        [("⬅️ برگشت به کالاها", f"ng:v4:shopback")],
        [("🏠 خانه", "ng:home")],
    ]


def shop_confirm_rows(item_code: str, qty: int) -> list:
    return [
        [("✅ تأیید خرید", f"ng:v4:buy:{item_code}:{qty}")],
        [("✏️ تغییر تعداد", f"ng:v4:item:{item_code}")],
        [("⬅️ انصراف", "ng:v4:shophome")],
    ]


def admin_hub_text() -> str:
    return (
        "🛡 پنل مدیریت\n"
        "━━━━━━━━━━━━\n"
        "بخش موردنظر را انتخاب کنید:"
    )


def admin_hub_rows(is_primary: bool = False) -> list:
    rows = []
    if is_primary:
        rows.append([("➕ مالک", "ng:owners"), ("🛡 مالکان", "ng:owners")])
    rows += [
        [("👤 بازیکنان", "ng:o:hub:players"), ("🗺 کشورها", "ng:o:hub:countries")],
        [("💰 اقتصاد", "ng:o:hub:economy"), ("📦 تجهیزات", "ng:o:hub:inventory")],
        [("🕊 دیپلماسی", "ng:o:hub:diplo"), ("⚔️ جنگ", "ng:o:hub:wars")],
        [("⚙️ تنظیمات", "ng:o:hub:settings"), ("📋 گزارش", "ng:o:hub:logs")],
        [("🎫 تیکت", "ng:otix"), ("🔍 بن", "ng:obansearch")],
        [("🏠 خانه", "ng:home")],
    ]
    return rows
