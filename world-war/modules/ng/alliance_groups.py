"""Reserved Bale groups pool for automatic alliance group assignment."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.ng.game import Game

log = logging.getLogger(__name__)


class AllianceGroupError(Exception):
    pass


class AllianceGroupPool:
    def __init__(self, game: "Game"):
        self.g = game
        self.db = game.db

    async def ensure_schema(self) -> None:
        try:
            await self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS ng_alliance_pool_groups (
                    id INTEGER PRIMARY KEY,
                    chat_id TEXT NOT NULL UNIQUE,
                    reserve_name TEXT NOT NULL DEFAULT 'گروه رزرو اتحاد',
                    status TEXT NOT NULL DEFAULT 'free',
                    alliance_id INTEGER,
                    invite_link TEXT,
                    last_error TEXT,
                    assigned_at TEXT,
                    last_checked_at TEXT,
                    created_at TEXT
                )
                """
            )
        except Exception:
            log.exception("create pool table")
        for col, typ in (
            ("group_chat_id", "TEXT"),
            ("group_invite_link", "TEXT"),
            ("group_pool_id", "INTEGER"),
        ):
            try:
                await self.db.execute(f"ALTER TABLE ng_alliances ADD COLUMN {col} {typ}")
            except Exception:
                pass

    def bot(self, bot=None):
        return bot or getattr(self.g, "bot", None)

    async def list_groups(self) -> list[dict]:
        await self.ensure_schema()
        return await self.db.fetch("SELECT * FROM ng_alliance_pool_groups ORDER BY id")

    async def stats(self) -> dict:
        rows = await self.list_groups()
        return {
            "total": len(rows),
            "free": sum(1 for r in rows if r.get("status") == "free"),
            "assigned": sum(1 for r in rows if r.get("status") == "assigned"),
            "holding": sum(1 for r in rows if r.get("status") == "holding"),
            "unusable": sum(1 for r in rows if r.get("status") == "unusable"),
            "rows": rows,
        }

    async def register(self, actor: int, chat_id: str, reserve_name: str = "گروه رزرو اتحاد") -> str:
        if not self.g.is_owner(int(actor)):
            raise AllianceGroupError("فقط مالک")
        await self.ensure_schema()
        chat_id = str(chat_id).strip()
        if not chat_id:
            raise AllianceGroupError("شناسه گروه نامعتبر")
        reserve_name = (reserve_name or "گروه رزرو اتحاد").strip()[:80] or "گروه رزرو اتحاد"
        if await self.db.fetchrow(
            "SELECT id FROM ng_alliance_pool_groups WHERE chat_id=$1", (chat_id,)
        ):
            raise AllianceGroupError("این گروه قبلاً ثبت شده")
        nid = await self.db.fetchrow(
            "SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_alliance_pool_groups"
        )
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO ng_alliance_pool_groups
            (id, chat_id, reserve_name, status, created_at)
            VALUES ($1,$2,$3,'free',$4)
            """,
            (int(nid["id"]), chat_id, reserve_name, now),
        )
        return (
            "✅ گروه رزرو ثبت شد."
            + chr(10)
            + f"شناسه: {chat_id}"
            + chr(10)
            + f"نام رزرو: {reserve_name}"
        )

    async def set_status(self, actor: int, pool_id: int, status: str) -> str:
        if not self.g.is_owner(int(actor)):
            raise AllianceGroupError("فقط مالک")
        if status not in ("free", "unusable"):
            raise AllianceGroupError("وضعیت نامعتبر")
        row = await self.db.fetchrow(
            "SELECT * FROM ng_alliance_pool_groups WHERE id=$1", (int(pool_id),)
        )
        if not row:
            raise AllianceGroupError("گروه یافت نشد")
        if row.get("status") == "assigned" and status == "free":
            raise AllianceGroupError("ابتدا اتحاد متصل را منحل کنید")
        await self.db.execute(
            "UPDATE ng_alliance_pool_groups SET status=$1, alliance_id=NULL, invite_link=NULL WHERE id=$2",
            (status, int(pool_id)),
        )
        return f"وضعیت گروه #{pool_id} → {status}"

    async def claim_free(self) -> dict | None:
        await self.ensure_schema()
        rows = await self.db.fetch(
            "SELECT * FROM ng_alliance_pool_groups WHERE status='free' ORDER BY id LIMIT 8"
        )
        for r in rows:
            await self.db.execute(
                "UPDATE ng_alliance_pool_groups SET status='holding' WHERE id=$1 AND status='free'",
                (int(r["id"]),),
            )
            check = await self.db.fetchrow(
                "SELECT * FROM ng_alliance_pool_groups WHERE id=$1", (int(r["id"]),)
            )
            if check and check.get("status") == "holding":
                return check
        return None

    async def release(self, pool_id: int, *, free: bool = True, err: str | None = None) -> None:
        st = "free" if free else "unusable"
        await self.db.execute(
            """
            UPDATE ng_alliance_pool_groups
            SET status=$1, alliance_id=NULL, invite_link=NULL, assigned_at=NULL, last_error=$2
            WHERE id=$3
            """,
            (st, err, int(pool_id)),
        )

    async def finalize(self, pool_id: int, alliance_id: int, invite_link: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            UPDATE ng_alliance_pool_groups
            SET status='assigned', alliance_id=$1, invite_link=$2, assigned_at=$3, last_error=NULL
            WHERE id=$4
            """,
            (int(alliance_id), invite_link, now, int(pool_id)),
        )

    async def _set_title(self, bot, chat_id, title: str) -> None:
        cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id
        title = str(title)[:120]
        last = None
        for name in ("set_chat_title", "setChatTitle", "edit_chat_title"):
            fn = getattr(bot, name, None)
            if not callable(fn):
                continue
            try:
                r = fn(cid, title)
                if hasattr(r, "__await__"):
                    await r
                return
            except Exception as e:
                last = e
        raise AllianceGroupError(f"تغییر نام گروه ممکن نشد: {last}")

    async def _invite(self, bot, chat_id) -> str:
        cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id
        last = None
        for name in (
            "create_chat_invite_link",
            "export_chat_invite_link",
            "createChatInviteLink",
            "exportChatInviteLink",
        ):
            fn = getattr(bot, name, None)
            if not callable(fn):
                continue
            try:
                r = fn(cid)
                if hasattr(r, "__await__"):
                    r = await r
                if isinstance(r, str) and r.strip():
                    return r.strip()
                link = getattr(r, "invite_link", None) or getattr(r, "link", None)
                if link:
                    return str(link).strip()
            except Exception as e:
                last = e
        for name in ("get_chat", "getChat"):
            fn = getattr(bot, name, None)
            if not callable(fn):
                continue
            try:
                r = fn(cid)
                if hasattr(r, "__await__"):
                    r = await r
                link = getattr(r, "invite_link", None)
                if link:
                    return str(link).strip()
            except Exception as e:
                last = e
        raise AllianceGroupError(f"ساخت لینک دعوت ناموفق: {last}")

    async def _send(self, bot, chat_id, text: str) -> None:
        cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id
        fn = getattr(bot, "send_message", None)
        if not callable(fn):
            return
        r = fn(cid, str(text)[:3500])
        if hasattr(r, "__await__"):
            await r

    async def setup_group(self, bot, pool: dict, alliance_name: str, owner_label: str) -> str:
        if not bot:
            raise AllianceGroupError("ربات برای مدیریت گروه در دسترس نیست.")
        chat_id = pool["chat_id"]
        try:
            await self._set_title(bot, chat_id, f"اتحاد {alliance_name}")
        except AllianceGroupError:
            await self.release(int(pool["id"]), free=False, err="rename_failed")
            raise
        try:
            await self._send(
                bot,
                chat_id,
                "🤝 اتحاد "
                + str(alliance_name)
                + chr(10)
                + "مالک: "
                + str(owner_label)
                + chr(10)
                + chr(10)
                + "عضویت در این گروه برای همه اعضای اتحاد اجباری است.",
            )
        except Exception as e:
            log.warning("intro send fail: %s", e)
        try:
            link = await self._invite(bot, chat_id)
        except AllianceGroupError:
            await self.release(int(pool["id"]), free=True, err="invite_failed")
            try:
                await self._set_title(bot, chat_id, pool.get("reserve_name") or "گروه رزرو اتحاد")
            except Exception:
                pass
            raise
        if not link:
            await self.release(int(pool["id"]), free=True, err="empty_invite")
            raise AllianceGroupError("لینک دعوت خالی بود")
        return link

    async def free_after_dissolve(self, alliance: dict, bot=None) -> None:
        await self.ensure_schema()
        pool_id = alliance.get("group_pool_id")
        chat_id = alliance.get("group_chat_id")
        bot = self.bot(bot)
        reserve = "گروه رزرو اتحاد"
        if pool_id:
            row = await self.db.fetchrow(
                "SELECT * FROM ng_alliance_pool_groups WHERE id=$1", (int(pool_id),)
            )
            if row:
                reserve = row.get("reserve_name") or reserve
                chat_id = chat_id or row.get("chat_id")
        if bot and chat_id:
            try:
                await self._set_title(bot, chat_id, reserve)
            except Exception:
                log.exception("rename on free")
            try:
                await self._send(bot, chat_id, "♻️ این گروه آزاد شد و برای اتحاد بعدی رزرو است.")
            except Exception:
                pass
        if pool_id:
            await self.release(int(pool_id), free=True)
        elif chat_id:
            await self.db.execute(
                """
                UPDATE ng_alliance_pool_groups
                SET status='free', alliance_id=NULL, invite_link=NULL, assigned_at=NULL
                WHERE chat_id=$1
                """,
                (str(chat_id),),
            )

    async def membership_gate(self, pid: int, alliance: dict, bot=None) -> str | None:
        """None if allowed; otherwise Persian message with invite."""
        chat_id = alliance.get("group_chat_id")
        if not chat_id:
            return None
        bot = self.bot(bot)
        if not bot or not hasattr(self.g, "check_chat_membership"):
            return None
        try:
            ok, _reason = await self.g.check_chat_membership(bot, int(pid), chat_id)
        except Exception:
            log.exception("membership_gate")
            ok = False
        if ok:
            return None
        link = (alliance.get("group_invite_link") or "").strip()
        if not link and alliance.get("group_pool_id"):
            prow = await self.db.fetchrow(
                "SELECT invite_link FROM ng_alliance_pool_groups WHERE id=$1",
                (int(alliance["group_pool_id"]),),
            )
            link = ((prow or {}).get("invite_link") or "").strip()
        if not link and bot:
            try:
                link = await self._invite(bot, chat_id)
                await self.db.execute(
                    "UPDATE ng_alliances SET group_invite_link=$1 WHERE id=$2",
                    (link, int(alliance["id"])),
                )
            except Exception:
                log.exception("refresh invite gate")
        msg = (
            "⚠️ برای دسترسی به پنل اتحاد، ابتدا باید عضو گروه رسمی اتحاد خود شوید."
            + chr(10)
            + chr(10)
            + "پس از عضویت، دوباره روی دکمه اتحاد من بزنید."
        )
        if link:
            msg += chr(10) + chr(10) + "لینک گروه:" + chr(10) + link
        return msg
