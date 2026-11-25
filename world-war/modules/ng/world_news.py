"""Hourly world news — narrative headlines from real events, or unique roleplay."""
from __future__ import annotations

import hashlib
import logging
import random
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
TEHRAN = ZoneInfo("Asia/Tehran")

REAL_KINDS = (
    "attack",
    "buy",
    "checkout",
    "shop",
    "sell",
    "aid_money",
    "aid_army",
    "aid_oil",
    "claim",
    "destroy",
    "nuke",
    "nuclear",
    "ban",
    "unban",
    "alliance",
    "peace",
    "trade",
    "oil_trade",
    "lucky_spin",
    "statement",
)

RP_TEMPLATES = [
    "زلزله‌ای خفیف در نزدیکی {a} گزارش شد؛ زیرساخت‌ها آسیب جزئی دیدند.",
    "مذاکرات تجاری محرمانه بین {a} و {b} آغاز شده است.",
    "شایعهٔ رزمایش مشترک {a} و {b} در آب‌های منطقه‌ای پیچیده است.",
    "قیمت نفت در بازار سیاه پس از تحرکات {a} نوسان کرد.",
    "هیئت دیپلماتیک {a} به‌طور غیرمنتظره عازم {b} شد.",
    "اعتراض‌های پراکنده در پایتخت {a} مهار شد.",
    "یک محمولهٔ فناوری حساس در مسیر {a} ناپدید شد — تحقیقات شروع شده.",
    "رصدخانه‌های {a} فعالیت غیرعادی در مرز {b} گزارش کردند.",
    "بانک مرکزی {a} محدودیت موقت ارزی اعلام کرد.",
    "گشت دریایی {a} نزدیک آب‌های {b} دیده شد.",
    "شایعهٔ استعفای یکی از مشاوران ارشد {a} منتشر شد.",
    "مه غلیظ و طوفان شن مانورهای {a} را مختل کرد.",
    "توافق آتش‌بس موقت محلی بین نیروهای نزدیک {a} و {b} گزارش شد.",
    "بازار سیاه تسلیحات در حوزهٔ {a} گرم‌تر از همیشه است.",
    "یک کانال تلویزیونی {a} فیلمی از رزمایش شبانه پخش کرد.",
]


async def ensure_tables(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ng_world_news (
            id BIGSERIAL PRIMARY KEY,
            fingerprint TEXT NOT NULL UNIQUE,
            body TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'real',
            created_at TEXT NOT NULL
        )
        """
    )
    try:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ng_world_news_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_hour_key TEXT,
                last_body TEXT
            )
            """
        )
        row = await db.fetchrow("SELECT id FROM ng_world_news_meta WHERE id=1")
        if not row:
            await db.execute(
                "INSERT INTO ng_world_news_meta (id, last_hour_key, last_body) VALUES (1, NULL, NULL)"
            )
    except Exception:
        log.exception("ng_world_news_meta ensure")


def _fp(text: str) -> str:
    norm = re.sub(r"\s+", " ", (text or "").strip())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:40]


def hour_key(now: datetime | None = None) -> str:
    now = now or datetime.now(TEHRAN)
    return now.strftime("%Y-%m-%d-%H")


async def _seen(db, fingerprint: str) -> bool:
    row = await db.fetchrow(
        "SELECT 1 AS x FROM ng_world_news WHERE fingerprint=$1", (fingerprint,)
    )
    return bool(row)


async def _remember(db, body: str, source: str) -> None:
    fp = _fp(body)
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.execute(
            """
            INSERT INTO ng_world_news (fingerprint, body, source, created_at)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (fingerprint) DO NOTHING
            """,
            (fp, body, source, now),
        )
    except Exception:
        try:
            if not await _seen(db, fp):
                await db.execute(
                    "INSERT INTO ng_world_news (fingerprint, body, source, created_at) VALUES ($1,$2,$3,$4)",
                    (fp, body, source, now),
                )
        except Exception:
            log.exception("remember news")


async def _country_label(db, code: str | None) -> str:
    if not code:
        return "یک کشور ناشناس"
    try:
        row = await db.fetchrow(
            "SELECT flag, name_fa FROM ng_countries WHERE country_code=$1",
            (str(code),),
        )
        if row:
            return f"{row.get('flag') or ''} {row.get('name_fa') or code}".strip()
    except Exception:
        pass
    return str(code)


async def _player_name(db, pid) -> str:
    if pid is None:
        return "یک فرمانده"
    try:
        row = await db.fetchrow(
            "SELECT display_name, username FROM ng_players WHERE player_id=$1",
            (int(pid),),
        )
        if row:
            return (
                (row.get("display_name") or row.get("username") or f"بازیکن {pid}")
            )
    except Exception:
        pass
    return f"بازیکن {pid}"


async def _country_names(db, limit: int = 40) -> list[str]:
    rows = await db.fetch(
        """
        SELECT name_fa, flag FROM ng_countries
        WHERE owner_player_id IS NOT NULL
        ORDER BY name_fa
        LIMIT $1
        """,
        (limit,),
    )
    names = []
    for r in rows or []:
        n = f"{r.get('flag') or ''} {r.get('name_fa') or ''}".strip()
        if n:
            names.append(n)
    if len(names) < 2:
        rows2 = await db.fetch(
            "SELECT name_fa, flag FROM ng_countries ORDER BY name_fa LIMIT $1", (limit,)
        )
        for r in rows2 or []:
            n = f"{r.get('flag') or ''} {r.get('name_fa') or ''}".strip()
            if n and n not in names:
                names.append(n)
    return names or ["کشور بی‌نام", "قدرت منطقه‌ای"]


def _extract_amount(summary: str) -> str | None:
    m = re.search(r"([\d٬,]{3,})", summary or "")
    if m:
        return m.group(1).replace(",", "٬")
    m2 = re.search(r"(\d+)\s*(بشکه|میلیون|میلیارد)?", summary or "")
    if m2:
        return (m2.group(0) or "").strip()
    return None


def _extract_prize(summary: str) -> str:
    s = summary or ""
    s = re.sub(r"^چرخ شانس\s*[:：\-]?\s*", "", s, flags=re.I).strip()
    return s or "یک جایزه مرموز"


async def narrate_event(db, row: dict) -> str | None:
    """Turn a raw activity row into a proper Persian news sentence."""
    kind = str(row.get("kind") or "")
    summary = re.sub(r"\s+", " ", (row.get("summary") or "").strip())
    if not summary or len(summary) < 4:
        return None
    if summary.startswith("❌") or summary.startswith("خطا"):
        return None

    country = await _country_label(db, row.get("country_code"))
    player = await _player_name(db, row.get("player_id"))
    amount = _extract_amount(summary)

    # --- lucky spin ---
    if kind == "lucky_spin" or "چرخ شانس" in summary:
        prize = _extract_prize(summary)
        templates = [
            f"در چرخ شانس امروز، کشور {country} موفق شد «{prize}» را به‌دست آورد و خوش‌شانسی خود را به رخ جهان کشید.",
            f"فرمانده {player} از {country} در چرخش بخت، برندهٔ «{prize}» شد؛ منابع این کشور تقویت شد.",
            f"گزارش ویژه: {country} با برنده شدن «{prize}» در چرخ شانس، توجه ناظران بین‌المللی را جلب کرد.",
        ]
        return random.choice(templates)

    # --- combat ---
    if kind in ("attack", "nuke", "nuclear") or "حمله" in summary:
        if "اتمی" in summary or "هسته‌" in summary or kind in ("nuke", "nuclear"):
            templates = [
                f"خبر فوری: {country} یک حمله اتمی علیه دشمن خود انجام داد و موازنه قدرت را بر هم زد.",
                f"پس از یک درگیری هسته‌ای، {country} نام خود را در صدر اخبار جنگ ثبت کرد.",
                f"ناظران نظامی از حمله اتمی منتسب به {country} خبر دادند؛ خسارت گسترده‌ای گزارش شده است.",
            ]
        elif "نابود" in summary:
            templates = [
                f"جهان در شوک: یک کشور در پی حملهٔ {country} از نقشه قدرت‌ها حذف شد.",
                f"گزارش‌ها حاکی است نیروهای {country} دشمن را تا مرز نابودی کامل پیش بردند.",
            ]
        else:
            templates = [
                f"ارتش {country} عملیات نظامی تازه‌ای را آغاز کرد و جبهه‌های جنگ دوباره داغ شد.",
                f"درگیری جدید: {country} به مواضع دشمن یورش برد؛ جزئیات خسارت در حال بررسی است.",
                f"خبرنگاران جبهه گزارش دادند نیروهای {country} در یک حملهٔ غافلگیرانه ظاهر شدند.",
            ]
        return random.choice(templates)

    if kind == "destroy" or "نابود" in summary:
        templates = [
            f"پایان یک قدرت: کشوری در اثر درگیری‌های اخیر نابود و قلمرویش آزاد اعلام شد. عامل اصلی: {country}.",
            f"سازمان ملل تأیید کرد یک واحد سیاسی پس از حملهٔ {country} از صحنه کنار رفت.",
        ]
        return random.choice(templates)

    # --- economy / shop ---
    if kind in ("buy", "checkout", "shop"):
        if amount:
            templates = [
                f"بازار تسلیحات تکان خورد: {country} خریدی به ارزش حدود {amount} انجام داد و انبار خود را تقویت کرد.",
                f"گزارش اقتصادی: فرمانده {player} برای {country} معامله‌ای بزرگ به مبلغ حدود {amount} ثبت کرد.",
            ]
        else:
            templates = [
                f"{country} در فروشگاه جهانی خرید سنگینی انجام داد؛ تحلیل‌گران از آماده‌سازی نظامی سخن می‌گویند.",
                f"تجارت جنگ‌افزار: {country} تجهیزات تازه‌ای به زرادخانه خود افزود.",
            ]
        return random.choice(templates)

    if kind == "sell":
        templates = [
            f"{country} آگهی تازه‌ای در بازار آزاد ثبت کرد؛ عرضهٔ تجهیزات ممکن است قیمت‌ها را تغییر دهد.",
            f"بازار آزاد: پیشنهاد فروش جدیدی از سوی {country} منتشر شد.",
        ]
        return random.choice(templates)

    if kind == "oil_trade" or ("نفت" in summary and kind in ("trade", "aid_oil", "sell", "buy")):
        templates = [
            f"بازار انرژی: {country} در معاملات نفتی فعال ظاهر شد و بشکه‌های سیاه جابه‌جا کرد.",
            f"گزارش نفتی — {country} نقش پررنگی در تجارت سوخت منطقه ایفا کرد.",
        ]
        return random.choice(templates)

    # --- aid ---
    if kind in ("aid_money", "aid_army", "aid_oil") or "کمک" in summary:
        if kind == "aid_oil" or "نفت" in summary:
            line = f"دیپلماسی انرژی: {country} محموله نفتی کمکی ارسال کرد و متحدان خود را تقویت نمود."
        elif kind == "aid_army" or "نظامی" in summary:
            line = f"کمک نظامی: {country} تجهیزات رزمی برای یک متحد ارسال کرد."
        else:
            line = (
                f"کمک مالی قابل‌توجهی از سوی {country} جابه‌جا شد"
                + (f" (حدود {amount})" if amount else "")
                + "؛ روابط دیپلماتیک گرم‌تر شد."
            )
        return line

    # --- claim / politics ---
    if kind == "claim":
        templates = [
            f"تغییر نقشه قدرت: {country} تحت فرماندهی جدید قرار گرفت و فصل تازه‌ای آغاز شد.",
            f"مراسم انتقال قدرت در {country} برگزار شد؛ جهان چشم به سیاست‌های تازه دوخته است.",
        ]
        return random.choice(templates)

    if kind in ("ban", "unban"):
        if kind == "ban" or "بن" in summary:
            return f"اعلامیه امنیتی: یک بازیکن به‌دلیل نقض قوانین از سوی ناظران جهان مسدود شد. (مرتبط با {country})"
        return f"رفع محدودیت: دسترسی یک فرمانده از سر گرفته شد و به عرصهٔ رقابت بازگشت."

    if kind in ("alliance", "peace"):
        templates = [
            f"تحول دیپلماتیک: {country} در مسیر اتحاد یا صلح گام تازه‌ای برداشت.",
            f"مذاکرات سیاسی اطراف {country} جدی‌تر شده است؛ احتمال پیمان جدید وجود دارد.",
        ]
        return random.choice(templates)

    if kind == "statement":
        templates = [
            f"بیانیه رسمی از {country} منتشر شد و موجی از واکنش‌های دیپلماتیک برانگیخت.",
            f"سخنگوی {country} مواضع تازه‌ای اعلام کرد؛ رسانه‌ها آن را تیتر کردند.",
        ]
        return random.choice(templates)

    # generic narrative — never dump raw summary alone
    templates = [
        f"رویداد مهم در {country}: ناظران بین‌المللی از تحرک تازهٔ این قدرت خبر دادند.",
        f"گزارش میدانی — {country} در ساعات اخیر در کانون توجه جهان قرار گرفت.",
        f"خبرگزاری جهان: تحولات مربوط به {country} می‌تواند معادلات منطقه را عوض کند.",
    ]
    return random.choice(templates)


async def collect_real_headlines(db, *, lookback_hours: int = 3, limit: int = 40) -> list[str]:
    since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    placeholders = ",".join(f"'{k}'" for k in REAL_KINDS)
    try:
        rows = await db.fetch(
            f"""
            SELECT kind, summary, country_code, player_id, created_at
            FROM ng_activity
            WHERE created_at >= $1
              AND kind IN ({placeholders})
              AND kind NOT LIKE 'group_%'
              AND kind NOT LIKE 'dm_%'
            ORDER BY id DESC
            LIMIT $2
            """,
            (since, limit),
        )
    except Exception:
        log.exception("collect real news")
        rows = []

    out: list[str] = []
    seen_local: set[str] = set()
    for r in rows or []:
        try:
            line = await narrate_event(db, dict(r))
        except Exception:
            log.exception("narrate_event")
            line = None
        if not line:
            continue
        line = line.strip()
        if len(line) < 20:
            continue
        key = _fp(line)
        if key in seen_local:
            continue
        seen_local.add(key)
        out.append(line[:400])
    return out


async def roleplay_headline(db) -> str:
    names = await _country_names(db)
    a = random.choice(names)
    b = random.choice(names)
    if b == a and len(names) > 1:
        b = names[(names.index(a) + 1) % len(names)]
    tpl = random.choice(RP_TEMPLATES)
    return tpl.format(a=a, b=b)


async def pick_unique_headline(db) -> tuple[str, str]:
    reals = await collect_real_headlines(db)
    random.shuffle(reals)
    for line in reals:
        if not await _seen(db, _fp(line)):
            return line, "real"
    for _ in range(25):
        line = await roleplay_headline(db)
        if not await _seen(db, _fp(line)):
            return line, "roleplay"
    line = (
        f"گزارش ویژه سازمان ملل در {datetime.now(TEHRAN).strftime('%H:%M')} — "
        "وضعیت جهان آرام اما پر از تنش پنهان توصیف شد."
    )
    return line, "roleplay"


def format_bulletin(body: str) -> str:
    now = datetime.now(TEHRAN)
    return (
        "📰 اخبار جهان\n"
        "━━━━━━━━━━━━\n"
        f"{body}\n"
        "━━━━━━━━━━━━\n"
        f"🕐 {now.strftime('%Y/%m/%d %H:%M')} (تهران)"
    )


async def already_sent_this_hour(db) -> bool:
    await ensure_tables(db)
    hk = hour_key()
    row = await db.fetchrow("SELECT last_hour_key FROM ng_world_news_meta WHERE id=1")
    return bool(row and row.get("last_hour_key") == hk)


async def mark_hour_sent(db, body: str) -> None:
    await ensure_tables(db)
    hk = hour_key()
    await db.execute(
        "UPDATE ng_world_news_meta SET last_hour_key=$1, last_body=$2 WHERE id=1",
        (hk, body[:500]),
    )


async def list_player_ids(db) -> list[int]:
    try:
        rows = await db.fetch("SELECT player_id FROM ng_players")
        return [int(r["player_id"]) for r in (rows or []) if r.get("player_id")]
    except Exception:
        log.exception("list players for news")
        return []


async def publish_hourly_news(game) -> str | None:
    db = game.db
    await ensure_tables(db)
    if await already_sent_this_hour(db):
        return None
    body, source = await pick_unique_headline(db)
    text = format_bulletin(body)
    await _remember(db, body, source)
    await mark_hour_sent(db, body)

    try:
        await game.log_activity("group_news", text)
    except Exception:
        log.exception("queue group news")
    try:
        await game.broadcast_log("news", text)
    except Exception:
        log.exception("broadcast_log news")

    pids = await list_player_ids(db)
    for pid in pids:
        try:
            await game.log_activity("dm_notice", text, player_id=int(pid))
        except Exception:
            log.exception("queue dm news pid=%s", pid)

    log.info("world news published source=%s players=%s", source, len(pids))
    return text
