"""Lucky wheel — one spin every 6 hours per player."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

COOLDOWN = timedelta(hours=6)

PRIZES = [
    ("money_100m", "۱۰۰ میلیون پول", "money", 100_000_000),
    ("oil_100", "۱۰۰ بشکه نفت", "oil", 100),
    ("nuke_3", "۳ بمب اتم", "item", ("nuke_bomb", 3)),
    ("uranium_5", "۵ اورانیوم", "item", ("res_uranium", 5)),
    ("refinery_l", "۱ پالایشگاه نفت بزرگ", "item", ("b_refinery_l", 1)),
    ("money_1b", "۱ میلیارد پول", "money", 1_000_000_000),
]


async def ensure_tables(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ng_lucky_spin (
            player_id BIGINT PRIMARY KEY,
            last_spin_at TEXT,
            last_prize TEXT,
            spin_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


async def status(db, pid: int) -> dict:
    await ensure_tables(db)
    row = await db.fetchrow("SELECT * FROM ng_lucky_spin WHERE player_id=$1", (int(pid),))
    now = datetime.now(timezone.utc)
    last = _parse_ts((row or {}).get("last_spin_at") if row else None)
    ready, wait_sec = True, 0
    if last:
        nxt = last + COOLDOWN
        if now < nxt:
            ready = False
            wait_sec = int((nxt - now).total_seconds())
    return {
        "ready": ready,
        "wait_sec": wait_sec,
        "last_prize": (row or {}).get("last_prize"),
        "spin_count": int((row or {}).get("spin_count") or 0),
    }


def format_wait(sec: int) -> str:
    h, r = divmod(max(0, sec), 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h} ساعت و {m} دقیقه"
    if m:
        return f"{m} دقیقه و {s} ثانیه"
    return f"{s} ثانیه"


async def mark_spin(db, pid: int, prize_label: str) -> None:
    await ensure_tables(db)
    now = datetime.now(timezone.utc).isoformat()
    exists = await db.fetchrow("SELECT player_id FROM ng_lucky_spin WHERE player_id=$1", (int(pid),))
    if exists:
        await db.execute(
            """
            UPDATE ng_lucky_spin
            SET last_spin_at=$1, last_prize=$2, spin_count=COALESCE(spin_count,0)+1
            WHERE player_id=$3
            """,
            (now, prize_label, int(pid)),
        )
    else:
        await db.execute(
            """
            INSERT INTO ng_lucky_spin (player_id, last_spin_at, last_prize, spin_count)
            VALUES ($1,$2,$3,1)
            """,
            (int(pid), now, prize_label),
        )


def pick_prize() -> tuple:
    return random.choice(PRIZES)


def panel_text(st: dict) -> str:
    lines = [
        "🎰 چرخ شانس",
        "━━━━━━━━━━━━",
        "هر ۶ ساعت یک‌بار می‌توانید بچرخانید.",
        "",
        "جوایز ممکن:",
    ]
    for _, label, _, _ in PRIZES:
        lines.append(f"• {label}")
    lines.append("")
    if st.get("ready"):
        lines.append("✅ الان می‌توانید بچرخانید!")
    else:
        lines.append(f"⏳ زمان باقی‌مانده: {format_wait(int(st.get('wait_sec') or 0))}")
    if st.get("last_prize"):
        lines.append(f"آخرین جایزه: {st['last_prize']}")
    lines.append(f"تعداد چرخش‌ها: {int(st.get('spin_count') or 0)}")
    return "\n".join(lines)
