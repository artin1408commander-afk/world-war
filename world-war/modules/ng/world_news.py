"""Hourly world news — real gameplay events, or unique roleplay if none."""
from __future__ import annotations

import hashlib
import logging
import random
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
TEHRAN = ZoneInfo("Asia/Tehran")

# Kinds from ng_activity that make good "real" news
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
    "daily",
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
    # SQLite-compatible fallback without BIGSERIAL if needed — Postgres on Railway
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


def _clean_summary(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s[:280]


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
        # SQLite-style without ON CONFLICT target
        try:
            if not await _seen(db, fp):
                await db.execute(
                    "INSERT INTO ng_world_news (fingerprint, body, source, created_at) VALUES ($1,$2,$3,$4)",
                    (fp, body, source, now),
                )
        except Exception:
            log.exception("remember news")


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


async def collect_real_headlines(db, *, lookback_hours: int = 3, limit: int = 30) -> list[str]:
    """Pull recent real gameplay activity and turn into news lines."""
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
    for r in rows or []:
        kind = str(r.get("kind") or "")
        summary = _clean_summary(r.get("summary") or "")
        if not summary or len(summary) < 8:
            continue
        # Skip pure internal noise
        if summary.startswith("❌") or "خطا" in summary[:12]:
            continue
        if kind in ("attack", "nuke", "nuclear", "destroy"):
            line = f"⚔️ {summary}"
        elif kind in ("buy", "checkout", "shop", "sell"):
            line = f"🛒 {summary}"
        elif kind.startswith("aid"):
            line = f"🤝 {summary}"
        elif kind in ("claim",):
            line = f"🏛 {summary}"
        elif kind in ("ban", "unban"):
            line = f"🚫 {summary}"
        else:
            line = f"📌 {summary}"
        out.append(line[:320])
    return out


async def roleplay_headline(db) -> str:
    names = await _country_names(db)
    a = random.choice(names)
    b = random.choice(names)
    if b == a and len(names) > 1:
        b = names[(names.index(a) + 1) % len(names)]
    tpl = random.choice(RP_TEMPLATES)
    return "🎭 " + tpl.format(a=a, b=b)


async def pick_unique_headline(db) -> tuple[str, str]:
    """Return (body_without_header, source). Guarantees uniqueness vs history."""
    reals = await collect_real_headlines(db)
    random.shuffle(reals)
    for line in reals:
        if not await _seen(db, _fp(line)):
            return line, "real"
    # roleplay attempts
    for _ in range(25):
        line = await roleplay_headline(db)
        if not await _seen(db, _fp(line)):
            return line, "roleplay"
    # last resort: timestamped unique
    line = f"📡 گزارش ویژه سازمان ملل در {datetime.now(TEHRAN).strftime('%H:%M')} — وضعیت جهان پایدار اما پرتنش است."
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
    """Build one unique news item and queue for groups + all player DMs."""
    db = game.db
    await ensure_tables(db)
    if await already_sent_this_hour(db):
        return None
    body, source = await pick_unique_headline(db)
    text = format_bulletin(body)
    await _remember(db, body, source)
    await mark_hour_sent(db, body)

    # Groups via existing group log pipeline
    try:
        await game.log_activity("group_news", text)
    except Exception:
        log.exception("queue group news")

    # Also try broadcast_log path
    try:
        await game.broadcast_log("news", text)
    except Exception:
        log.exception("broadcast_log news")

    # DM every player (queued; dm_notice_loop sends)
    pids = await list_player_ids(db)
    for pid in pids:
        try:
            await game.log_activity("dm_notice", text, player_id=int(pid))
        except Exception:
            log.exception("queue dm news pid=%s", pid)

    log.info("world news published source=%s players=%s", source, len(pids))
    return text
