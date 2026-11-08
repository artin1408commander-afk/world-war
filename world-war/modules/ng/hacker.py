"""Dedicated Anonymous Hacker Group system."""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
TEHRAN = ZoneInfo("Asia/Tehran")

HACKER_CODE = "ANON"
HACKER_NAME_FA = "گروه هکری آنانیموس"
HACKER_FLAG = "🎭"
ALLOWED_OWNER_ID = 1401214874
ALLOWED_USERNAME = "mahbod_farajian"  # display aid only

# Configurable defaults (override via settings attrs when present)
STEAL_WAIT_MIN_SEC = 15 * 60
STEAL_WAIT_MAX_SEC = 30 * 60
STEAL_AMOUNT_MIN = 1_000_000
STEAL_AMOUNT_MAX = 15_000_000
STEAL_XP_BASE = 25
BANK_MIN_LEVEL = 2
BANK_COOLDOWN_SEC = 6 * 3600
BANK_PERCENT_BASE = 0.005  # 0.5% of eligible world treasury pool cap per country share
LEVEL_UP_BASE_COST = 5_000_000
LEVEL_UP_COST_GROWTH = 1.45
ANNOUNCE_COOLDOWN_SEC = 10 * 60
ANNOUNCE_MAX_LEN = 900


class HackerError(Exception):
    pass


def xp_needed_for_level(level: int) -> int:
    """XP required to go from `level` to level+1. Recoverable curve."""
    level = max(1, int(level))
    # 100, 250, 450, 700, ...
    return int(50 * level * (level + 1))


def level_up_cost(level: int) -> float:
    level = max(1, int(level))
    return float(LEVEL_UP_BASE_COST * (LEVEL_UP_COST_GROWTH ** (level - 1)))


class HackerService:
    def __init__(self, game: Any):
        self.g = game
        self.db = game.db

    def _cfg(self, name: str, default):
        s = getattr(self.g, "settings", None)
        if s is not None and hasattr(s, name):
            try:
                return type(default)(getattr(s, name))
            except Exception:
                return getattr(s, name)
        return default

    async def ensure_tables(self) -> None:
        for sql in (
            """CREATE TABLE IF NOT EXISTS ng_hacker_groups (
                country_code TEXT PRIMARY KEY,
                owner_player_id INTEGER NOT NULL,
                level INTEGER NOT NULL DEFAULT 1,
                xp INTEGER NOT NULL DEFAULT 0,
                ops_success INTEGER NOT NULL DEFAULT 0,
                total_stolen REAL NOT NULL DEFAULT 0,
                last_steal_at TEXT,
                next_steal_at TEXT,
                last_bank_at TEXT,
                next_bank_at TEXT,
                last_daily_date TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS ng_hacker_ops (
                id INTEGER PRIMARY KEY,
                op_key TEXT NOT NULL UNIQUE,
                country_code TEXT NOT NULL,
                op_type TEXT NOT NULL,
                target_code TEXT,
                amount REAL NOT NULL DEFAULT 0,
                xp_gain INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS ng_hacker_tx (
                id INTEGER PRIMARY KEY,
                country_code TEXT NOT NULL,
                kind TEXT NOT NULL,
                amount REAL NOT NULL,
                balance_after REAL NOT NULL,
                meta TEXT,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS ng_hacker_announcements (
                id INTEGER PRIMARY KEY,
                country_code TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                sent_ok INTEGER NOT NULL DEFAULT 0,
                sent_fail INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )""",
        ):
            try:
                await self.db.execute(sql)
            except Exception:
                log.exception("hacker ensure_tables")

    async def ensure_seed_country(self) -> None:
        """Create ANON entity without owner until claimed by allowed user."""
        await self.ensure_tables()
        now = datetime.now(timezone.utc).isoformat()
        row = await self.db.fetchrow(
            "SELECT * FROM ng_countries WHERE country_code=$1", (HACKER_CODE,)
        )
        if not row:
            await self.db.execute(
                """
                INSERT INTO ng_countries (
                    country_code, name_fa, name_en, flag, capital_fa, leader_fa, leader_title_fa,
                    currency_code, currency_name_fa, npt_member, owner_player_id, treasury, hp, max_hp,
                    is_destroyed, claimed_at, entity_type
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,0,NULL,$10,1000,1000,0,NULL,'hacker')
                """,
                (
                    HACKER_CODE,
                    HACKER_NAME_FA,
                    "Anonymous Hacker Group",
                    HACKER_FLAG,
                    "فضای سایبری",
                    "Anonymous",
                    "رهبر هکر",
                    "ANX",
                    "واحد سایبری",
                    50_000_000.0,
                ),
            )
        else:
            try:
                await self.db.execute(
                    """
                    UPDATE ng_countries
                    SET entity_type='hacker', npt_member=0, name_fa=$1, flag=$2
                    WHERE country_code=$3
                    """,
                    (HACKER_NAME_FA, HACKER_FLAG, HACKER_CODE),
                )
            except Exception:
                log.exception("update ANON entity")

    def is_allowed_player(self, pid: int) -> bool:
        return int(pid) == int(ALLOWED_OWNER_ID)

    def is_hacker_code(self, code: str | None) -> bool:
        return (code or "").upper() == HACKER_CODE

    async def get_group(self, code: str = HACKER_CODE) -> Optional[dict]:
        return await self.db.fetchrow(
            "SELECT * FROM ng_hacker_groups WHERE country_code=$1", (code,)
        )

    async def assert_owner(self, pid: int) -> dict:
        if not self.is_allowed_player(pid):
            raise HackerError("فقط حساب مجاز می‌تواند گروه هکری آنانیموس را مدیریت کند.")
        c = await self.db.fetchrow(
            "SELECT * FROM ng_countries WHERE country_code=$1", (HACKER_CODE,)
        )
        if not c or not c.get("owner_player_id") or int(c["owner_player_id"]) != int(pid):
            raise HackerError("ابتدا گروه هکری آنانیموس را از بخش انتخاب کشور انتخاب کنید.")
        g = await self.get_group()
        if not g:
            raise HackerError("پروفایل گروه هکری هنوز ساخته نشده است.")
        if int(g.get("active") or 0) != 1:
            raise HackerError("گروه هکری فعلاً غیرفعال است.")
        return g

    async def on_claim(self, pid: int) -> dict:
        """Called after successful claim of ANON — create or keep progress."""
        if not self.is_allowed_player(pid):
            raise HackerError(
                "انتخاب گروه هکری آنانیموس فقط برای کاربر مجاز است."
            )
        now = datetime.now(timezone.utc).isoformat()
        existing = await self.get_group()
        if existing:
            # Do not reset progress
            await self.db.execute(
                "UPDATE ng_hacker_groups SET owner_player_id=$1, updated_at=$2 WHERE country_code=$3",
                (int(pid), now, HACKER_CODE),
            )
            return await self.get_group()
        await self.db.execute(
            """
            INSERT INTO ng_hacker_groups (
                country_code, owner_player_id, level, xp, ops_success, total_stolen,
                active, created_at, updated_at
            ) VALUES ($1,$2,1,0,0,0,1,$3,$3)
            """,
            (HACKER_CODE, int(pid), now),
        )
        return await self.get_group()

    async def profile_text(self, pid: int) -> str:
        g = await self.assert_owner(pid)
        c = await self.db.fetchrow(
            "SELECT * FROM ng_countries WHERE country_code=$1", (HACKER_CODE,)
        )
        p = await self.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (int(pid),))
        level = int(g["level"] or 1)
        xp = int(g["xp"] or 0)
        need = xp_needed_for_level(level)
        name = (p or {}).get("display_name") or (p or {}).get("username") or str(pid)
        daily = float(getattr(self.g, "daily_income_base", 20_000_000) or 20_000_000) * (
            0.5 + 0.15 * level
        )
        return (
            f"{HACKER_FLAG} پروفایل — {HACKER_NAME_FA}\n\n"
            f"بازیکن: {name}\n"
            f"User ID: {pid}\n"
            f"لول: {level}\n"
            f"XP: {xp:,} / {need:,}\n"
            f"درآمد روزانه (تقریبی): {int(daily):,}\n"
            f"خزانه: {int(float((c or {}).get('treasury') or 0)):,}\n"
            f"عملیات موفق: {int(g.get('ops_success') or 0)}\n"
            f"مجموع دزدی: {int(float(g.get('total_stolen') or 0)):,}"
        )

    async def levelup_preview(self, pid: int) -> str:
        g = await self.assert_owner(pid)
        c = await self.db.fetchrow(
            "SELECT treasury FROM ng_countries WHERE country_code=$1", (HACKER_CODE,)
        )
        level = int(g["level"] or 1)
        xp = int(g["xp"] or 0)
        need = xp_needed_for_level(level)
        cost = level_up_cost(level)
        treas = float((c or {}).get("treasury") or 0)
        miss = max(0.0, cost - treas)
        lines = [
            "⬆️ ارتقای لول گروه هکری",
            "",
            f"لول فعلی: {level}",
            f"لول بعدی: {level + 1}",
            f"XP: {xp:,} / {need:,}",
            f"هزینه ارتقا: {int(cost):,}",
            f"خزانه: {int(treas):,}",
        ]
        if xp < need:
            lines.append(f"⛔ XP کافی نیست (کمبود {need - xp:,})")
        if miss > 0:
            lines.append(f"⛔ پول کافی نیست (کمبود {int(miss):,})")
        if xp >= need and miss <= 0:
            lines.append("✅ آماده تأیید ارتقا")
        return "\n".join(lines)

    async def level_up(self, pid: int) -> str:
        g = await self.assert_owner(pid)
        level = int(g["level"] or 1)
        xp = int(g["xp"] or 0)
        need = xp_needed_for_level(level)
        cost = level_up_cost(level)
        if xp < need:
            raise HackerError(f"XP کافی نیست. نیاز: {need:,}")
        now = datetime.now(timezone.utc).isoformat()
        op_key = f"lvlup:{HACKER_CODE}:{level}:{uuid.uuid4().hex[:10]}"
        async with self.db.transaction() as tx:
            c = await tx.fetchrow(
                "SELECT treasury FROM ng_countries WHERE country_code=$1", (HACKER_CODE,)
            )
            treas = float((c or {}).get("treasury") or 0)
            if treas < cost:
                raise HackerError(f"پول کافی نیست. نیاز: {int(cost):,}")
            # prevent double
            exists = await tx.fetchrow(
                "SELECT id FROM ng_hacker_ops WHERE op_key=$1", (op_key,)
            )
            if exists:
                raise HackerError("عملیات تکراری")
            new_treas = treas - cost
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (new_treas, HACKER_CODE),
            )
            new_level = level + 1
            new_xp = max(0, xp - need)
            await tx.execute(
                """
                UPDATE ng_hacker_groups
                SET level=$1, xp=$2, updated_at=$3 WHERE country_code=$4
                """,
                (new_level, new_xp, now, HACKER_CODE),
            )
            nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_hacker_ops")
            await tx.execute(
                """
                INSERT INTO ng_hacker_ops (id, op_key, country_code, op_type, target_code, amount, xp_gain, created_at)
                VALUES ($1,$2,$3,'level_up',NULL,$4,0,$5)
                """,
                (int(nid["id"]), op_key, HACKER_CODE, cost, now),
            )
            tid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_hacker_tx")
            await tx.execute(
                """
                INSERT INTO ng_hacker_tx (id, country_code, kind, amount, balance_after, meta, created_at)
                VALUES ($1,$2,'level_up',$3,$4,$5,$6)
                """,
                (int(tid["id"]), HACKER_CODE, -cost, new_treas, f"to L{new_level}", now),
            )
        return f"✅ ارتقا انجام شد.\nلول جدید: {level + 1}\nهزینه: {int(cost):,}"

    def _steal_bounds(self, level: int) -> tuple[float, float]:
        level = max(1, int(level))
        mn = STEAL_AMOUNT_MIN * (1 + 0.12 * (level - 1))
        mx = STEAL_AMOUNT_MAX * (1 + 0.18 * (level - 1))
        return float(mn), float(mx)

    async def steal_country(self, pid: int, target: str) -> str:
        g = await self.assert_owner(pid)
        target = (target or "").upper()
        if target == HACKER_CODE:
            raise HackerError("هدف نامعتبر است.")
        now = datetime.now(timezone.utc)
        next_at = g.get("next_steal_at")
        if next_at:
            try:
                na = datetime.fromisoformat(str(next_at).replace("Z", "+00:00"))
                if na.tzinfo is None:
                    na = na.replace(tzinfo=timezone.utc)
                if na > now:
                    left = int((na - now).total_seconds())
                    raise HackerError(f"هنوز در کول‌داون دزدی هستید ({left // 60} دقیقه).")
            except HackerError:
                raise
            except Exception:
                pass
        level = int(g["level"] or 1)
        mn, mx = self._steal_bounds(level)
        amount = random.uniform(mn, mx)
        wait = random.randint(STEAL_WAIT_MIN_SEC, STEAL_WAIT_MAX_SEC)
        xp_gain = int(STEAL_XP_BASE * (1 + 0.1 * (level - 1)))
        op_key = f"steal:{HACKER_CODE}:{target}:{now.strftime('%Y%m%d%H%M%S')}:{uuid.uuid4().hex[:8]}"
        async with self.db.transaction() as tx:
            trow = await tx.fetchrow(
                "SELECT * FROM ng_countries WHERE country_code=$1", (target,)
            )
            if not trow or int(trow.get("is_destroyed") or 0):
                raise HackerError("کشور هدف موجود نیست.")
            if not trow.get("owner_player_id"):
                raise HackerError("کشور هدف مالک ندارد.")
            treas = float(trow.get("treasury") or 0)
            if treas <= 0:
                raise HackerError("خزانه هدف خالی است.")
            taken = min(amount, treas)
            new_t = treas - taken
            hrow = await tx.fetchrow(
                "SELECT treasury FROM ng_countries WHERE country_code=$1", (HACKER_CODE,)
            )
            h_treas = float((hrow or {}).get("treasury") or 0) + taken
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (new_t, target),
            )
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (h_treas, HACKER_CODE),
            )
            next_iso = (now + timedelta(seconds=wait)).isoformat()
            await tx.execute(
                """
                UPDATE ng_hacker_groups
                SET xp=xp+$1, ops_success=ops_success+1, total_stolen=total_stolen+$2,
                    last_steal_at=$3, next_steal_at=$4, updated_at=$3
                WHERE country_code=$5
                """,
                (xp_gain, taken, now.isoformat(), next_iso, HACKER_CODE),
            )
            nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_hacker_ops")
            await tx.execute(
                """
                INSERT INTO ng_hacker_ops (id, op_key, country_code, op_type, target_code, amount, xp_gain, created_at)
                VALUES ($1,$2,$3,'steal',$4,$5,$6,$7)
                """,
                (int(nid["id"]), op_key, HACKER_CODE, target, taken, xp_gain, now.isoformat()),
            )
            tid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_hacker_tx")
            await tx.execute(
                """
                INSERT INTO ng_hacker_tx (id, country_code, kind, amount, balance_after, meta, created_at)
                VALUES ($1,$2,'steal',$3,$4,$5,$6)
                """,
                (int(tid["id"]), HACKER_CODE, taken, h_treas, target, now.isoformat()),
            )
        try:
            label = await self.g.country_label(target)
        except Exception:
            label = target
        return (
            f"✅ دزدی موفق از {label}\n"
            f"مبلغ: {int(taken):,}\n"
            f"XP: +{xp_gain}\n"
            f"کول‌داون بعدی: حدود {wait // 60} دقیقه"
        )

    async def bank_info(self, pid: int) -> str:
        g = await self.assert_owner(pid)
        level = int(g["level"] or 1)
        if level < BANK_MIN_LEVEL:
            return (
                "🏦 بانک جهانی\n\n"
                "بانک جهانی یک قابلیت ویژه گروه هکری است که اجازه می‌دهد "
                "از مجموع خزانه کشورهای موجود مبلغی مشخص به خزانه شما منتقل شود.\n\n"
                f"این قابلیت از Level {BANK_MIN_LEVEL} فعال می‌شود.\n"
                "ابتدا گروه را ارتقا دهید."
            )
        return (
            "🏦 بانک جهانی — فعال\n\n"
            "با تأیید، سهم کوچکی از خزانه‌های واجد شرایط کشورها "
            "به‌صورت اتمیک به خزانه گروه منتقل می‌شود.\n"
            "کول‌داون مستقل دارد."
        )

    async def bank_heist(self, pid: int) -> str:
        g = await self.assert_owner(pid)
        level = int(g["level"] or 1)
        if level < BANK_MIN_LEVEL:
            raise HackerError(f"بانک جهانی از Level {BANK_MIN_LEVEL} فعال است.")
        now = datetime.now(timezone.utc)
        next_at = g.get("next_bank_at")
        if next_at:
            try:
                na = datetime.fromisoformat(str(next_at).replace("Z", "+00:00"))
                if na.tzinfo is None:
                    na = na.replace(tzinfo=timezone.utc)
                if na > now:
                    left = int((na - now).total_seconds())
                    raise HackerError(f"کول‌داون بانک: {left // 60} دقیقه.")
            except HackerError:
                raise
            except Exception:
                pass
        pct = BANK_PERCENT_BASE * (1 + 0.15 * (level - BANK_MIN_LEVEL))
        pct = min(pct, 0.02)
        op_key = f"bank:{HACKER_CODE}:{now.strftime('%Y%m%d%H%M')}:{uuid.uuid4().hex[:8]}"
        async with self.db.transaction() as tx:
            exists = await tx.fetchrow(
                "SELECT id FROM ng_hacker_ops WHERE op_key=$1", (op_key,)
            )
            if exists:
                raise HackerError("عملیات تکراری")
            rows = await tx.fetch(
                """
                SELECT country_code, treasury FROM ng_countries
                WHERE owner_player_id IS NOT NULL
                  AND COALESCE(is_destroyed,0)=0
                  AND country_code <> $1
                  AND treasury > 0
                """,
                (HACKER_CODE,),
            )
            total_taken = 0.0
            for r in rows:
                treas = float(r["treasury"] or 0)
                take = min(treas, treas * pct)
                if take < 1:
                    continue
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (treas - take, r["country_code"]),
                )
                total_taken += take
            if total_taken <= 0:
                raise HackerError("هیچ خزانه‌ای برای برداشت موجود نیست.")
            hrow = await tx.fetchrow(
                "SELECT treasury FROM ng_countries WHERE country_code=$1", (HACKER_CODE,)
            )
            h_treas = float((hrow or {}).get("treasury") or 0) + total_taken
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (h_treas, HACKER_CODE),
            )
            next_iso = (now + timedelta(seconds=BANK_COOLDOWN_SEC)).isoformat()
            await tx.execute(
                """
                UPDATE ng_hacker_groups
                SET total_stolen=total_stolen+$1, ops_success=ops_success+1,
                    last_bank_at=$2, next_bank_at=$3, updated_at=$2
                WHERE country_code=$4
                """,
                (total_taken, now.isoformat(), next_iso, HACKER_CODE),
            )
            nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_hacker_ops")
            await tx.execute(
                """
                INSERT INTO ng_hacker_ops (id, op_key, country_code, op_type, target_code, amount, xp_gain, created_at)
                VALUES ($1,$2,$3,'bank',NULL,$4,0,$5)
                """,
                (int(nid["id"]), op_key, HACKER_CODE, total_taken, now.isoformat()),
            )
            tid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_hacker_tx")
            await tx.execute(
                """
                INSERT INTO ng_hacker_tx (id, country_code, kind, amount, balance_after, meta, created_at)
                VALUES ($1,$2,'bank',$3,$4,$5,$6)
                """,
                (
                    int(tid["id"]),
                    HACKER_CODE,
                    total_taken,
                    h_treas,
                    f"pct={pct:.4f}",
                    now.isoformat(),
                ),
            )
        return f"✅ دزدی بانک جهانی موفق\nمبلغ کل: {int(total_taken):,}\nکول‌داون: {BANK_COOLDOWN_SEC // 3600} ساعت"

    async def queue_announcement(self, pid: int, body: str) -> str:
        g = await self.assert_owner(pid)
        body = (body or "").strip()
        if len(body) < 10:
            raise HackerError("متن بیانیه خیلی کوتاه است.")
        if len(body) > ANNOUNCE_MAX_LEN:
            raise HackerError(f"حداکثر {ANNOUNCE_MAX_LEN} کاراکتر.")
        now = datetime.now(timezone.utc)
        # simple rate limit via last announcement
        last = await self.db.fetchrow(
            "SELECT created_at FROM ng_hacker_announcements WHERE country_code=$1 ORDER BY id DESC LIMIT 1",
            (HACKER_CODE,),
        )
        if last and last.get("created_at"):
            try:
                la = datetime.fromisoformat(str(last["created_at"]).replace("Z", "+00:00"))
                if la.tzinfo is None:
                    la = la.replace(tzinfo=timezone.utc)
                if (now - la).total_seconds() < ANNOUNCE_COOLDOWN_SEC:
                    raise HackerError("برای بیانیه بعدی کمی صبر کنید.")
            except HackerError:
                raise
            except Exception:
                pass
        text = (
            f"📢 بیانیه {HACKER_NAME_FA}\n\n"
            f"{body}\n\n"
            f"— {HACKER_FLAG}"
        )
        # Use existing broadcast pipeline without owner approval
        try:
            await self.g.broadcast_log("hacker_statement", text)
        except Exception:
            log.exception("hacker broadcast")
        nid = await self.db.fetchrow(
            "SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_hacker_announcements"
        )
        await self.db.execute(
            """
            INSERT INTO ng_hacker_announcements (id, country_code, player_id, body, sent_ok, sent_fail, created_at)
            VALUES ($1,$2,$3,$4,1,0,$5)
            """,
            (int(nid["id"]), HACKER_CODE, int(pid), body, now.isoformat()),
        )
        return "✅ بیانیه ثبت و برای انتشار در صف همگانی قرار گرفت."


    async def admin_profile_text(self) -> str:
        await self.ensure_tables()
        g = await self.get_group()
        c = await self.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (HACKER_CODE,))
        if not g:
            owner = (c or {}).get("owner_player_id")
            return (
                f"{HACKER_FLAG} {HACKER_NAME_FA}\n\n"
                f"وضعیت: هنوز انتخاب نشده یا پروفایل ساخته نشده.\n"
                f"مالک فعلی کشور: {owner or 'آزاد'}\n"
                f"خزانه: {int(float((c or {}).get('treasury') or 0)):,}"
            )
        level = int(g.get("level") or 1)
        xp = int(g.get("xp") or 0)
        need = xp_needed_for_level(level)
        return (
            f"{HACKER_FLAG} {HACKER_NAME_FA} — مدیریت\n\n"
            f"مالک: {g.get('owner_player_id')}\n"
            f"فعال: {'بله' if int(g.get('active') or 0) else 'خیر'}\n"
            f"لول: {level}\n"
            f"XP: {xp:,} / {need:,}\n"
            f"عملیات موفق: {int(g.get('ops_success') or 0)}\n"
            f"مجموع دزدی: {int(float(g.get('total_stolen') or 0)):,}\n"
            f"خزانه: {int(float((c or {}).get('treasury') or 0)):,}\n"
            f"کول‌داون دزدی تا: {g.get('next_steal_at') or '—'}\n"
            f"کول‌داون بانک تا: {g.get('next_bank_at') or '—'}"
        )

    async def admin_set_level(self, actor: int, level: int) -> str:
        if not self.g.is_owner(int(actor)):
            raise HackerError("فقط مالک")
        level = max(1, min(50, int(level)))
        now = datetime.now(timezone.utc).isoformat()
        g = await self.get_group()
        if not g:
            raise HackerError("گروه هنوز ساخته نشده (باید توسط کاربر مجاز انتخاب شود).")
        await self.db.execute(
            "UPDATE ng_hacker_groups SET level=$1, updated_at=$2 WHERE country_code=$3",
            (level, now, HACKER_CODE),
        )
        try:
            await self.g.admin_log(int(actor), "hacker_set_level", f"level={level}")
        except Exception:
            pass
        return f"✅ لول گروه هکری = {level}"

    async def admin_set_xp(self, actor: int, xp: int) -> str:
        if not self.g.is_owner(int(actor)):
            raise HackerError("فقط مالک")
        xp = max(0, int(xp))
        now = datetime.now(timezone.utc).isoformat()
        g = await self.get_group()
        if not g:
            raise HackerError("گروه هنوز ساخته نشده.")
        await self.db.execute(
            "UPDATE ng_hacker_groups SET xp=$1, updated_at=$2 WHERE country_code=$3",
            (xp, now, HACKER_CODE),
        )
        try:
            await self.g.admin_log(int(actor), "hacker_set_xp", f"xp={xp}")
        except Exception:
            pass
        return f"✅ XP گروه هکری = {xp:,}"

    async def admin_set_treasury(self, actor: int, amount: float) -> str:
        if not self.g.is_owner(int(actor)):
            raise HackerError("فقط مالک")
        amount = max(0.0, float(amount))
        await self.db.execute(
            "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
            (amount, HACKER_CODE),
        )
        try:
            await self.g.admin_log(int(actor), "hacker_set_treasury", f"treasury={amount}")
        except Exception:
            pass
        return f"✅ خزانه آنانیموس = {int(amount):,}"

    async def admin_set_active(self, actor: int, active: bool) -> str:
        if not self.g.is_owner(int(actor)):
            raise HackerError("فقط مالک")
        g = await self.get_group()
        if not g:
            raise HackerError("گروه هنوز ساخته نشده.")
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE ng_hacker_groups SET active=$1, updated_at=$2 WHERE country_code=$3",
            (1 if active else 0, now, HACKER_CODE),
        )
        return f"✅ گروه هکری {'فعال' if active else 'غیرفعال'} شد"

    async def admin_clear_cooldowns(self, actor: int) -> str:
        if not self.g.is_owner(int(actor)):
            raise HackerError("فقط مالک")
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE ng_hacker_groups SET next_steal_at=NULL, next_bank_at=NULL, updated_at=$1 WHERE country_code=$2",
            (now, HACKER_CODE),
        )
        return "✅ کول‌داون دزدی و بانک پاک شد"

