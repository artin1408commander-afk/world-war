"""New Generation — complete Persian button UI."""
from __future__ import annotations

import logging
from modules.ng.menu_session import MENU_SESSIONS, EXPIRED_MENU_TEXT, FORBIDDEN_MENU_TEXT
from bot.ui import menus_v4 as v4ui

from pathlib import Path

from bale import (
    MenuKeyboardMarkup,
    MenuKeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
)
from modules.ng.catalog import CATALOG, CAT_FA, items_in_category
from modules.ng.guide import guide_menu_rows, guide_page, GUIDE_SECTIONS
from modules.ng.game import GameError
from modules.ng.alliances import AllianceError, create_cost, RENAME_COST
from modules.ng.control import ControlError
from modules.ng.hacker import HackerError, HACKER_CODE, HACKER_NAME_FA, ALLOWED_OWNER_ID
from modules.ng.special_countries import PAHLAVI_CODE, PAHLAVI_NAME_FA, PAHLAVI_FLAG, PERSONALIZED

log = logging.getLogger(__name__)

# owner assign-country page cache: owner_pid -> list of country codes
_set_country_cache: dict[int, list[str]] = {}


def parse_amount(text) -> float:
    """Parse user-typed money/qty; strip invisible/bidi marks (e.g. U+200E from RTL keyboards)."""
    import re
    s = str(text or "")
    for ch in (
        "‎", "‏", "​", "‌", "‍", "﻿", " ",
        "‪", "‫", "‬", "‭", "‮",
    ):
        s = s.replace(ch, "")
    s = s.replace(",", "").replace("،", "").replace(" ", "").replace("٬", "").strip()
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    s = s.translate(trans)
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s or s in (".", "-", "-."):
        raise ValueError("عدد نامعتبر")
    return float(s)


BTN_MY = "🏛 کشور"
BTN_ECO = "💰 اقتصاد"
BTN_SHOP = "🛒 فروشگاه"
BTN_INV = "📦 انبار"
BTN_MKT = "🌐 بازار آزاد"
BTN_TRADE = "🚢 تجارت جهانی"
BTN_DIPLO = "🤝 روابط خارجی"
BTN_PEACE = "🕊 پیمان صلح"
BTN_ATTACK = "⚔️ حمله"
BTN_STMT = "📜 بیانیه رسمی"
BTN_WORLD = "🌍 جهان"
BTN_REPORT = "📊 گزارش‌ها"
BTN_PICK = "🗺 انتخاب کشور"
BTN_OWNER = "🛡 پنل مدیریت"
BTN_TICKET = "🎫 تیکت"
BTN_WORKSHOP = "🏭 کارگاه"
BTN_ABOUT = "ℹ️ درباره ما"
BTN_GUIDE = "📖 راهنما"
BTN_REF = "🎁 دعوت کردن"
BTN_ALLY = "🤝 اتحاد"
BTN_CTRL = "🏛 کنترل کشور"
BTN_TREATY = "⚖ پیمان‌ها"
BTN_WALLET = "💰 کیف پول"
BTN_DONATE = "💎 حمایت مالی"
BTN_MORE = "📂 بیشتر"
BTN_NPT = "پیمان NPT"

_pending: dict[int, dict] = {}


async def _set_pending(game, pid: int, kind: str, **extra) -> None:
    pid = int(pid)
    data = {"kind": kind, **extra}
    _pending[pid] = data
    try:
        await game.set_user_pending(pid, kind, extra or {})
    except Exception:
        log.exception("persist pending failed kind=%s pid=%s", kind, pid)


async def _get_pending(game, pid: int) -> dict | None:
    pid = int(pid)
    st = _pending.get(pid)
    if st and st.get("kind"):
        return st
    try:
        st = await game.get_user_pending(pid)
        if st and st.get("kind"):
            _pending[pid] = dict(st)
            return _pending[pid]
    except Exception:
        log.exception("load pending failed pid=%s", pid)
    return None


async def _clear_pending(game, pid: int) -> None:
    pid = int(pid)
    _pending.pop(pid, None)
    try:
        await game.clear_user_pending(pid)
    except Exception:
        log.exception("clear pending failed pid=%s", pid)

_hacker_shop_cache: dict[int, list] = {}  # pid -> list of item_code for indexed buy


_nav_stack: dict[int, list[str]] = {}


def nav_push(pid: int, screen: str) -> None:
    st = _nav_stack.setdefault(int(pid), [])
    if not st or st[-1] != screen:
        st.append(screen)
    if len(st) > 16:
        del st[:-16]


def nav_home(pid: int) -> None:
    _nav_stack[int(pid)] = []


def nav_back(pid: int) -> str | None:
    st = _nav_stack.get(int(pid)) or []
    if st:
        st.pop()
    return st[-1] if st else None


def main_kb(is_owner: bool = False, has_country: bool = False) -> MenuKeyboardMarkup:
    """Phase 4 main menu — category reply keyboard."""
    kb = MenuKeyboardMarkup()
    rows = v4ui.main_rows(is_owner=is_owner)
    seen = set()
    clean = []
    for row in rows:
        nr = []
        for label in row:
            if label and label not in seen:
                seen.add(label)
                nr.append(label)
        if nr:
            clean.append(nr)
    for i, row in enumerate(clean, 1):
        for label in row:
            kb.add(MenuKeyboardButton(label), row=i)
    return kb


def ik(rows: list) -> InlineKeyboardMarkup:
    """Build inline keyboard. Each row must be list/tuple of (label, callback) pairs."""
    kb = InlineKeyboardMarkup()
    for ri, row in enumerate(rows or [], 1):
        if not row:
            continue
        # If a single (label, data) was passed instead of a row, wrap it
        if (
            isinstance(row, (list, tuple))
            and len(row) == 2
            and not isinstance(row[0], (list, tuple))
            and not isinstance(row[1], (list, tuple))
        ):
            row = [row]
        for item in row:
            try:
                if not item:
                    continue
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    label, data = item[0], item[1]
                else:
                    continue
                if label:
                    ds = str(data)
                    if ds.startswith("http://") or ds.startswith("https://") or ds.startswith("ble.ir/"):
                        if ds.startswith("ble.ir/"):
                            ds = "https://" + ds
                        try:
                            kb.add(InlineKeyboardButton(str(label)[:64], url=ds[:200]), row=ri)
                        except TypeError:
                            # older API may use different kw
                            try:
                                kb.add(InlineKeyboardButton(str(label)[:64], ds[:200]), row=ri)
                            except Exception:
                                kb.add(InlineKeyboardButton(str(label)[:64], callback_data=("ng:joinurl:" + ds)[:64]), row=ri)
                    else:
                        kb.add(InlineKeyboardButton(str(label)[:64], callback_data=str(data)[:64]), row=ri)
            except Exception:
                log.exception("ik button skip bad item=%r", item)
                continue
    return kb



def more_menu_rows():
    """Phase 4 more hub — nested categories."""
    return v4ui.more_hub_rows()


def more_menu_text() -> str:
    return v4ui.more_hub_text()

def back_row():
    """Back goes to previous screen; Home goes to main menu."""
    return [("🔙 بازگشت", "ng:back"), ("🏠 خانه", "ng:home")]


def cancel_row():
    return [("❌ انصراف", "ng:cancel"), ("🏠 خانه", "ng:home")]


def banned_kb():
    """Only ticket button for banned users."""
    kb = MenuKeyboardMarkup()
    kb.add(MenuKeyboardButton(BTN_TICKET), row=1)
    return kb


def ticket_user_inline():
    return [
        [("📬 تیکت‌های من", "ng:tix:mine")],
        [("✍️ تیکت جدید", "ng:tix:new")],
        [("🏠 خانه", "ng:home")],
    ]

def ticket_owner_menu_kb():
    return [
        [("📂 تیکت‌های باز", "ng:otix:openlist")],
        [("⏳ جواب‌داده‌نشده", "ng:otix:unans")],
        back_row(),
    ]

def ticket_owner_view_kb(tid: int, *, is_open: bool = True):
    rows = []
    if is_open:
        rows.append([("✉️ پاسخ به کاربر", f"ng:otix:reply:{int(tid)}")])
        rows.append([("🔒 بستن تیکت", f"ng:otix:close:{int(tid)}")])
    rows.append([("📂 لیست باز", "ng:otix:openlist"), ("⏳ بی‌پاسخ", "ng:otix:unans")])
    rows.append([("🎫 منوی تیکت‌ها", "ng:otix")])
    rows.append(back_row())
    return rows





MENU_TEXTS = {
    BTN_MY, BTN_ECO, BTN_SHOP, BTN_INV, BTN_MKT, BTN_TRADE, BTN_DIPLO,
    BTN_PEACE, BTN_ATTACK, BTN_STMT, BTN_WORLD, BTN_REPORT, BTN_PICK,
    BTN_OWNER, BTN_WORKSHOP, BTN_ABOUT, BTN_GUIDE, BTN_REF, BTN_ALLY, BTN_CTRL, BTN_TREATY, BTN_WALLET, BTN_DONATE, BTN_MORE, BTN_NPT,
    "/start", "شروع", "منو", "menu", "/admin", "/owner", "/panel",
}


async def create_bot(token: str):
    from bale import Bot
    return Bot(token)


def _uid(obj):
    u = getattr(obj, "author", None) or getattr(obj, "from_user", None) or getattr(obj, "user", None)
    if not u:
        return None
    raw = getattr(u, "user_id", None) or getattr(u, "id", None)
    try:
        return int(raw)
    except Exception:
        return None


def _text(m):
    t = getattr(m, "content", None)
    if t is None:
        t = getattr(m, "text", None)
    return str(t or "").strip()


def _names(m):
    u = getattr(m, "author", None) or getattr(m, "from_user", None)
    if not u:
        return None, None
    un = getattr(u, "username", None)
    dn = f"{getattr(u, 'first_name', None) or ''} {getattr(u, 'last_name', None) or ''}".strip() or None
    return un, dn


async def reply(msg, text, kb=None):
    await msg.reply(str(text)[:3500], components=kb)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

_ALLY_CREATE_LOCK: set[int] = set()


def _extract_chat_id(target_msg):
    if target_msg is None:
        return None
    chat = getattr(target_msg, "chat", None)
    if chat is not None:
        cid = getattr(chat, "id", None) or getattr(chat, "chat_id", None)
        if cid is not None:
            return cid
    return getattr(target_msg, "chat_id", None)


def legendary_image_path(image_path):
    if not image_path:
        return None
    p = Path(str(image_path))
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def load_photo_input(photo_path):
    """Local file as bytes for first-time upload."""
    if photo_path is None:
        return None
    p = Path(photo_path)
    if not p.exists() or not p.is_file():
        log.warning("legendary image missing: %s", p)
        return None
    data = p.read_bytes()
    if not data:
        log.warning("legendary image empty: %s", p)
        return None
    return InputFile(data, file_name=p.name)


def extract_photo_file_id(message) -> str | None:
    """Pick largest photo size file_id from a sent Message."""
    if message is None:
        return None
    photos = getattr(message, "photos", None) or getattr(message, "photo", None)
    if not photos:
        return None
    try:
        items = list(photos)
    except TypeError:
        items = [photos]
    best = None
    best_area = -1
    for ph in items:
        fid = getattr(ph, "file_id", None) or getattr(ph, "id", None)
        if not fid:
            continue
        w = int(getattr(ph, "width", 0) or 0)
        h = int(getattr(ph, "height", 0) or 0)
        area = w * h
        if area >= best_area:
            best_area = area
            best = str(fid)
    return best


async def send_photo_with_caption(
    target_msg, bot, photo_path, caption: str, kb=None, *, file_id: str | None = None
):
    """Send photo by cached file_id when possible so clients need not re-download."""
    caption = str(caption or "")[:1024]
    sent = None
    # 1) Prefer cached file_id (no re-upload)
    if file_id:
        try:
            photo = InputFile(str(file_id))
            if target_msg is not None and hasattr(target_msg, "reply_photo"):
                sent = await target_msg.reply_photo(photo, caption=caption, components=kb)
                return True, extract_photo_file_id(sent) or file_id
            chat_id = _extract_chat_id(target_msg)
            if chat_id is not None and bot is not None:
                sent = await bot.send_photo(chat_id, photo, caption=caption, components=kb)
                return True, extract_photo_file_id(sent) or file_id
        except Exception:
            log.exception("send by cached file_id failed; will re-upload")

    # 2) Upload local bytes once
    photo = load_photo_input(photo_path)
    if photo is not None:
        try:
            if target_msg is not None and hasattr(target_msg, "reply_photo"):
                sent = await target_msg.reply_photo(photo, caption=caption, components=kb)
                return True, extract_photo_file_id(sent)
        except Exception:
            log.exception("reply_photo failed path=%s", photo_path)
        try:
            chat_id = _extract_chat_id(target_msg)
            if chat_id is not None and bot is not None:
                photo2 = load_photo_input(photo_path)
                if photo2 is not None:
                    sent = await bot.send_photo(chat_id, photo2, caption=caption, components=kb)
                    return True, extract_photo_file_id(sent)
        except Exception:
            log.exception("bot.send_photo failed path=%s", photo_path)

    # 3) Text fallback
    try:
        if target_msg is not None:
            note = "\n\n(عکس آیتم روی سرور پیدا نشد)" if photo is None else ""
            await target_msg.reply((caption + note)[:3500], components=kb)
            return False, None
    except Exception:
        log.exception("photo fallback text failed")
    return False, None


async def send_legendary_shop(target_msg, bot, game, pid: int, out_text=None):
    defs = await game.legendary.list_defs()
    bal = await game.legendary.ensure_wallet(pid)
    intro = (
        "🎁 فروشگاه آیتم‌های لجندری" + "\n"
        + f"کیف پول شما: {int(bal):,} تومان" + "\n\n"
        + "هر آیتم جداگانه با عکس ارسال می‌شود. عکس‌ها پس از اولین بار از سرور Bale کش می‌شوند."
    )
    if out_text is not None:
        await out_text(intro)
    elif target_msg is not None:
        await target_msg.reply(intro)
    for d in defs:
        code = str(d["item_code"])
        card = game.legendary.card_text(d, bal)
        owned = await game.legendary.owns_item(pid, code)
        if owned:
            kb = ik([[("✔️ خریداری شده", "ng:legowned:" + code)]])
        else:
            kb = ik([[("✅ خرید این آیتم", "ng:legbuy:" + code)]])
        img = legendary_image_path(d.get("image_path"))
        cache_key = f"legendary:{code}"
        cached_id = await game.legendary.get_media_file_id(cache_key)
        ok, new_fid = await send_photo_with_caption(
            target_msg, bot, img, card, kb, file_id=cached_id
        )
        if new_fid and new_fid != cached_id:
            try:
                await game.legendary.set_media_file_id(cache_key, new_fid)
            except Exception:
                log.exception("cache file_id failed for %s", code)
        log.info(
            "legendary card item=%s ok=%s cached=%s new_fid=%s owned=%s",
            code, ok, bool(cached_id), bool(new_fid), owned,
        )



_GROUP_JOIN_WARNED: set[tuple[int, int]] = set()


def _is_bot_user(obj) -> bool:
    u = getattr(obj, "author", None) or getattr(obj, "from_user", None) or getattr(obj, "user", None) or obj
    if u is None:
        return False
    for attr in ("is_bot", "bot", "is_bot_user"):
        v = getattr(u, attr, None)
        if v is True:
            return True
    return False


def _is_group_chat(message) -> bool:
    chat = getattr(message, "chat", None)
    if chat is None:
        return False
    t = str(getattr(chat, "type", None) or getattr(chat, "chat_type", None) or "").lower()
    if t in ("group", "supergroup", "channel"):
        return True
    cid = getattr(chat, "id", None) or getattr(chat, "chat_id", None)
    try:
        return int(cid) < 0
    except Exception:
        return False


# Gameplay interactions are private-chat only
GAMEPLAY_TEXT_COMMANDS = {
    BTN_MY, BTN_ECO, BTN_SHOP, BTN_INV, BTN_MKT, BTN_TRADE, BTN_DIPLO,
    BTN_PEACE, BTN_ATTACK, BTN_STMT, BTN_WORLD, BTN_REPORT, BTN_PICK,
    BTN_WORKSHOP, BTN_REF, BTN_ALLY, BTN_CTRL, BTN_TREATY, BTN_WALLET,
    BTN_DONATE, BTN_MORE, BTN_NPT, "⚔️ نظامی",
    v4ui.BTN_HOME, v4ui.BTN_COUNTRY, v4ui.BTN_ECO, v4ui.BTN_MIL, v4ui.BTN_SHOP,
    v4ui.BTN_INV, v4ui.BTN_WORLD, v4ui.BTN_MORE, v4ui.BTN_GUIDE, v4ui.BTN_PICK,
    v4ui.BTN_OWNER, v4ui.BTN_ALLY,
}
PRIVATE_ONLY_HINT = (
    "🔒 دستورات و منوهای بازی فقط در گفت‌وگوی خصوصی ربات در دسترس هستند.\n"
    "همین‌جا به پیوی ربات پیام بدهید."
)


def register_handlers(bot, app_ctx: dict):

    game = app_ctx["game"]
    settings = app_ctx["settings"]
    # optional: store last group send helper
    app_ctx.setdefault("group_send", None)

    async def ensure(pid, username=None, display=None):
        await game.touch_player(pid, username, display)
        await game.assert_not_banned(pid)

    async def require_membership(pid, message_or_cq, is_callback=False, *, force: bool = False):
        """Block non-members when forced membership is enabled.

        Group chats: at most one soft notice per user per group; never spam.
        Private chats: always block gameplay and show join buttons.
        Never process/reply to the bot's own messages.
        """
        if not await game.membership_enabled():
            return True
        if game.is_owner(pid):
            return True
        try:
            if await game.is_test_mode(pid):
                return True
        except Exception:
            pass
        chats = await game.active_forced_chats()
        if not chats:
            return True
        missing = []
        api_errors = []
        for ch in chats:
            cid = ch["chat_id"]
            ok, detail = await game.verify_membership(bot, pid, cid, force=force)
            if ok:
                continue
            if detail == "api_error":
                api_errors.append(ch)
            else:
                missing.append(ch)
        if not missing and not api_errors:
            return True

        # Determine if this interaction is in a group
        src = message_or_cq
        if is_callback:
            src = getattr(message_or_cq, "message", None) or message_or_cq
        in_group = False
        try:
            in_group = _is_group_chat(src) if src is not None else False
        except Exception:
            in_group = False

        chat_id = None
        try:
            chat_id = _extract_chat_id(src)
        except Exception:
            chat_id = None

        # In groups: only one notice per (user, group); no further replies in group
        if in_group and not force:
            key = (int(pid), int(chat_id) if chat_id is not None else 0)
            if key in _GROUP_JOIN_WARNED:
                return False
            _GROUP_JOIN_WARNED.add(key)
            # short one-time group notice (no big button spam if possible)
            try:
                lines = ["🔒 برای استفاده از ربات در پیوی، ابتدا در کانال/گروه اجباری عضو شوید."]
                show = missing if missing else api_errors
                for ch in show[:3]:
                    title = ch.get("title") or "کانال/گروه"
                    link = (ch.get("invite_link") or "").strip()
                    if link:
                        lines.append(f"• {title}: {link}")
                    else:
                        lines.append(f"• {title}")
                body = "\n".join(lines)
                if hasattr(src, "reply"):
                    await src.reply(body[:3500])
                elif chat_id is not None and hasattr(bot, "send_message"):
                    await bot.send_message(chat_id, body[:3500])
            except Exception:
                log.exception("group join once-notice failed")
            return False

        # Private (or forced re-check): full prompt with buttons
        lines = [
            "🔒 برای استفاده از ربات ابتدا عضو شوید.",
            "",
            "روی دکمه عضویت بزنید، عضو شوید، سپس «عضو شدم — تأیید» را بزنید.",
            "",
        ]
        rows = []
        show = missing if missing else api_errors
        for ch in show:
            title = ch.get("title") or ch.get("chat_id") or "کانال/گروه"
            kind_fa = "کانال" if str(ch.get("kind")) == "channel" else "گروه"
            link = (ch.get("invite_link") or "").strip()
            if not link:
                cid = str(ch.get("chat_id") or "")
                if cid.startswith("@"):
                    link = "https://ble.ir/" + cid.lstrip("@")
            lines.append(f"• {kind_fa}: {title}")
            if link:
                lines.append(f"  {link}")
                rows.append([(f"📥 عضویت در {title}"[:60], link)])
            else:
                rows.append([(f"📥 عضویت در {title}"[:60], f"ng:joinlink:{ch['id']}")])
        if api_errors and not missing:
            lines.append("")
            lines.append("⚠️ اگر دکمه کار نکرد، مطمئن شوید ربات در آن گروه/کانال ادمین است.")
        rows.append([("✅ عضو شدم — تأیید", "ng:joincheck")])
        body = "\n".join(lines)
        try:
            if is_callback:
                try:
                    if hasattr(message_or_cq, "answer"):
                        await message_or_cq.answer("ابتدا عضو شوید", show_alert=False)
                except Exception:
                    pass
                msg = getattr(message_or_cq, "message", None)
                # Prefer private DM for join prompt when possible
                try:
                    if hasattr(bot, "send_message"):
                        await bot.send_message(int(pid), body[:3500], components=ik(rows))
                        return False
                except Exception:
                    log.debug("dm join prompt failed, fallback reply", exc_info=True)
                if msg is not None and hasattr(msg, "reply"):
                    await msg.reply(body[:3500], components=ik(rows))
                else:
                    cid2 = _extract_chat_id(msg)
                    if cid2 is not None and hasattr(bot, "send_message"):
                        await bot.send_message(cid2, body[:3500], components=ik(rows))
            else:
                # private message path
                await reply(message_or_cq, body, ik(rows))
        except Exception:
            log.exception("require_membership prompt failed")
        return False

        return False

    @bot.listen("on_ready")
    async def on_ready():
        log.info("NG UI ready")

    @bot.listen("on_message")
    async def on_message(message):
        try:
            # Never react to the bot's own messages (prevents join-loop in groups)
            try:
                if _is_bot_user(message):
                    return
            except Exception:
                pass
            # Auto-detect reserved alliance groups named "c." when bot is admin
            try:
                await game.alliance_groups.try_auto_from_message(bot, message)
            except Exception:
                log.exception("auto pool register")
            text = _text(message)
            if not text:
                return
            pid = _uid(message)
            if not pid:
                return
            username, display = _names(message)
            # Private-chat-only gameplay (groups: short hint, no execution)
            try:
                if _is_group_chat(message):
                    tstrip = (text or "").strip()
                    if (
                        tstrip in GAMEPLAY_TEXT_COMMANDS
                        or tstrip.startswith(("/country", "/shop", "/attack"))
                        or tstrip in ("خرید", "حمله", "کشور من", "انبار", "فروشگاه")
                    ):
                        try:
                            await reply(message, PRIVATE_ONLY_HINT)
                        except Exception:
                            pass
                        return
            except Exception:
                log.exception("private-only gate")
            try:
                await ensure(pid, username, display)
            except GameError as e:
                err = str(e)
                if err == "BANNED" or "مسدود" in err:
                    ban = await game.get_ban_info(pid)
                    notice = game.format_ban_user_notice(ban, display) if ban else "شما مسدود شده‌اید."
                    early_st = await _get_pending(game, pid)
                    early_kind = (early_st or {}).get("kind") or ""
                    # Cancel while banned
                    if text in ("لغو", "cancel", "/cancel", "❌ انصراف", "انصراف"):
                        await _clear_pending(game, pid)
                        await reply(message, "عملیات لغو شد.", banned_kb())
                        return
                    # Ticket message body while banned — handle here and STOP (no normal menu)
                    if early_kind == "ticket_new_body":
                        await _clear_pending(game, pid)
                        try:
                            tid, msg = await game.create_ticket(pid, text)
                            await reply(
                                message,
                                f"✅ {msg}\nشناسه تیکت: #{tid}",
                                ik(ticket_user_inline()),
                            )
                            try:
                                if hasattr(bot, "send_message"):
                                    for oid in await game.all_owner_ids():
                                        try:
                                            await bot.send_message(
                                                int(oid),
                                                f"یک تیکت جدید دریافت کرده‌اید : #{tid}",
                                                components=ik([[("باز کردن", f"ng:otix:open:{tid}")]]),
                                            )
                                        except Exception:
                                            pass
                            except Exception:
                                log.exception("notify owners new ticket")
                        except GameError as ge:
                            await reply(message, f"❌ {ge}", banned_kb())
                        except Exception:
                            log.exception("banned ticket_new_body")
                            await reply(message, "❌ ثبت تیکت ناموفق بود. دوباره تلاش کنید.", banned_kb())
                        return
                    if early_kind == "ticket_reply_body":
                        tid = int((early_st or {}).get("ticket_id") or 0)
                        await _clear_pending(game, pid)
                        try:
                            msg = await game.reply_ticket(tid, pid, text, is_admin=False)
                            await reply(message, msg, ik(ticket_user_inline()))
                        except GameError as ge:
                            await reply(message, f"❌ {ge}", banned_kb())
                        except Exception:
                            log.exception("banned ticket_reply_body")
                            await reply(message, "❌ ارسال پاسخ ناموفق بود.", banned_kb())
                        return
                    if text in ("/start", "شروع", "منو", "menu", BTN_TICKET, "تیکت"):
                        if text in (BTN_TICKET, "تیکت"):
                            await reply(message, "بخش تیکت:", ik(ticket_user_inline()))
                        else:
                            await reply(message, notice, banned_kb())
                        return
                    # ignore random messages while banned — never show main menu
                    return
                else:
                    await reply(message, f"❌ {e}")
                    return
            owner = game.is_owner(pid)

            # ---- EARLY pending (DB+memory) so chat-id inputs never get swallowed ----
            early_st = await _get_pending(game, pid)
            if early_st and early_st.get("kind") == "force_add_chat":
                if not owner:
                    await _clear_pending(game, pid)
                    await reply(message, "❌ فقط مالک")
                    return
                # cancel shortcuts
                if text in ("لغو", "cancel", "/cancel", "❌ لغو"):
                    await _clear_pending(game, pid)
                    await reply(message, "عملیات لغو شد.", main_kb(owner))
                    return
                log.info("EARLY force_add_chat pid=%s text=%r", pid, text)
                try:
                    msg = await game.add_forced_chat(pid, text, bot=bot)
                    await _clear_pending(game, pid)
                    await reply(
                        message,
                        msg,
                        ik([
                            [("⚙️ عضویت اجباری", "ng:oforce")],
                            back_row(),
                        ]),
                    )
                except GameError as e:
                    await reply(
                        message,
                        f"❌ {e}" + chr(10) + chr(10) + "دوباره آیدی/@ را بفرستید یا لغو کنید.",
                        ik([cancel_row()]),
                    )
                except Exception as e:
                    log.exception("EARLY force_add_chat")
                    await reply(message, f"❌ خطا: {e}", ik([cancel_row()]))
                return
            # owner panel commands only
            # Direct money ops (bypass pending — more reliable)
            if owner and (text.startswith("/give ") or text.startswith("پول ")):
                try:
                    parts = text.split()
                    if len(parts) < 3:
                        await reply(message, "فرمت:\n/give شناسه مبلغ\nیا:\nپول شناسه مبلغ\nمثال: پول 123456 5000000")
                        return
                    tid = int(float(str(parts[1]).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))))
                    amount = game.parse_money_amount(parts[2])
                    msg = await game.admin_give_to_player(pid, tid, amount)
                    await reply(message, msg, main_kb(True))
                except GameError as e:
                    await reply(message, f"❌ {e}")
                except Exception:
                    log.exception("direct give")
                    await reply(message, "❌ خطا در واریز")
                return
            if owner and (text.startswith("/take ") or text.startswith("برداشت ")):
                try:
                    parts = text.split()
                    if len(parts) < 3:
                        await reply(message, "فرمت:\n/take شناسه مبلغ\nمثال: /take 123456 1000000")
                        return
                    tid = int(float(str(parts[1]).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))))
                    amount = game.parse_money_amount(parts[2])
                    msg = await game.admin_take_from_player(pid, tid, amount)
                    await reply(message, msg, main_kb(True))
                except GameError as e:
                    await reply(message, f"❌ {e}")
                except Exception:
                    log.exception("direct take")
                    await reply(message, "❌ خطا در برداشت")
                return

            if text in ("/admin", "/owner", "/panel", BTN_OWNER, v4ui.BTN_OWNER):
                if not owner:
                    await reply(message, "❌ دسترسی مجاز نیست.")
                    return
                nav_push(pid, "owner")
                try:
                    summary = await game.owner_admin_summary()
                except Exception:
                    log.exception("owner_admin_summary")
                    summary = "🛡 پنل مالک / سازمان ملل"
                rows = []
                if game.is_primary_owner(pid):
                    rows.append([("➕ افزودن مالک", "ng:owners"), ("🛡 لیست مالکان", "ng:owners")])
                rows += [
                    [("👤 بازیکنان", "ng:o:hub:players"), ("🗺 کشورها", "ng:o:hub:countries")],
                    [("🛡 Sethp ۱۰۰۰/۱۰۰۰", "ng:ohpfull")],
                    [("☠️ هاردکور", "ng:ohardcore:status"), ("💸 کسر همگانی", "ng:omassdeduct")],
                    [("💰 اقتصاد", "ng:o:hub:economy"), ("📦 تجهیزات", "ng:o:hub:inventory")],
                    [("🕊 دیپلماسی", "ng:o:hub:diplo"), ("⚔️ جنگ", "ng:o:hub:wars")],
                    [("⚙️ تنظیمات", "ng:o:hub:settings"), ("📋 گزارش‌ها", "ng:o:hub:logs")],
                    [("🎫 تیکت‌ها", "ng:otix"), ("🔍 جستجوی بن", "ng:obansearch")],
                ]
                await reply(
                    message,
                    str(summary) + chr(10) + chr(10) + "بخش را انتخاب کنید. با ورود به هر دسته، همین پیام به‌روز می‌شود.",
                    ik(rows),
                )
                return
            owner = game.is_owner(pid)
            code = await game.player_country(pid)

            # Pending owner/player input must run before membership gate,
            # otherwise forced-join prompts swallow the typed chat id with no reply.
            # Forced membership: check on every message for non-owners (3h cache inside)
            if not owner and not await _get_pending(game, pid):
                if not await require_membership(pid, message, False):
                    return

            # ---- pending typed flows ----
            st = await _get_pending(game, pid)
            if st:
                kind = st.get("kind")
                if kind == "hacker_statement":
                    await _clear_pending(game, pid)
                    await reply(message, "بیانیه ویژه هکری حذف شده؛ از بیانیه عادی کشور استفاده کنید.", main_kb(owner))
                    return
                if False and kind == "hacker_statement_disabled":
                    try:
                        msg = await game.hacker.queue_announcement(pid, text)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except (HackerError, GameError) as e:
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    except Exception as e:
                        log.exception("hacker_statement")
                        await reply(message, f"❌ {e}")
                    return
                if kind == "add_co_owner" and game.is_primary_owner(pid):
                    raw = (text or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
                    try:
                        tid = int(raw.replace(",", "").replace(" ", ""))
                    except Exception:
                        await reply(message, "شناسه عددی معتبر بنویس.", ik([cancel_row()]))
                        return
                    try:
                        msg = await game.add_co_owner(pid, tid)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(True))
                    except GameError as e:
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    except Exception as e:
                        log.exception("add_co_owner")
                        await reply(message, f"❌ {e}")
                    return
                # cancel pending if user pressed a main menu button
                if text in MENU_TEXTS or (text.startswith("/") and kind and kind.startswith("ally")):
                    await _clear_pending(game, pid)
                    # fall through to normal menu handling below
                elif kind == "ally_name":
                    name = text.strip()[:40]
                    if len(name) < 3:
                        await reply(
                            message,
                            "نام اتحاد حداقل ۳ حرف باشد.\nدوباره بنویسید:",
                            ik([cancel_row()]),
                        )
                        return
                    st["name"] = name
                    st["kind"] = "ally_members"
                    _pending[pid] = dict(st)
                    await reply(
                        message,
                        f"نام: {name}\n\nظرفیت اعضا را وارد کنید (عدد بین ۲ تا ۲۰):",
                        ik([cancel_row()]),
                    )
                    return
                elif kind == "ally_members":
                    try:
                        mm = int(text.strip().replace(",", "").replace("،", ""))
                    except Exception:
                        await reply(message, "فقط عدد وارد کنید (۲ تا ۲۰):", ik([cancel_row()]))
                        return
                    if mm < 2 or mm > 20:
                        await reply(message, "ظرفیت اعضا باید بین ۲ تا ۲۰ باشد:", ik([cancel_row()]))
                        return
                    st["max_members"] = mm
                    st["kind"] = "ally_cap"
                    _pending[pid] = dict(st)
                    await reply(
                        message,
                        f"ظرفیت اعضا: {mm}\n\nظرفیت خزانه را وارد کنید (مثلاً 100000000):",
                        ik([cancel_row()]),
                    )
                    return
                elif kind == "ally_cap":
                    raw = text.replace(",", "").replace("،", "").replace(" ", "").strip()
                    try:
                        tc = float(raw)
                    except Exception:
                        await reply(message, "عدد معتبر برای ظرفیت خزانه وارد کنید:", ik([cancel_row()]))
                        return
                    if tc < 50_000_000:
                        await reply(message, "حداقل ظرفیت خزانه ۵۰٬۰۰۰٬۰۰۰ است:", ik([cancel_row()]))
                        return
                    st["treasury_cap"] = tc
                    name = st.get("name") or "?"
                    mm = int(st.get("max_members") or 2)
                    cost = create_cost(mm, tc)
                    st["kind"] = "ally_confirm"
                    st["cost"] = cost
                    _pending[pid] = dict(st)
                    rows = [
                        [("✅ تأیید و ساخت اتحاد", "ng:acreateyes")],
                        cancel_row(),
                    ]
                    preview = (
                        "📋 پیش‌نمایش اتحاد\n\n"
                        f"نام: {name}\n"
                        f"ظرفیت اعضا: {mm}\n"
                        f"ظرفیت خزانه: {int(tc):,}\n"
                        f"هزینه نهایی: {cost:,}\n\n"
                        "اگر درست است «تأیید و ساخت اتحاد» را بزنید."
                    )
                    await reply(message, preview, ik(rows))
                    return
                elif kind == "ally_confirm":
                    name = st.get("name") or "?"
                    mm = int(st.get("max_members") or 2)
                    tc = float(st.get("treasury_cap") or 100_000_000)
                    cost = int(st.get("cost") or create_cost(mm, tc))
                    rows = [
                        [("✅ تأیید و ساخت اتحاد", "ng:acreateyes")],
                        cancel_row(),
                    ]
                    await reply(
                        message,
                        (
                            "لطفاً از دکمه‌ها استفاده کنید.\n\n"
                            f"نام: {name}\n"
                            f"ظرفیت: {mm}\n"
                            f"خزانه: {int(tc):,}\n"
                            f"هزینه: {cost:,}"
                        ),
                        ik(rows),
                    )
                    return
                elif kind == "ally_deposit":
                    await _clear_pending(game, pid)
                    try:
                        msg = await game.alliances.deposit(pid, code, parse_amount(text))
                    except (AllianceError, GameError, ValueError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "ally_withdraw":
                    await _clear_pending(game, pid)
                    try:
                        msg = await game.alliances.withdraw(pid, parse_amount(text))
                    except (AllianceError, GameError, ValueError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "ally_rename":
                    await _clear_pending(game, pid)
                    try:
                        msg = await game.alliances.rename(pid, text.strip())
                    except (AllianceError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "ally_emembers":
                    try:
                        raw = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
                        msg = await game.alliances.expand_members(pid, int(raw))
                        await _clear_pending(game, pid)
                    except (AllianceError, GameError, ValueError) as e:
                        msg = f"❌ {e}\nدوباره عدد بزرگ‌تر از ظرفیت فعلی را بفرستید."
                    await reply(message, msg, main_kb(owner) if "✅" in str(msg) else None)
                    return
                if kind == "ally_etreasury":
                    await _clear_pending(game, pid)
                    try:
                        msg = await game.alliances.expand_treasury(pid, parse_amount(text))
                    except (AllianceError, GameError, ValueError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "ally_pay":
                    st["pay_country"] = st.get("pay_country")
                    try:
                        amount = parse_amount(text)
                        msg = await game.alliances.pay_member(pid, st["pay_country"], amount)
                    except (AllianceError, GameError, ValueError, KeyError) as e:
                        msg = f"❌ {e}"
                    await _clear_pending(game, pid)
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "set_shop_price":
                    st = dict((await _get_pending(game, pid)) or {})
                    await _clear_pending(game, pid)
                    try:
                        price = parse_amount(text)
                        msg = await game.set_item_unit_price(pid, st.get("item"), price)
                    except GameError as e:
                        msg = f"❌ {e}"
                    except Exception:
                        msg = "❌ عدد معتبر وارد کنید."
                    await reply(message, msg, main_kb(owner))
                    return

                if kind == "donation_amount":
                    raw = (text or "").strip().replace(",", "").replace("،", "").replace(" ", "")
                    raw = raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
                    try:
                        amount = float(raw)
                    except Exception:
                        await reply(message, "فقط عدد معتبر بنویس. مثال: 50000", ik([cancel_row()]))
                        return
                    if amount < 1000:
                        await reply(message, "حداقل مبلغ ۱٬۰۰۰ تومان است.", ik([cancel_row()]))
                        return
                    method = st.get("method") or "card"
                    st["amount"] = amount
                    st["kind"] = "donation_show_name"
                    _pending[pid] = st
                    await reply(
                        message,
                        f"مبلغ: {int(amount):,} تومان\n\nمی‌خواهی اسمت در اطلاع همگانی نمایش داده شود؟",
                        ik([
                            [("✅ بله، نمایش بده", "ng:donate:showname:1"), ("❌ خیر، ناشناس", "ng:donate:showname:0")],
                            cancel_row(),
                        ]),
                    )
                    return


                if kind == "donation_set_total":
                    if not owner:
                        await _clear_pending(game, pid)
                        await reply(message, "❌ فقط مالک")
                        return
                    raw = (text or "").strip().replace(",", "").replace(" ", "")
                    raw = raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
                    try:
                        amount = float(raw)
                        msg = await game.donations.set_total_manual(pid, amount)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(True))
                    except Exception as e:
                        await reply(message, f"❌ {e}")
                    return
                if kind and str(kind).startswith("donation_set_"):
                    if not owner:
                        await _clear_pending(game, pid)
                        await reply(message, "❌ فقط مالک")
                        return
                    field = str(kind).replace("donation_set_", "")
                    try:
                        msg = await game.donations.set_field(pid, field, text)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(True))
                    except Exception as e:
                        await reply(message, f"❌ {e}")
                    return
                if kind == "law_title":
                    st["title"] = text.strip()[:80]
                    st["kind"] = "law_body"
                    _pending[pid] = st
                    await reply(message, "متن کامل قانون را بنویسید (حداقل ۲۰ کاراکتر):", ik([cancel_row()]))
                    return
                if kind == "law_body":
                    st = dict((await _get_pending(game, pid)) or {})
                    await _clear_pending(game, pid)
                    if not code:
                        await reply(message, "کشور ندارید", main_kb(owner))
                        return
                    try:
                        msg = await game.control.submit_law(code, pid, st.get("title") or "قانون", text)
                    except ControlError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "law_bonus":
                    st = dict((await _get_pending(game, pid)) or {})
                    await _clear_pending(game, pid)
                    try:
                        bonus = parse_amount(text or "0")
                    except Exception:
                        bonus = 0
                    try:
                        msg = await game.control.review_law(int(st["law_id"]), pid, True, bonus)
                    except ControlError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "ref_code":
                    preset = st.get("preset")
                    await _clear_pending(game, pid)
                    code_in = (text or "").strip() or str(preset or "")
                    try:
                        msg = await game.apply_referral_code(pid, code_in)
                    except GameError as e:
                        msg = f"❌ {e}"
                    except Exception as e:
                        log.exception("ref_code apply")
                        msg = f"❌ خطا در ثبت کد دعوت: {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "statement":
                    await _clear_pending(game, pid)
                    if not code:
                        await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                        return
                    try:
                        msg = await game.submit_statement(code, pid, text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "aid_oil_amount":
                    try:
                        barrels = int(float(parse_amount(text)))
                    except Exception:
                        await reply(message, "مقدار نامعتبر.", ik([cancel_row()]))
                        return
                    try:
                        msg = await game.aid_oil(code, st["dst"], barrels, pid)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    except Exception:
                        log.exception("aid_oil_amount")
                        await reply(message, "❌ خطا در کمک نفتی.", ik([cancel_row()]))
                    return
                if kind == "aid_money_amount":
                    await _clear_pending(game, pid)
                    try:
                        amount = parse_amount(text)
                        if amount <= 0:
                            raise ValueError("مبلغ باید بزرگ‌تر از صفر باشد")
                        msg = await game.aid_money(code, st["dst"], amount, pid)
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    except Exception as e:
                        log.exception("aid_money_amount")
                        msg = "❌ مبلغ نامعتبر است. فقط عدد بنویسید." + chr(10) + "مثال: 50000000"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "aid_army_qty":
                    await _clear_pending(game, pid)
                    try:
                        qty = parse_amount(text)
                        msg = await game.aid_army(code, st["dst"], st["item"], qty, pid)
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "shop_add_qty":
                    ic = st.get("item") or st.get("item_code")
                    if not ic and isinstance(st.get("data"), dict):
                        ic = st["data"].get("item")
                    if not ic:
                        await _clear_pending(game, pid)
                        await reply(
                            message,
                            "نشست خرید منقضی شد. دوباره کالا را از فروشگاه انتخاب کنید.",
                            ik([[("🛒 فروشگاه", "ng:shophome")]]),
                        )
                        return
                    raw = (text or "").strip().replace(",", "").replace(" ", "")
                    raw = raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
                    try:
                        qty = float(raw)
                    except Exception:
                        await reply(
                            message,
                            "فقط یک عدد بین ۱ تا ۲۵۰ بفرست (یا از دکمه‌های ＋ استفاده کن).",
                            ik([[("🛒 فروشگاه", "ng:shophome")], cancel_row()]),
                        )
                        return
                    if qty <= 0 or qty > 250:
                        await reply(
                            message,
                            "⚠ مقدار باید بین ۱ تا ۲۵۰ باشد.",
                            ik([[("🛒 فروشگاه", "ng:shophome")], cancel_row()]),
                        )
                        return
                    try:
                        add_msg = await game.cart_add(pid, ic, qty)
                    except GameError as e:
                        await reply(message, f"❌ {e}", main_kb(owner))
                        return
                    except Exception as e:
                        log.exception("shop_add_qty")
                        await reply(message, f"❌ {e}", main_kb(owner))
                        return
                    await _set_pending(game, pid, "shop_add_qty", item=ic)
                    cart_txt = ""
                    try:
                        if code:
                            cart_txt, _, _ = await game.cart_view(pid, code)
                    except Exception:
                        cart_txt = ""
                    body = str(add_msg)
                    if cart_txt:
                        body = body + "\n\n" + cart_txt
                    await reply(
                        message,
                        body,
                        ik([
                            [("＋۱", f"ng:add:{ic}:1"), ("＋۵", f"ng:add:{ic}:5"), ("＋۱۰", f"ng:add:{ic}:10")],
                            [("🛒 سبد", "ng:cart"), ("✅ تسویه", "ng:checkout")],
                            [("🛒 فروشگاه", "ng:shophome")],
                            cancel_row(),
                        ]),
                    )
                    return
                if kind == "mkt_qty":
                    try:
                        qty = parse_amount(text)
                        if qty <= 0:
                            raise ValueError("عدد نامعتبر")
                        item = st.get("item")
                        await _set_pending(game, pid, "mkt_price", item=item, qty=qty)
                        await reply(
                            message,
                            "قیمت واحد پیشنهادی را بنویسید:",
                            ik([cancel_row()]),
                        )
                    except ValueError:
                        await reply(message, "یک عدد معتبر بنویسید.", ik([cancel_row()]))
                    return
                if kind == "mkt_price":
                    try:
                        price = parse_amount(text)
                        if price < 0:
                            raise ValueError("عدد نامعتبر")
                        item = st.get("item")
                        qty = st.get("qty")
                        msg = await game.market_create(code, item, qty, price, pid)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except ValueError:
                        # keep waiting for a valid price
                        await reply(message, "یک عدد معتبر بنویسید.", ik([cancel_row()]))
                    except GameError as e:
                        await _clear_pending(game, pid)
                        await reply(message, f"❌ {e}", main_kb(owner))
                    except Exception:
                        log.exception("mkt_price")
                        await _clear_pending(game, pid)
                        await reply(message, "❌ خطا در ثبت آگهی.", main_kb(owner))
                    return
                # ── Ban wizard (from player profile) ─────────────────
                if kind == "ban_search_code":
                    await _clear_pending(game, pid)
                    code = text.strip().lstrip("#")
                    try:
                        ban = await game.find_ban_by_code(code)
                    except Exception:
                        log.exception("ban_search_code")
                        await reply(message, "❌ خطا در جستجو.", main_kb(owner))
                        return
                    if not ban:
                        await reply(message, f"❌ بن با کد #{code} یافت نشد.", main_kb(owner))
                        return
                    card = game.format_ban_search_card(ban)
                    tid = int(ban.get("player_id") or 0)
                    rows = []
                    if tid:
                        rows.append([("👤 پروفایل کاربر", f"ng:ou:{tid}")])
                        if int(ban.get("is_banned") or 0) == 1:
                            rows.append([("✅ آن‌بن", f"ng:ouunban:{tid}")])
                    rows.append(back_row())
                    await reply(message, card, ik(rows))
                    return

                if kind == "ban_wizard_code":
                    code = text.strip().lstrip("#")
                    if not code or len(code) > 32:
                        await reply(message, "❌ کد بن نامعتبر است. دوباره وارد کنید:", ik([cancel_row()]))
                        return
                    if await game.is_ban_code_taken(code):
                        await reply(message, "❌ این کد بن تکراری است. کد دیگری وارد کنید:", ik([cancel_row()]))
                        return
                    st["ban_code"] = code
                    st["kind"] = "ban_wizard_duration"
                    _pending[pid] = st
                    await reply(
                        message,
                        "مدت زمان را به روز وارد کن\nاگر دائم است بنویس دائم",
                        ik([cancel_row()]),
                    )
                    return
                if kind == "ban_wizard_duration":
                    t = text.strip()
                    permanent = t in ("دائم", "permanent", "perm", "همیشگی")
                    days = None
                    if not permanent:
                        try:
                            days = int(t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
                            if days <= 0:
                                raise ValueError()
                        except Exception:
                            await reply(message, "❌ عدد روز معتبر یا «دائم» وارد کنید:", ik([cancel_row()]))
                            return
                    st["permanent"] = permanent
                    st["days"] = days
                    st["kind"] = "ban_wizard_package"
                    _pending[pid] = st
                    await reply(
                        message,
                        "پکیج آن‌بن فعال باشد؟\nبنویس: بله یا خیر",
                        ik([cancel_row()]),
                    )
                    return
                if kind == "ban_wizard_package":
                    t = text.strip().lower()
                    yes = t in ("بله", "آره", "اره", "yes", "y", "1", "true")
                    no = t in ("خیر", "نه", "no", "n", "0", "false")
                    if not yes and not no:
                        await reply(message, "❌ فقط بله یا خیر بنویس:", ik([cancel_row()]))
                        return
                    st["unban_package"] = yes
                    st["kind"] = "ban_wizard_reason"
                    _pending[pid] = st
                    await reply(message, "دلیل بن را بنویس:", ik([cancel_row()]))
                    return
                if kind == "ban_wizard_reason":
                    reason = text.strip()
                    if len(reason) < 2:
                        await reply(message, "❌ دلیل خیلی کوتاه است. دوباره بنویس:", ik([cancel_row()]))
                        return
                    st["reason"] = reason
                    st["kind"] = "ban_wizard_confirm"
                    _pending[pid] = st
                    duration = "دائم" if st.get("permanent") else f"{st.get('days')} روز"
                    pkg = "بله" if st.get("unban_package") else "خیر"
                    yes = bool(st.get("unban_package"))
                    summary = (
                        f"تأیید نهایی بن:\n"
                        f"کاربر: {st.get('target')}\n"
                        f"کد بن: #{st.get('ban_code')}\n"
                        f"مدت: {duration}\n"
                        f"دلیل: {st.get('reason')}\n"
                        f"پکیج آن‌بن: {pkg}\n\n"
                        f"برای تأیید بنویس: تأیید\nبرای لغو: لغو"
                    )
                    await reply(message, summary, ik([cancel_row()]))
                    return
                if kind == "ban_wizard_confirm":
                    t = text.strip()
                    if t not in ("تأیید", "تایید", "confirm", "ok", "بله"):
                        await reply(message, "برای تأیید نهایی بنویس «تأیید» یا برای لغو «لغو»", ik([cancel_row()]))
                        return
                    target = int(st.get("target"))
                    try:
                        receipt = await game.ban(
                            pid,
                            target,
                            st.get("reason") or "",
                            ban_code=st.get("ban_code"),
                            days=st.get("days"),
                            permanent=bool(st.get("permanent")),
                            unban_package=bool(st.get("unban_package")),
                        )
                    except GameError as e:
                        await _clear_pending(game, pid)
                        await reply(message, f"❌ {e}", main_kb(owner))
                        return
                    await _clear_pending(game, pid)
                    await reply(message, receipt, main_kb(owner))
                    # Notify banned user if possible
                    try:
                        ban = await game.get_ban_info(target)
                        if ban and hasattr(bot, "send_message"):
                            p = await game.db.fetchrow(
                                "SELECT display_name, username FROM ng_players WHERE player_id=$1",
                                (target,),
                            )
                            name = (p or {}).get("display_name") or (p or {}).get("username")
                            notice = game.format_ban_user_notice(ban, name)
                            await bot.send_message(target, notice[:3500], components=banned_kb())
                    except Exception:
                        log.exception("notify banned user")
                    return

                if kind == "ticket_new_body":
                    await _clear_pending(game, pid)
                    try:
                        tid, msg = await game.create_ticket(pid, text)
                        await reply(
                            message,
                            f"✅ {msg}\nشناسه تیکت: #{tid}",
                            ik(ticket_user_inline()),
                        )
                        # notify owners
                        try:
                            if hasattr(bot, "send_message"):
                                oids = await game.all_owner_ids()
                                for oid in oids:
                                    try:
                                        await bot.send_message(
                                            int(oid),
                                            f"یک تیکت جدید دریافت کرده‌اید : #{tid}",
                                            components=ik([[("باز کردن", f"ng:otix:open:{tid}")]]),
                                        )
                                    except Exception:
                                        pass
                        except Exception:
                            log.exception("notify owners new ticket")
                    except GameError as e:
                        await reply(message, f"❌ {e}", banned_kb())
                    return
                if kind == "ticket_reply_body":
                    tid = int(st.get("ticket_id") or 0)
                    is_admin = bool(st.get("is_admin"))
                    await _clear_pending(game, pid)
                    try:
                        msg = await game.reply_ticket(tid, pid, text, is_admin=is_admin)
                        await reply(message, msg)
                    except GameError as e:
                        await reply(message, f"❌ {e}")
                    return

                if kind == "ban_user" or kind == "ban_wizard_target":
                    # resolve target then start full wizard (no instant 1-day ban)
                    raw = (text or "").strip()
                    try:
                        tid = await game.resolve_player_id(raw)
                    except Exception:
                        tid = None
                    if not tid:
                        # try numeric
                        try:
                            tid = int(raw.replace("@", "").strip())
                        except Exception:
                            tid = None
                    if not tid:
                        await reply(message, "❌ کاربر یافت نشد. آیدی یا @username معتبر بفرستید:", ik([cancel_row()]))
                        return
                    import time as _time
                    auto_code = str(int(_time.time()) % 1000000)
                    try:
                        while await game.is_ban_code_taken(auto_code):
                            auto_code = str((int(auto_code) + 7) % 1000000)
                    except Exception:
                        pass
                    await _set_pending(
                        game, pid, "ban_wizard_duration",
                        target=int(tid), ban_code=auto_code,
                    )
                    await reply(
                        message,
                        f"هدف: {tid}\nکد بن: #{auto_code}\n\nچند روز بن باشد؟\nعدد روز یا «دائم» را بفرستید:",
                        ik([cancel_row()]),
                    )
                    return
                if kind == "unban_user":
                    await _clear_pending(game, pid)
                    try:
                        msg = await game.unban_user(pid, text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "set_log_group":
                    if not owner:
                        await _clear_pending(game, pid)
                        await reply(message, "❌ فقط مالک")
                        return
                    try:
                        msg = await game.set_log_group(pid, text)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    except Exception:
                        log.exception("set_log_group")
                        await reply(message, "❌ خطا در تنظیم گروه لاگ")
                    return
                if kind == "force_add_chat":
                    if not owner:
                        await _clear_pending(game, pid)
                        await reply(message, "❌ فقط مالک")
                        return
                    log.info("force_add_chat input pid=%s text=%r", pid, text)
                    try:
                        msg = await game.add_forced_chat(pid, text, bot=bot)
                        await _clear_pending(game, pid)
                        await reply(
                            message,
                            msg,
                            ik([
                                [("⚙️ عضویت اجباری", "ng:oforce")],
                                back_row(),
                            ]),
                        )
                    except GameError as e:
                        await reply(
                            message,
                            f"❌ {e}" + chr(10) + chr(10) + "دوباره آیدی/@ را بفرستید یا لغو کنید.",
                            ik([cancel_row()]),
                        )
                    except Exception as e:
                        log.exception("force_add_chat")
                        await reply(
                            message,
                            f"❌ خطا در افزودن گروه/کانال: {e}" + chr(10) + "دوباره تلاش کنید یا لغو کنید.",
                            ik([cancel_row()]),
                        )
                    return
                if kind == "owner_hp_all":
                    try:
                        amount = game.parse_money_amount(text)
                        msg = await game.admin_adjust_hp_all(pid, amount)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}")
                    except Exception:
                        log.exception("owner_hp_all")
                        await reply(message, "❌ خطا در جون همگانی")
                    return
                if kind == "oapool_add":
                    raw = (text or "").strip()
                    if "|" in raw:
                        cid, rname = raw.split("|", 1)
                    else:
                        cid, rname = raw, "گروه رزرو اتحاد"
                    try:
                        msg = await game.alliance_groups.register(
                            pid, cid.strip(), rname.strip(), bot=bot
                        )
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except Exception as e:
                        await reply(message, f"❌ {e}")
                    return
                if kind == "owner_give_all":
                    try:
                        amount = game.parse_money_amount(text)
                        msg = await game.admin_give_all_players(pid, amount)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}")
                    except Exception:
                        log.exception("owner_give_all")
                        await reply(message, "❌ خطا در پول همگانی")
                    return
                if kind == "admin_money":
                    try:
                        parts = text.replace("،", " ").replace(",", " ").split()
                        if len(parts) < 2:
                            await reply(message, "فرمت: کدکشور مبلغ\nمثال: IR 5000000", ik([cancel_row()]))
                            return
                        ccode = parts[0].upper()
                        amount = game.parse_money_amount(parts[1])
                        msg = await game.admin_money(pid, ccode, amount)
                        await _clear_pending(game, pid)
                    except GameError as e:
                        msg = f"❌ {e}"
                    except Exception as e:
                        log.exception("admin_money pending")
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner) if "موفق" in str(msg) or "✅" in str(msg) else None)
                    if "✅" not in str(msg) and pid in _pending:
                        await reply(message, "دوباره مبلغ را بفرستید یا لغو کنید.", ik([cancel_row()]))
                    return
                if kind == "reset_phrase":
                    await _clear_pending(game, pid)
                    try:
                        msg = await game.full_reset(pid, text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return

                if kind == "global_tax_amount":
                    await _clear_pending(game, pid)
                    try:
                        amount = parse_amount(text)
                        result = await game.global_tax(pid, amount)
                        msg = (
                            f"✅ مالیات سراسری انجام شد\n"
                            f"مبلغ هر نفر: {int(result['amount']):,}\n"
                            f"تعداد مشمول: {result['taxed']}\n"
                            f"ردشده (موجودی کم): {result['skipped']}\n"
                            f"جمع واریز به سازمان ملل: {int(result['collected']):,}"
                        )
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "owner_eq_grant":
                    try:
                        tid = int(st.get("target") or 0)
                        if not tid:
                            await _clear_pending(game, pid)
                            await reply(message, "❌ شناسه بازیکن نامعتبر", main_kb(owner))
                            return
                        msg = await game.admin_grant_equipment_text(pid, tid, text)
                        await _clear_pending(game, pid)
                        await reply(
                            message,
                            msg,
                            ik([[("👤 بازگشت به کاربر", f"ng:ou:{tid}")], [("🏠 خانه", "ng:home")]]),
                        )
                    except GameError as e:
                        await reply(message, f"❌ {e}\nمتن تجهیزات را دوباره بفرستید یا لغو کنید.", ik([cancel_row()]))
                    except Exception as e:
                        log.exception("owner_eq_grant")
                        await reply(message, f"❌ خطا در ثبت تجهیزات: {e}", ik([cancel_row()]))
                    return
                if kind == "user_give_money":
                    try:
                        amount = game.parse_money_amount(text)
                        tid = int(st.get("tid") or 0)
                        if not tid:
                            await _clear_pending(game, pid)
                            await reply(message, "❌ شناسه بازیکن نامعتبر", main_kb(owner))
                            return
                        msg = await game.admin_give_to_player(pid, tid, amount)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}\nدوباره مبلغ را بفرستید یا لغو کنید.", ik([cancel_row()]))
                    except Exception:
                        log.exception("user_give_money")
                        await reply(message, "❌ خطا در افزودن پول. دوباره تلاش کنید.", ik([cancel_row()]))
                    return
                if kind == "user_take_money":
                    try:
                        amount = game.parse_money_amount(text)
                        tid = int(st.get("tid") or 0)
                        if not tid:
                            await _clear_pending(game, pid)
                            await reply(message, "❌ شناسه بازیکن نامعتبر", main_kb(owner))
                            return
                        msg = await game.admin_take_from_player(pid, tid, amount)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}\nدوباره مبلغ را بفرستید.", ik([cancel_row()]))
                    except Exception:
                        log.exception("user_take_money")
                        await reply(message, "❌ خطا در برداشت پول.", ik([cancel_row()]))
                    return
                if kind == "user_tax":
                    await _clear_pending(game, pid)
                    try:
                        amount = parse_amount(text)
                        msg = await game.admin_tax_user(pid, st["code"], amount)
                    except (ValueError, GameError) as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "condemn_speech":
                    await _clear_pending(game, pid)
                    try:
                        msg = await game.condemn_country(pid, st["code"], text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return

                if kind == "edit_start":
                    await _clear_pending(game, pid)
                    try:
                        msg = await game.set_setting(pid, "start_message", text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "edit_about":
                    await _clear_pending(game, pid)
                    try:
                        msg = await game.set_setting(pid, "about_message", text)
                    except GameError as e:
                        msg = f"❌ {e}"
                    await reply(message, msg, main_kb(owner))
                    return
                if kind == "owner_wallet_charge":
                    try:
                        amount = game.parse_money_amount(text)
                        tid = int(st.get("target"))
                        if amount <= 0:
                            await reply(message, "❌ مبلغ باید بزرگ‌تر از صفر باشد.", ik([cancel_row()]))
                            return
                        msg = await game.legendary.admin_charge_wallet(pid, tid, amount)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    except Exception as e:
                        log.exception("owner_wallet_charge")
                        await reply(message, f"❌ خطا در شارژ کیف پول: {e}", ik([cancel_row()]))
                    return
                if kind == "owner_leg_price":
                    try:
                        price = game.parse_money_amount(text)
                        ic = st.get("item")
                        msg = await game.legendary.set_price(pid, ic, price)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    except Exception as e:
                        log.exception("owner_leg_price")
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    return
                if kind == "owner_leg_uses":
                    try:
                        raw = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
                        uses = int(float(raw.replace(",", "").replace("،", "").replace(" ", "")))
                        ic = st.get("item")
                        msg = await game.legendary.set_uses(pid, ic, uses)
                        await _clear_pending(game, pid)
                        await reply(message, msg, main_kb(owner))
                    except GameError as e:
                        await reply(message, f"❌ {e}", ik([cancel_row()]))
                    except Exception as e:
                        log.exception("owner_leg_uses")
                        await reply(message, "❌ عدد استفاده نامعتبر است. مثال: 20", ik([cancel_row()]))
                    return
                if kind == "owner_player_search":
                    try:
                        hits = await game.search_players(text, limit=30)
                        await _clear_pending(game, pid)
                        if not hits:
                            await reply(
                                message,
                                "❌ بازیکنی پیدا نشد." + "\n"
                                + "دوباره با @username یا شناسه جستجو کنید.",
                                ik([
                                    [("🔍 جستجوی دوباره", "ng:o:psearch")],
                                    [("⬅️ لیست کاربران", "ng:o:players:0")],
                                    back_row(),
                                ]),
                            )
                            return
                        rows = []
                        lines_out = [f"🔍 نتیجه جستجو برای: {text}", f"تعداد: {len(hits)}", ""]
                        for p in hits:
                            cname = p.get("country_label") or "بدون کشور"
                            un = p.get("display_name") or p.get("username") or "بدون‌نام"
                            uname = p.get("username")
                            at = f"@{uname}" if uname else ""
                            pid_s = p["player_id"]
                            lines_out.append(f"• {un} {at} | {cname} | {pid_s}")
                            label = f"{un} | {cname} | {pid_s}"
                            rows.append([(label[:48], f"ng:ou:{pid_s}")])
                        rows.append([("🔍 جستجوی دوباره", "ng:o:psearch")])
                        rows.append([("⬅️ لیست کاربران", "ng:o:players:0")])
                        rows.append(back_row())
                        await reply(message, "\n".join(lines_out), ik(rows))
                    except Exception as e:
                        log.exception("owner_player_search")
                        await reply(message, f"❌ خطا در جستجو: {e}", ik([cancel_row()]))
                    return

                if kind == "hacker_admin_level":
                    try:
                        msg = await game.hacker.admin_set_level(pid, int(text.strip()))
                        await _clear_pending(game, pid)
                        await reply(message, msg, ik([[("🎭 پنل هکر", "ng:ohack")]]))
                    except Exception as e:
                        await reply(message, f"❌ {e}")
                    return
                if kind == "hacker_admin_xp":
                    try:
                        msg = await game.hacker.admin_set_xp(pid, int(text.strip().replace(",", "")))
                        await _clear_pending(game, pid)
                        await reply(message, msg, ik([[("🎭 پنل هکر", "ng:ohack")]]))
                    except Exception as e:
                        await reply(message, f"❌ {e}")
                    return
                if kind == "hacker_admin_treasury":
                    try:
                        amt = parse_amount(text)
                        msg = await game.hacker.admin_set_treasury(pid, amt)
                        await _clear_pending(game, pid)
                        await reply(message, msg, ik([[("🎭 پنل هکر", "ng:ohack")]]))
                    except Exception as e:
                        await reply(message, f"❌ {e}")
                    return

                
                if kind == "owner_mass_deduct":
                    if not game.is_owner(pid):
                        await reply(message, "❌ فقط مالک")
                        await _clear_pending(game, pid)
                        return
                    raw = (text or "").replace(",", "").replace("٬", "").replace(" ", "").strip()
                    try:
                        amount = float(raw)
                    except Exception:
                        await reply(message, "❌ یک عدد معتبر بنویسید. مثال: 50000000")
                        return
                    if amount <= 0:
                        await reply(message, "❌ مبلغ باید بزرگ‌تر از صفر باشد.")
                        return
                    try:
                        msg = await game.admin_mass_deduct_treasury(pid, amount)
                    except GameError as e:
                        msg = f"❌ {e}"
                    except Exception as e:
                        log.exception("mass deduct")
                        msg = f"❌ {e}"
                    await _clear_pending(game, pid)
                    await reply(message, msg)
                    return

if kind == "owner_set_hp":
                    try:
                        raw = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
                        for ch in ("‎", "‏", "​", "‌", "‍", "﻿", " "):
                            raw = raw.replace(ch, "")
                        raw = raw.replace(",", "").replace("،", "").replace(" ", "")
                        tid = int(st.get("target"))
                        msg = await game.admin_set_hp(pid, tid, raw)
                        await _clear_pending(game, pid)
                        await reply(
                            message,
                            msg,
                            ik([
                                [("👤 بازگشت به کاربر", f"ng:ou:{tid}")],
                                [("⬅️ لیست کاربران", "ng:o:players:0")],
                                back_row(),
                            ]),
                        )
                    except GameError as e:
                        await reply(
                            message,
                            f"❌ {e}\nفرمت: فعلی/سقف مثل 300/1000 یا 4000/4000",
                            ik([cancel_row()]),
                        )
                    except Exception as e:
                        log.exception("owner_set_hp")
                        await reply(
                            message,
                            "❌ فرمت نامعتبر است.\nمثال: 300/1000 یا 4000/4000",
                            ik([cancel_row()]),
                        )
                    return

                # Unknown pending step — do not swallow input silently
                await _clear_pending(game, pid)
                await reply(
                    message,
                    "❌ این مرحله ورودی منقضی یا نامعتبر بود. دوباره از منو اقدام کنید.",
                    main_kb(owner),
                )
                return

            # ---- main menu ----
            if text in ("/start", "شروع", "منو", "menu") or text.startswith("/start"):
                try:
                    await game.record_start(pid)
                except Exception:
                    log.exception("record_start")
                start_msg = await game.get_setting("start_message", game.DEFAULT_START)
                nav_home(pid)
                await reply(message, start_msg, main_kb(owner, bool(code)))
                # deep-link referral: /start WW123456
                payload = ""
                if text.startswith("/start"):
                    parts = text.split(maxsplit=1)
                    if len(parts) > 1:
                        payload = parts[1].strip()
                if payload:
                    try:
                        ref_msg = await game.apply_referral_code(pid, payload)
                        await reply(message, ref_msg, main_kb(owner))
                    except GameError as e:
                        err = str(e)
                        if "کشور" in err:
                            _pending[pid] = {"kind": "ref_code", "preset": payload}
                            await reply(
                                message,
                                "🎟 کد دعوت ذخیره شد.\n"
                                "بعد از انتخاب کشور، همین کد خودکار اعمال می‌شود یا دوباره کد را بفرستید.\n"
                                f"کد: {payload}",
                                main_kb(owner),
                            )
                        else:
                            await reply(message, f"❌ {e}", main_kb(owner))
                    except Exception:
                        log.exception("start referral payload")
                return

            if text == BTN_NPT:
                if not code:
                    await reply(message, "برای درخواست NPT ابتدا باید کشور داشته باشید.", main_kb(owner, False))
                    return
                if await game.is_group(code):
                    await reply(message, "گروهک‌ها امکان عضویت در NPT ندارند.", main_kb(owner, True))
                    return
                c = await game.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
                st = "عضو NPT" if c and int(c.get("npt_member") or 0) == 1 else "غیرعضو NPT"
                cname = (c or {}).get("name_fa") or code
                rows = [
                    [("✅ درخواست عضویت در NPT", "ng:npt:join")],
                    [("🚪 درخواست خروج از NPT", "ng:npt:leave")],
                    [("⬅️ بازگشت", "ng:home")],
                ]
                await reply(
                    message,
                    f"☢ پیمان منع گسترش سلاح‌های هسته‌ای (NPT)\n"
                    f"کشور: {cname}\n"
                    f"وضعیت فعلی: {st}\n\n"
                    f"درخواست شما برای مالک ارسال می‌شود و پس از تأیید/رد، در گروه و پیوی اطلاع داده می‌شود.\n"
                    f"از دکمه‌های زیر عضویت یا خروج را انتخاب کنید.",
                    ik(rows),
                )
                return

            if text == BTN_MORE:

                nav_push(pid, "more")
                await reply(message, more_menu_text(), ik(more_menu_rows()))
                return

            if text == BTN_PICK:
                try:
                    if code:
                        await reply(message, "شما هم‌اکنون یک کشور/گروهک دارید.", main_kb(owner))
                        return
                    countries = await game.list_countries()
                    free_c = [
                        c for c in countries
                        if not c.get("owner_player_id")
                        and str(c.get("entity_type") or "country") not in ("group", "hacker", "special")
                    ]
                    free_g = [
                        c for c in countries
                        if not c.get("owner_player_id")
                        and str(c.get("entity_type") or "") == "group"
                    ]
                    rows = []
                    if free_c:
                        rows.append([("—— کشورها ——", "ng:noop")])
                    for c in free_c[:40]:
                        rows.append([(
                            f"{c.get('flag') or ''} {c.get('name_fa') or c.get('country_code')}",
                            f"ng:claim:{c['country_code']}",
                        )])
                    if free_g:
                        rows.append([("—— گروهک‌ها ——", "ng:noop")])
                        for c in free_g:
                            if str(c.get("country_code") or "").upper() == HACKER_CODE:
                                continue
                            rows.append([(
                                f"⬛ {c.get('name_fa') or c.get('country_code')}",
                                f"ng:claim:{c['country_code']}",
                            )])
                    rows.append([("—— شخصی‌سازی‌شده ——", "ng:noop")])
                    rows.append([(f"🎭 {HACKER_NAME_FA}", f"ng:claim:{HACKER_CODE}")])
                    # other personalized countries (free or claimable by this player)
                    try:
                        for scode, smeta in PERSONALIZED.items():
                            crow = await game.db.fetchrow(
                                "SELECT owner_player_id, is_destroyed FROM ng_countries WHERE country_code=$1",
                                (scode,),
                            )
                            owned = crow and crow.get("owner_player_id")
                            destroyed = crow and int(crow.get("is_destroyed") or 0)
                            if destroyed:
                                continue
                            flag = smeta.get("flag") or "🏷"
                            name = smeta.get("name_fa") or scode
                            if owned:
                                rows.append([(f"{flag} {name} (دارای بازیکن)", "ng:noop")])
                            else:
                                rows.append([(f"{flag} {name}", f"ng:claim:{scode}")])
                    except Exception:
                        log.exception("personalized claim list")
                    rows.append(back_row())
                    await reply(
                        message,
                        "🗺 انتخاب کنید:\nکشورها و گروهک‌های آزاد.\nگروهک‌ها عضو NPT نمی‌شوند.",
                        ik(rows),
                    )
                except Exception as e:
                    log.exception("BTN_PICK")
                    await reply(message, f"❌ خطا در فهرست کشورها: {e}", main_kb(owner))
                return

            if text == BTN_MY:
                nav_push(pid, "country")
                if not code:
                    await reply(message, "ابتدا «انتخاب کشور» را بزنید.", main_kb(owner))
                    return
                nav_push(pid, "country")
                card = await game.country_card(code)
                rows = [
                    [("🏛 کنترل کشور", "ng:ctrl")],
                    [("✅ عضویت NPT", "ng:npt:join"), ("🚪 خروج NPT", "ng:npt:leave")],
                    [("📦 انبار", "ng:go:inv"), ("💰 اقتصاد", "ng:go:eco")],
                    [("🛒 فروشگاه", "ng:shophome"), ("📜 گزارش", "ng:go:rep")],
                    back_row(),
                ]
                await reply(
                    message,
                    card + chr(10) + chr(10) + "☢ برای عضویت/خروج از پیمان NPT از دکمه‌های زیر استفاده کنید.",
                    ik(rows),
                )
                return

            if text == BTN_CTRL:
                nav_push(pid, "ctrl")
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                try:
                    text_c = await game.control.panel_text(code)
                except Exception:
                    log.exception("control panel")
                    text_c = "کنترل کشور"
                rows = [
                    [("📜 تصویب قوانین", "ng:ctrl:laws")],
                    [("🌊 کنترل تنگه‌ها", "ng:ctrl:straits")],
                    [("✈️ پروازها", "ng:ctrl:flights"), ("🚢 دریایی", "ng:ctrl:maritime")],
                    [("🌐 اینترنت", "ng:ctrl:net")],
                    back_row(),
                ]
                await reply(message, text_c, ik(rows))
                return

            if text == BTN_ECO:
                nav_push(pid, "eco")
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                nav_push(pid, "eco")
                await reply(message, await game.economy_card(code), main_kb(owner))
                return


            if text == BTN_WALLET:
                try:
                    txt = await game.legendary.wallet_text(pid)
                except Exception:
                    log.exception("wallet")
                    txt = "خطا در کیف پول"
                rows = [
                    [("💳 واریز به کیف پول", "ng:wallet_deposit")],
                    [("🎁 فروشگاه لجندری", "ng:legshop")],
                    [("🎁 استفاده از آیتم", "ng:leguse")],
                    back_row(),
                ]
                await reply(message, txt, ik(rows))
                return

            if text == BTN_SHOP:
                nav_push(pid, "shop")
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                try:
                    await game.ensure_shop_catalog()
                except Exception:
                    log.exception("shop catalog seed")
                catmap = getattr(game, "_cat", None) or {}
                if not catmap:
                    try:
                        from modules.ng.catalog import CATALOG as _CAT
                        catmap = {x["item_code"]: x for x in _CAT}
                    except Exception:
                        catmap = {}
                await reply(message, v4ui.shop_hub_text(), ik(v4ui.shop_hub_rows(catmap)))
                return

            if text == BTN_INV:
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                nav_push(pid, "inv")
                await reply(message, v4ui.inv_hub_text(), ik(v4ui.inv_hub_rows()))
                return

            if text == BTN_MKT:
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                listings = await game.market_list(0)
                rows = []
                for L in listings:
                    name = game._cat.get(L["item_code"], {}).get("name_fa", L["item_code"])
                    rows.append([(
                        f"#{L['id']} {name} ×{int(float(L['quantity']))} | {int(float(L['unit_price'])):,}",
                        f"ng:mbuy:{L['id']}",
                    )])
                rows.append([("📢 ثبت آگهی جدید", "ng:mnew"), ("📋 آگهی‌های من", "ng:mmine")])
                rows.append([("🔄 تازه‌سازی", "ng:more:mkt")])
                rows.append(back_row())
                await reply(message, "🌐 بازار آزاد جهانی\nآگهی‌ها را ببینید یا آگهی بگذارید:", ik(rows))
                return

            if text == BTN_TRADE:
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                rows = [
                    [("💰 کمک مالی", "ng:trade:money"), ("📦 کمک نظامی", "ng:trade:army")],
                        [("🛢 کمک نفتی", "ng:trade:oil")],
                    back_row(),
                ]
                await reply(message, "🚢 تجارت و کمک بین کشورها", ik(rows))
                return

            if text == BTN_DIPLO:
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                nav_push(pid, "diplo")
                rows = [
                    [("🌍 فهرست کشورها", "ng:diplo:list")],
                    [("💰 کمک مالی", "ng:trade:money"), ("📦 کمک نظامی", "ng:trade:army")],
                        [("🛢 کمک نفتی", "ng:trade:oil")],
                    [("🤝 اتحادها", "ng:go:ally")],
                    back_row(),
                ]
                await reply(message, "🤝 روابط خارجی — کمک، دیپلماسی و کشورها", ik(rows))
                return

            if text == BTN_PEACE:
                await reply(
                    message,
                    "پیمان صلح حذف شده است.\nبه‌جای آن از «🤝 اتحادها» استفاده کنید.",
                    main_kb(owner),
                )
                return


            if text in (BTN_ATTACK, "⚔️ نظامی", v4ui.BTN_MIL):
                nav_push(pid, "attack")
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                meta = await game.db.fetchrow("SELECT war_enabled FROM world_meta WHERE id=1")
                war_on = bool(meta and int(meta.get("war_enabled") or 0))
                # سازمان ملل و گروه هکری آنانیموس همیشه منوی نظامی کامل دارند
                is_un = bool(owner) and str(code).upper() in ("UN", "UN2", "UN3")
                is_hack = False  # ANON has no war bypass
                combat_on = war_on or is_un or is_hack
                rows = []
                if combat_on:
                    rows.append([("⚔️ حمله نظامی", "ng:atkmenu")])
                # هک و پدافند همیشه در دسترس (وابسته به جنگ نیست)
                rows.append([("💻 هک و امنیت", "ng:cyber")])
                rows.append([("🛡 وضعیت پدافند من", "ng:mydef")])
                rows.append([("🎁 استفاده از آیتم لجندری", "ng:leguse")])
                rows.append(back_row())
                if is_un and not war_on:
                    head = (
                        "🇺🇳 سازمان ملل — دسترسی ویژه" + "\n"
                        + "جنگ برای بازیکنان بسته است؛ حمله نظامی برای شما باز است." + "\n"
                        + "هک و پدافند برای همه فعال است."
                    )
                elif war_on:
                    head = "⚔️ عملیات نظامی و سایبری:"
                else:
                    head = (
                        "⚠️ جنگ جهان بسته است — حمله نظامی غیرفعال." + "\n"
                        + "💻 هک و امنیت و وضعیت پدافند فعال هستند." + "\n"
                        + "همچنین می‌توانید از آیتم‌های لجندری استفاده کنید:"
                    )
                await reply(message, head, ik(rows))
                return

            if text == BTN_STMT:
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                _pending[pid] = {"kind": "statement"}
                await reply(message, "متن بیانیه رسمی را بنویسید و ارسال کنید:", main_kb(owner))
                return

            if text == BTN_WORLD:
                nav_push(pid, "world")
                await reply(message, await game.world_status_text(for_owner=owner), main_kb(owner))
                return

            if text == BTN_REPORT:
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                rows = await game.db.fetch(
                    "SELECT * FROM ng_activity WHERE country_code=$1 ORDER BY id DESC", (code,)
                )
                lines = ["📊 گزارش فعالیت‌ها"] + [f"• {r['summary'][:120]}" for r in rows[:15]]
                if len(lines) == 1:
                    lines.append("هنوز گزارشی نیست.")
                await reply(message, "\n".join(lines), main_kb(owner))
                return


            if text == BTN_WORKSHOP:
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                await game.complete_due_jobs(code)
                rows = [
                    [("📊 وضعیت کارگاه", "ng:ws:status")],
                    [("⚛ تولید اورانیوم", "ng:ws:uranium"), ("🔬 فناوری صلح‌آمیز", "ng:ws:research")],
                    [("⬆️ ارتقای کارگاه", "ng:ws:upgrade")],
                    [("💣 ساخت بمب اتم", "ng:ws:bomb")],
                    back_row(),
                ]
                await reply(message, await game.workshop_status(code), ik(rows))
                return


            if text == BTN_DONATE or text == "💎 منم حمایت کن":
                nav_push(pid, "donate")
                try:
                    body = await game.donations.intro_text()
                except Exception:
                    body = "💎 حمایت مالی\n\nآیا واقعاً از حمایت کردن مطمئنی؟\nاز دادن درخواست الکی خودداری کنید."
                await reply(
                    message,
                    body,
                    ik([
                        [("✅ بله", "ng:donate:yes"), ("❌ خیر", "ng:donate:no")],
                        back_row(),
                    ]),
                )
                return


            if text == BTN_ABOUT:
                about = await game.get_setting("about_message", game.DEFAULT_ABOUT)
                await reply(message, about, main_kb(owner))
                return


            if text == BTN_ALLY:
                nav_push(pid, "ally")
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                mem = await game.alliances.member_of(code)
                if mem:
                    a = await game.alliances.get(mem["alliance_id"])
                    if a:
                        try:
                            gate = await game.alliance_groups.membership_gate(pid, a, bot=bot)
                        except Exception:
                            log.exception("ally gate")
                            gate = None
                        if gate:
                            await reply(message, gate, main_kb(owner))
                            return
                    mems = await game.alliances.members(mem["alliance_id"])
                    labels = {}
                    for m in mems:
                        labels[m["country_code"]] = await game.country_label(m["country_code"])
                    text_a = game.alliances.card_text(a, mems, labels)
                    rows = [
                        [("👥 اعضا", f"ng:amembers:{a['id']}"), ("🏦 خزانه", f"ng:atreasure:{a['id']}")],
                        [("🚪 خروج از اتحاد", "ng:aleave")],
                    ]
                    if mem.get("role") == "founder":
                        rows.insert(1, [("⚙️ مدیریت", f"ng:amgmt:{a['id']}")])
                        rows.insert(2, [("💸 تقسیم مساوی خزانه", "ng:asplit")])
                    rows.append(back_row())
                    await reply(message, text_a, ik(rows))
                else:
                    allies = await game.alliances.list_active()
                    rows = [[("➕ ساخت اتحاد", "ng:acreate")]]
                    for a in allies[:25]:
                        mems = await game.alliances.members(a["id"])
                        rows.append([(f"{a['name']} ({len(mems)}/{a['max_members']})", f"ng:aview:{a['id']}")])
                    rows.append(back_row())
                    await reply(message, "🤝 اتحادها — فهرست فعال یا ساخت اتحاد جدید:", ik(rows))
                return

            if text == BTN_REF:
                text_r = await game.referral_panel_text(pid)
                rows = [
                    [("📋 نمایش کد دعوت", "ng:refcode")],
                    [("✍️ وارد کردن کد دعوت", "ng:refenter")],
                    back_row(),
                ]
                await reply(message, text_r, ik(rows))
                return

            if text == BTN_GUIDE:
                nav_push(pid, "guide")
                rows = guide_menu_rows()
                await reply(
                    message,
                    "📖 راهنمای بازی\n\nبخش موردنظر را انتخاب کنید. همه توضیحات بر اساس امکانات واقعی بازی نوشته شده‌اند.",
                    ik(rows),
                )
                return

            if text == BTN_TREATY:
                if not code:
                    await reply(message, "هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                c = await game.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
                st = "عضو NPT" if int(c["npt_member"]) else "غیرعضو NPT"
                rows = [
                    [("عضویت در NPT", "ng:npt:join"), ("خروج از NPT", "ng:npt:leave")],
                    back_row(),
                ]
                await reply(message, f"⚖ پیمان‌ها\nوضعیت فعلی: {st}", ik(rows))
                return

            # Owner panel is command-only: /admin /owner /panel

        except Exception:
            log.exception("on_message")
            try:
                pid_ex = _uid(message)
                ban_ex = None
                try:
                    if pid_ex:
                        ban_ex = await game.get_ban_info(pid_ex)
                except Exception:
                    ban_ex = None
                kb_ex = banned_kb() if ban_ex else main_kb(False)
                await message.reply("خطای داخلی. دوباره تلاش کنید.", components=kb_ex)
            except Exception:
                pass

    @bot.listen("on_callback")
    async def on_callback(cq):
        try:
            data = (getattr(cq, "data", None) or "").strip()
            pid = _uid(cq)
            if not pid or not data:
                return
            # --- Nuclear attack confirm: early guaranteed feedback ---
            if data.startswith("ng:nukego:"):
                try:
                    if hasattr(cq, "answer"):
                        await cq.answer(text="حمله اتمی…", show_alert=False)
                except Exception:
                    pass
                msg0 = getattr(cq, "message", None)
                try:
                    await ensure(pid)
                except Exception:
                    pass
                code0 = await game.player_country(pid)
                dst = data.split(":")[-1]

                async def _nuke_out(text, kb=None):
                    body = str(text)[:3500]
                    comp = kb
                    if msg0 is not None:
                        for attr in ("edit_text", "edit", "edit_message_text"):
                            fn = getattr(msg0, attr, None)
                            if not callable(fn):
                                continue
                            try:
                                try:
                                    await fn(body, components=comp)
                                    return
                                except TypeError:
                                    await fn(body)
                                    return
                            except Exception:
                                pass
                        try:
                            await msg0.reply(body, components=comp)
                            return
                        except Exception:
                            log.exception("nuke reply")
                if not code0:
                    await _nuke_out("❌ هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    result = await game.attack_nuclear(code0, dst, pid)
                    if not result or not str(result).strip():
                        result = "✅ حمله اتمی با موفقیت انجام شد."
                    try:
                        if hasattr(cq, "answer"):
                            await cq.answer(text="✅ حمله اتمی انجام شد", show_alert=True)
                    except Exception:
                        pass
                    await _nuke_out(
                        result,
                        ik([[("⚔️ منوی حمله", "ng:atkmenu")], [("🏠 خانه", "ng:home")]]),
                    )
                except GameError as e:
                    try:
                        if hasattr(cq, "answer"):
                            await cq.answer(text=str(e)[:180], show_alert=True)
                    except Exception:
                        pass
                    await _nuke_out(f"❌ {e}", ik([[("⚔️ منوی حمله", "ng:atkmenu")]]))
                except Exception as e:
                    log.exception("nukego early")
                    await _nuke_out(f"❌ خطا در حمله اتمی: {e}", ik([[("⚔️ منوی حمله", "ng:atkmenu")]]))
                return

            # --- Lucky spin: handle early (no 30s menu lock / guaranteed UI update) ---
            if data in ("ng:spin", "ng:spin:panel", "ng:spin:go"):
                msg0 = getattr(cq, "message", None)
                owner0 = False
                try:
                    await ensure(pid)
                    owner0 = game.is_owner(pid)
                except Exception:
                    pass

                async def _spin_out(text, kb=None):
                    body = str(text)[:3500]
                    comp = kb if kb is not None else None
                    # Prefer edit current message so user always sees change
                    if msg0 is not None:
                        for attr in ("edit_text", "edit", "edit_message_text"):
                            fn = getattr(msg0, attr, None)
                            if not callable(fn):
                                continue
                            try:
                                if comp is not None:
                                    try:
                                        await fn(body, components=comp)
                                        return
                                    except TypeError:
                                        pass
                                await fn(body)
                                return
                            except Exception:
                                log.debug("spin edit failed %s", attr, exc_info=True)
                        try:
                            await msg0.reply(body, components=comp)
                            return
                        except Exception:
                            log.exception("spin reply failed")
                    try:
                        await reply(msg0, body, comp) if msg0 is not None else None
                    except Exception:
                        log.exception("spin reply2 failed")

                try:
                    if data in ("ng:spin", "ng:spin:panel"):
                        try:
                            txt = await game.lucky_spin_panel(pid)
                        except Exception:
                            log.exception("spin panel early")
                            txt = "🎰 چرخ شانس"
                        rows = [
                            [("🎲 چرخاندن چرخ", "ng:spin:go")],
                            back_row(),
                        ]
                        try:
                            if hasattr(cq, "answer"):
                                await cq.answer(text="چرخ شانس", show_alert=False)
                        except Exception:
                            pass
                        await _spin_out(txt, ik(rows))
                        return

                    # data == ng:spin:go
                    try:
                        win_msg = await game.lucky_spin(pid)
                        ok = True
                    except GameError as e:
                        win_msg = f"❌ {e}"
                        ok = False
                    except Exception as e:
                        log.exception("spin go early")
                        win_msg = f"❌ خطا در چرخ شانس: {e}"
                        ok = False
                    # Toast / alert so user always sees feedback
                    try:
                        short = (win_msg or "")[:180].replace("\n", " ")
                        if hasattr(cq, "answer"):
                            await cq.answer(text=short or ("✅ انجام شد" if ok else "خطا"), show_alert=True)
                    except Exception:
                        pass
                    rows = [
                        [("🎲 دوباره بچرخان", "ng:spin:go"), ("🎰 وضعیت", "ng:spin")],
                        back_row(),
                    ]
                    await _spin_out(win_msg, ik(rows))
                    return
                except Exception:
                    log.exception("early spin handler")
                    try:
                        if hasattr(cq, "answer"):
                            await cq.answer(text="خطا در چرخ شانس", show_alert=True)
                    except Exception:
                        pass
                    return

            try:
                if hasattr(cq, "answer"):
                    await cq.answer(text="⏳", show_alert=False)
            except Exception:
                pass
            # 30s menu timeout for interactive ng: menus
            try:
                msg_to = getattr(cq, "message", None)
                mid_to = None
                if msg_to is not None:
                    mid_to = getattr(msg_to, "message_id", None) or getattr(msg_to, "id", None)
                if data.startswith("ng:") and mid_to is not None and not data.startswith("ng:spin") and not data.startswith("ng:nukego"):
                    key = (int(pid), int(mid_to))
                    if not MENU_SESSIONS.owned_by(pid, mid_to):
                        try:
                            await cq.answer(FORBIDDEN_MENU_TEXT, show_alert=True)
                        except Exception:
                            pass
                        return
                    if key in MENU_SESSIONS._sessions and not MENU_SESSIONS.is_alive(pid, mid_to):
                        try:
                            await cq.answer(EXPIRED_MENU_TEXT, show_alert=True)
                        except Exception:
                            pass
                        try:
                            if msg_to is not None:
                                for attr in ("edit_text", "edit"):
                                    fn = getattr(msg_to, attr, None)
                                    if callable(fn):
                                        await fn(EXPIRED_MENU_TEXT)
                                        break
                        except Exception:
                            pass
                        MENU_SESSIONS.expire(pid, mid_to)
                        return
                    MENU_SESSIONS.touch(pid, mid_to)
            except Exception:
                log.exception("menu timeout check")
            log.info("callback data=%s pid=%s", data[:64], pid)
            if data.startswith("ng:leg") or data.startswith("ng:legendary"):
                await out("⛔ سیستم آیتم‌های افسانه‌ای در این نسخه حذف شده است.")
                return
            data0 = str(getattr(cq, "data", None) or getattr(cq, "callback_data", None) or "")
            banned_user = False
            try:
                await ensure(pid)
            except GameError as e:
                err = str(e)
                msg = getattr(cq, "message", None)
                if err == "BANNED" or "مسدود" in err:
                    banned_user = True
                    if not data0.startswith("ng:tix"):
                        ban = await game.get_ban_info(pid)
                        notice = game.format_ban_user_notice(ban, None) if ban else "شما مسدود شده‌اید."
                        if msg:
                            try:
                                await msg.reply(notice[:3500], components=banned_kb())
                            except Exception:
                                pass
                        return
                else:
                    if msg:
                        await msg.reply(f"❌ {e}")
                    return
            owner = game.is_owner(pid)
            code = None if banned_user else await game.player_country(pid)

            msg = getattr(cq, "message", None)

            async def out(text, kb=None, *, force_new: bool = False):
                body = str(text)[:3500]
                comp = kb if kb is not None else main_kb(owner)
                try:
                    mid_out = None
                    if msg is not None:
                        mid_out = getattr(msg, "message_id", None) or getattr(msg, "id", None)
                    if mid_out is not None:
                        MENU_SESSIONS.touch(pid, mid_out)
                except Exception:
                    pass
                if not force_new and msg is not None:
                    for attr in ("edit_text", "edit", "edit_message_text"):
                        fn = getattr(msg, attr, None)
                        if callable(fn):
                            try:
                                await fn(body, components=comp)
                                return
                            except TypeError:
                                try:
                                    await fn(body)
                                    return
                                except Exception:
                                    pass
                            except Exception:
                                log.debug("out.%s failed", attr, exc_info=True)
                    # Bale Message.edit_reply_markup style
                    try:
                        if hasattr(msg, "edit_caption"):
                            await msg.edit_caption(body, components=comp)
                            return
                    except Exception:
                        pass
                try:
                    if msg is not None:
                        await msg.reply(body, components=comp)
                        return
                except Exception:
                    log.exception("out.reply failed")
                try:
                    chat = getattr(msg, "chat", None) if msg is not None else None
                    chat_id = getattr(chat, "id", None) or getattr(chat, "chat_id", None)
                    if chat_id is not None:
                        await bot.send_message(chat_id, body, components=comp)
                except Exception:
                    log.exception("out.send_message failed")


            if data == "ng:guide" or data.startswith("ng:guide:"):
                if data == "ng:guide":
                    rows = guide_menu_rows()
                    await out(
                        "📖 راهنمای بازی\n\nبخش موردنظر را انتخاب کنید.",
                        ik(rows),
                    )
                    return
                parts = data.split(":")
                section = parts[2] if len(parts) > 2 else ""
                page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
                text, rows = guide_page(section, page)
                await out(text, ik(rows))
                return

            # owner callbacks — server-side authorization
            if data.startswith("ng:dcd") or data.startswith("ng:orec") or data.startswith("ng:o") or data.startswith("ng:owar") or data.startswith("ng:onuke") or data.startswith("ng:ostmt") or data.startswith("ng:onpt") or data.startswith("ng:ologs") or data.startswith("ng:ostart") or data.startswith("ng:oabout") or data.startswith("ng:oban") or data.startswith("ng:obansearch") or data.startswith("ng:ounban") or data.startswith("ng:otix") or data.startswith("ng:omoney") or data.startswith("ng:oreset") or data.startswith("ng:sapp") or data.startswith("ng:srej") or data.startswith("ng:nptok") or data.startswith("ng:nptno") or data.startswith("ng:logtoggle") or data.startswith("ng:otest") or data.startswith("ng:oforce") or data.startswith("ng:ou") or data.startswith("ng:otax") or data.startswith("ng:ocondemn") or data.startswith("ng:oureset") or data.startswith("ng:oally") or data.startswith("ng:oaway") or data.startswith("ng:orefstats") or data.startswith("ng:odbl") or data.startswith("ng:oudbl") or data.startswith("ng:olaws") or data.startswith("ng:lawok") or data.startswith("ng:lawno") or data.startswith("ng:oprice") or data.startswith("ng:odisc") or data.startswith("ng:ogiveall") or data.startswith("ng:odaily") or data.startswith("ng:ohp") or data.startswith("ng:osethp") or data.startswith("ng:oleg") or data.startswith("ng:owallet") or data.startswith("ng:olegprices") or data.startswith("ng:odonate") or data.startswith("ng:donrev"):
                if not owner:
                    await out("❌ دسترسی مجاز نیست.")
                    return
            elif data not in (
                "ng:cancel", "ng:joincheck",
            ) and not data.startswith("ng:joinlink") and not data.startswith("ng:joinurl"):
                # All gameplay requires forced membership when enabled
                if not owner and not await require_membership(pid, cq, True):
                    return

            # ---- cooldown owner controls (early, high priority) ----
            if data == "ng:ocdstd" or data == "ng:ocd:30" or data == "ng:ocd30":
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                try:
                    msg = await game.apply_standard_war_cooldowns(pid)
                    a = await game.attack_cooldown_sec()
                    n = await game.nuke_cooldown_sec()
                    await out(
                        msg
                        + chr(10)
                        + chr(10)
                        + f"خوانده‌شده از دیتابیس: حمله={a}ث | اتم={n}ث",
                        force_new=True,
                    )
                except GameError as e:
                    await out(f"❌ {e}", force_new=True)
                except Exception as e:
                    log.exception("ocdstd")
                    await out(f"❌ خطا در تنظیم کول‌داون: {e}", force_new=True)
                return

            # ---- legendary global lock (early) ----
            if data == "ng:llock" or data.startswith("ng:llock:"):
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                try:
                    parts = data.split(":")
                    if len(parts) >= 3 and parts[2] in ("0", "1"):
                        en = parts[2] == "1"
                        msg = await game.legendary.set_locked(pid, en)
                    else:
                        on = await game.legendary.is_locked()
                        msg = ("🔒 محدودیت لجندری: روشن" if on else "✅ محدودیت لجندری: خاموش")
                        msg += "\n" + (
                            "خرید و استفاده و همه اثرها غیرفعال‌اند."
                            if on else
                            "خرید و استفاده آزاد است."
                        )
                    on = await game.legendary.is_locked()
                    await out(
                        str(msg) + "\n\n" + ("وضعیت فعلی: 🔒 روشن" if on else "وضعیت فعلی: ✅ خاموش"),
                        ik([
                            [("🔒 روشن کردن محدودیت", "ng:llock:1")],
                            [("🔓 خاموش کردن محدودیت", "ng:llock:0")],
                            [("🔄 بررسی وضعیت", "ng:llock")],
                            [("⬅️ پنل مالک", "ng:opanel")],
                        ]),
                        force_new=True,
                    )
                except Exception as e:
                    log.exception("llock")
                    await out(f"❌ خطا در محدودیت لجندری: {e}", force_new=True)
                return
            if data.startswith("ng:oucd30on:") or data.startswith("ng:oucd30off:") or data.startswith("ng:oucd30:"):
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                try:
                    tid = int(str(data).split(":")[-1])
                except Exception:
                    await out("❌ شناسه نامعتبر", force_new=True)
                    return
                if data.startswith("ng:oucd30off:"):
                    enable = False
                elif data.startswith("ng:oucd30on:"):
                    enable = True
                else:
                    # toggle
                    try:
                        enable = not await game.has_fast_attack_cd(tid)
                    except Exception:
                        enable = True
                try:
                    msg = await game.set_fast_attack_cd(pid, tid, enable)
                    on = await game.has_fast_attack_cd(tid)
                    status = "⚡ فعال (۳۰ث)" if on else "⏱ عادی جهان"
                    rows = [
                        [("⚡ روشن ۳۰ث", f"ng:oucd30on:{tid}"), ("🕊 خاموش", f"ng:oucd30off:{tid}")],
                        [("👤 بازگشت پروفایل", f"ng:ou:{tid}")],
                        [("🏠 خانه", "ng:home")],
                    ]
                    await out(
                        msg + chr(10) + chr(10) + f"وضعیت فعلی: {status}",
                        ik(rows),
                        force_new=True,
                    )
                except GameError as e:
                    await out(f"❌ {e}", force_new=True)
                except Exception as e:
                    log.exception("oucd30 toggle")
                    await out(f"❌ خطا در کول‌داون ۳۰ث: {e}", force_new=True)
                return


            if data in ("ng:home", "ng:busy", "ng:cancel"):
                await _clear_pending(game, pid)
                nav_home(pid)
                if data == "ng:busy":
                    await out("این کشور دارای بازیکن است.", main_kb(owner))
                elif data == "ng:cancel":
                    await out("عملیات لغو شد.", main_kb(owner))
                else:
                    await out("🏠 منوی اصلی", main_kb(owner))
                return


            if data == "ng:more:npt":
                if not code:
                    await out("برای NPT ابتدا کشور انتخاب کنید.")
                    return
                if await game.is_group(code):
                    await out("گروهک‌ها عضو NPT نمی‌شوند.")
                    return
                c = await game.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
                st = "عضو NPT" if c and int(c.get("npt_member") or 0) == 1 else "غیرعضو NPT"
                cname = (c or {}).get("name_fa") or code
                await out(
                    f"☢ پیمان NPT\nکشور: {cname}\nوضعیت: {st}",
                    ik([
                        [("✅ درخواست عضویت", "ng:npt:join")],
                        [("🚪 درخواست خروج", "ng:npt:leave")],
                        back_row(),
                    ]),
                )
                return

            if data == "ng:more" or data.startswith("ng:more:"):
                nav_push(pid, "more")
                key = data.split(":")[-1] if data.startswith("ng:more:") else ""
                if key in ("", "home", "more"):
                    await out(more_menu_text(), ik(more_menu_rows()))
                    return
                if key == "attack":
                    if not code:
                        await out("هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.")
                        return
                    nav_push(pid, "attack")
                    await out(
                        "⚔️ حمله نظامی\n\nنوع درگیری را انتخاب کنید:",
                        ik([
                            [("🏞 زمینی", "ng:atk:ground"), ("✈️ هوایی", "ng:atk:air")],
                            [("🚢 دریایی", "ng:atk:sea")],
                            back_row(),
                        ]),
                    )
                    return
                if key == "ctrl":
                    if not code:
                        await out("هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.")
                        return
                    nav_push(pid, "ctrl")
                    await out(
                        "🏛 کنترل کشور\n\nمدیریت داخلی، تنگه‌ها و قوانین:",
                        ik([
                            [("🌊 تنگه‌ها", "ng:ctrl:straits"), ("📜 قوانین", "ng:ctrl:laws")],
                            [("📊 وضعیت کنترل", "ng:ctrl:status")],
                            back_row(),
                        ]),
                    )
                    return
                if key == "oil":
                    if not code:
                        await out("هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.")
                        return
                    nav_push(pid, "oil")
                    try:
                        txt = await game.oil_panel_text(code)
                    except Exception:
                        txt = "🛢 پنل نفت"
                    await out(
                        txt,
                        ik([
                            [("🛒 خرید نفت از فروشگاه", "ng:shop:mine")],
                            [("🤝 فروش نفت به بازیکن", "ng:oil:sell")],
                            [("📦 انبار", "ng:go:inv")],
                            back_row(),
                        ]),
                    )
                    return
                if key == "workshop":
                    if not code:
                        await out("هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.")
                        return
                    nav_push(pid, "workshop")
                    rows = [
                        [("📊 وضعیت کارگاه", "ng:ws:status")],
                        [("⚛ تولید اورانیوم", "ng:ws:uranium"), ("🔬 فناوری صلح‌آمیز", "ng:ws:research")],
                        [("⬆️ ارتقای کارگاه", "ng:ws:upgrade")],
                        [("💣 ساخت بمب اتم", "ng:ws:bomb")],
                        back_row(),
                    ]
                    await out("🏭 کارگاه — تولید و فناوری", ik(rows))
                    return
                if key == "diplo":
                    if not code:
                        await out("هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.")
                        return
                    nav_push(pid, "diplo")
                    rows = [
                        [("🌍 فهرست کشورها", "ng:diplo:list")],
                        [("💰 کمک مالی", "ng:trade:money"), ("📦 کمک نظامی", "ng:trade:army")],
                        [("🛢 کمک نفتی", "ng:trade:oil")],
                        [("🤝 اتحادها", "ng:go:ally")],
                        back_row(),
                    ]
                    await out("🤝 روابط خارجی — کمک، دیپلماسی و کشورها", ik(rows))
                    return
                if key == "mkt":
                    if not code:
                        await out("هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.")
                        return
                    nav_push(pid, "mkt")
                    try:
                        listings = await game.market_list(0)
                    except Exception:
                        listings = []
                    rows = []
                    for L in listings:
                        name = game._cat.get(L["item_code"], {}).get("name_fa", L["item_code"])
                        rows.append([(
                            f"#{L['id']} {name} ×{int(float(L['quantity']))} | {int(float(L['unit_price'])):,}",
                            f"ng:mbuy:{L['id']}",
                        )])
                    rows.append([("📢 ثبت آگهی جدید", "ng:mnew"), ("📋 آگهی‌های من", "ng:mmine")])
                    rows.append([("🔄 تازه‌سازی", "ng:more:mkt")])
                    rows.append(back_row())
                    await out("🌐 بازار آزاد جهانی\nآگهی‌ها را ببینید یا آگهی بگذارید:", ik(rows))
                    return
                if key == "trade":
                    if not code:
                        await out("هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.")
                        return
                    nav_push(pid, "trade")
                    rows = [
                        [("💰 کمک مالی", "ng:trade:money"), ("📦 کمک نظامی", "ng:trade:army")],
                        [("🛢 کمک نفتی", "ng:trade:oil")],
                        back_row(),
                    ]
                    await out("🚢 تجارت و کمک بین کشورها", ik(rows))
                    return
                if key == "treaty":
                    nav_push(pid, "treaty")
                    await out(
                        "⚖ پیمان‌ها" + chr(10)+chr(10) + "پیمان صلح قدیمی حذف شده است." + chr(10) + "از اتحادها برای همکاری پایدار استفاده کنید.",
                        ik([
                            [("🤝 اتحادها", "ng:go:ally")],
                            back_row(),
                        ]),
                    )
                    return
                if key == "wallet":
                    nav_push(pid, "wallet")
                    txt = (
                        "💰 کیف پول\n\n"
                        "سیستم آیتم‌های افسانه‌ای حذف شده است.\n"
                        "موجودی و اقتصاد اصلی کشور از بخش «کشور من» و «اقتصاد» مدیریت می‌شود."
                    )
                    await out(txt, ik([back_row()]))
                    return
                if key == "stmt":
                    nav_push(pid, "stmt")
                    _pending[pid] = {"kind": "statement"}
                    await out("📜 متن بیانیه را بنویسید (لینک مجاز نیست). برای لغو: لغو", ik([cancel_row()]))
                    return
                if key == "report":
                    nav_push(pid, "report")
                    try:
                        txt = await game.world_status_text(for_owner=owner)
                    except Exception:
                        txt = "📊 گزارش جهان"
                    await out(txt, ik([back_row()]))
                    return
                if key == "ref":
                    nav_push(pid, "ref")
                    try:
                        txt = await game.referral_panel_text(pid)
                    except Exception as e:
                        log.exception("referral more")
                        txt = "🎁 سیستم دعوت — " + str(e)
                    await out(txt, ik([
                        [("📋 نمایش کد دعوت", "ng:refcode")],
                        [("✍️ وارد کردن کد دعوت", "ng:refenter")],
                        back_row(),
                    ]))
                    return
                if key == "donate":
                    nav_push(pid, "donate")
                    try:
                        txt = await game.donations.intro_text()
                    except Exception:
                        txt = "💎 حمایت مالی\n\nآیا واقعاً از حمایت کردن مطمئنی؟\nاز دادن درخواست الکی خودداری کنید."
                    await out(
                        txt,
                        ik([
                            [("✅ بله", "ng:donate:yes"), ("❌ خیر", "ng:donate:no")],
                            back_row(),
                        ]),
                    )
                    return
                if key == "about":
                    txt = None
                    try:
                        row = await game.db.fetchrow(
                            "SELECT value FROM ng_bot_settings WHERE key=$1",
                            ("about_message",),
                        )
                        txt = (row or {}).get("value")
                    except Exception:
                        pass
                    await out(str(txt or "ℹ️ WORLD WAR — بازی کشور‌داری چندنفره در بله"), ik([back_row()]))
                    return
                await out(more_menu_text(), ik(more_menu_rows()))
                return

            if data == "ng:back":
                prev = nav_back(pid)
                await _clear_pending(game, pid)
                if not prev:
                    nav_home(pid)
                    await out("🏠 منوی اصلی", main_kb(owner))
                    return
                # Re-open previous high-level screens without dumping to home
                if prev == "country" and code:
                    card = await game.country_card(code)
                    rows = [
                        [("🏛 کنترل کشور", "ng:ctrl")],
                        [("📦 انبار", "ng:go:inv"), ("💰 اقتصاد", "ng:go:eco")],
                        [("📜 گزارش", "ng:go:rep")],
                        back_row(),
                    ]
                    await out(card, ik(rows))
                    return
                if prev == "ctrl" and code:
                    rows = [
                        [("📜 تصویب قوانین", "ng:ctrl:laws")],
                        [("🌊 کنترل تنگه‌ها", "ng:ctrl:straits")],
                        [("✈️ پروازها", "ng:ctrl:flights"), ("🚢 دریایی", "ng:ctrl:maritime")],
                        [("🌐 اینترنت", "ng:ctrl:net")],
                        back_row(),
                    ]
                    await out("🏛 کنترل کشور — سیاست داخلی", ik(rows))
                    return
                if prev == "eco" and code:
                    await out(await game.economy_card(code), ik([back_row()]))
                    return
                if prev == "shop":
                    cats = {}
                    for it in game._cat.values():
                        cats[it.get("category") or "other"] = cats.get(it.get("category") or "other", 0) + 1
                    rows = []
                    pair = []
                    for cat, n in list(cats.items())[:12]:
                        name = {"ground":"زمینی","air":"هوایی","sea":"دریایی","missile":"موشکی","defense":"پدافند","infra":"زیرساخت","nuclear":"هسته‌ای","mine":"منابع"}.get(cat, cat)
                        pair.append((f"{name} ({n})", f"ng:shop:{cat}"))
                        if len(pair) == 2:
                            rows.append(pair); pair = []
                    if pair:
                        rows.append(pair)
                    rows.append([("🛒 سبد خرید", "ng:cart"), ("✅ تسویه حساب", "ng:checkout")])
                    rows.append(back_row())
                    await out("🛒 فروشگاه", ik(rows))
                    return
                if prev == "attack":
                    await out("⚔️ بخش حمله", ik([[("انتخاب هدف", "ng:atk")], back_row()]))
                    return
                if prev == "owner" and owner:
                    await out("🛡 پنل مالک — از کیبورد «پنل مالک» استفاده کنید.", main_kb(True))
                    return
                if prev == "more":
                    await out(more_menu_text(), ik(more_menu_rows()))
                    return
                if prev == "ally":
                    await out("🤝 اتحادها", ik([[("اتحاد من", "ng:ally")], back_row()]))
                    return
                await out("↩️ بازگشت به بخش قبلی.\nاز منوی همان بخش ادامه دهید.", ik([back_row(), [("🏠 خانه", "ng:home")]]))
                return

            # ---- Alliance System 2.0 callbacks ----
            if data == "ng:acreate":
                if not code:
                    await out("هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                if await game.alliances.member_of(code):
                    await out("شما هم‌اکنون عضو یک اتحاد هستید.", main_kb(owner))
                    return
                _pending[pid] = {"kind": "ally_name"}
                await out(
                    "🏗 ساخت اتحاد\n\nنام اتحاد را بنویسید (حداقل ۳ حرف):",
                    ik([cancel_row()]),
                )
                return
            if data == "ng:acreateyes":
                if not code:
                    await _clear_pending(game, pid)
                    await out("هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                # Double-tap / late callback after success: already in alliance
                try:
                    mem_now = await game.alliances.member_of(code)
                except Exception:
                    mem_now = None
                if mem_now:
                    await _clear_pending(game, pid)
                    a = await game.alliances.get(mem_now["alliance_id"])
                    link = ((a or {}).get("group_invite_link") or "").strip()
                    msg = "✅ اتحاد شما فعال است."
                    if a:
                        msg += chr(10) + "نام: " + str(a.get("name") or "")
                    if link:
                        msg += chr(10) + chr(10) + "لینک گروه:" + chr(10) + link
                    await out(msg, main_kb(owner), force_new=True)
                    return
                st = dict(_pending.get(pid) or {})
                if not st:
                    for k in list(_pending.keys()):
                        try:
                            if int(k) == int(pid):
                                st = dict(_pending.get(k) or {})
                                break
                        except Exception:
                            continue
                name = (st.get("name") or "").strip()
                mm_raw = st.get("max_members")
                tc_raw = st.get("treasury_cap")
                if not name or mm_raw is None or tc_raw is None:
                    rows = [[("➕ ساخت اتحاد", "ng:acreate")], cancel_row()]
                    await out(
                        "❌ اطلاعات ساخت ناقص یا منقضی شده."
                        + chr(10)
                        + "دوباره «➕ ساخت اتحاد» را بزنید.",
                        ik(rows),
                        force_new=True,
                    )
                    return
                if int(pid) in _ALLY_CREATE_LOCK:
                    await out("⏳ ساخت اتحاد در حال انجام است؛ لطفاً صبر کنید…", force_new=True)
                    return
                _ALLY_CREATE_LOCK.add(int(pid))
                try:
                    mm = int(mm_raw or 2)
                    tc = float(tc_raw or 100_000_000)
                    st["kind"] = "ally_confirm"
                    _pending[pid] = dict(st)
                    msg = await game.alliances.create(pid, code, name, mm, tc, bot=bot)
                    await _clear_pending(game, pid)
                    await out(msg, main_kb(owner), force_new=True)
                except (AllianceError, GameError) as e:
                    st["kind"] = "ally_confirm"
                    _pending[pid] = dict(st)
                    rows = [
                        [("✅ تلاش دوباره", "ng:acreateyes")],
                        [("➕ شروع مجدد", "ng:acreate")],
                        cancel_row(),
                    ]
                    await out("❌ ساخت انجام نشد:" + chr(10) + str(e), ik(rows), force_new=True)
                except Exception:
                    log.exception("alliance create")
                    await out(
                        "❌ خطای سیستمی ساخت اتحاد." + chr(10) + "دوباره تلاش کنید.",
                        main_kb(owner),
                        force_new=True,
                    )
                finally:
                    _ALLY_CREATE_LOCK.discard(int(pid))
                return

            if data.startswith("ng:aview:"):
                aid = int(data.split(":")[-1])
                a = await game.alliances.get(aid)
                if not a or a.get("status") != "active":
                    await out("اتحاد یافت نشد")
                    return
                mems = await game.alliances.members(aid)
                labels = {}
                for m in mems:
                    labels[m["country_code"]] = await game.country_label(m["country_code"])
                text_a = game.alliances.card_text(a, mems, labels)
                rows = [[("➕ عضویت در اتحاد", f"ng:ajoin:{aid}")], back_row()]
                await out(text_a, ik(rows))
                return
            if data.startswith("ng:ajoin:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    aid = int(data.split(":")[-1])
                    msg = await game.alliances.join(pid, code, aid)
                    a = await game.alliances.get(aid)
                    link = (a or {}).get("group_invite_link") or ""
                    if link:
                        msg = str(msg) + chr(10) + chr(10) + "⚠️ عضویت در گروه اتحاد اجباری است:" + chr(10) + str(link)
                    await out(msg)
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:aleave":
                rows = [[("✅ تأیید خروج", "ng:aleaveyes"), ("❌ انصراف", "ng:home")]]
                await out("از اتحاد خارج می‌شوید؟", ik(rows))
                return
            if data == "ng:aleaveyes":
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    await out(await game.alliances.leave(pid, code))
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:atreasure:"):
                rows = [
                    [("➕ واریز", "ng:adep"), ("➖ برداشت (بنیان‌گذار)", "ng:awith")],
                    [("💸 تقسیم مساوی", "ng:asplit")],
                    back_row(),
                ]
                await out("🏦 خزانه اتحاد", ik(rows))
                return
            if data == "ng:adep":
                _pending[pid] = {"kind": "ally_deposit"}
                await out("مبلغ واریز را وارد کنید:")
                return
            if data == "ng:awith":
                _pending[pid] = {"kind": "ally_withdraw"}
                await out("مبلغ برداشت را وارد کنید:")
                return
            if data == "ng:asplit":
                try:
                    await out(await game.alliances.equal_split(pid))
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:amembers:"):
                aid = int(data.split(":")[-1])
                mems = await game.alliances.members(aid)
                lines = ["👥 اعضای اتحاد"]
                for m in mems:
                    role = "👑 بنیان‌گذار" if m["role"] == "founder" else "عضو"
                    label = await game.country_label(m["country_code"])
                    lines.append(f"{role}: {label}")
                await out("\n".join(lines))
                return
            if data.startswith("ng:amgmt:"):
                aid = int(data.split(":")[-1])
                rows = [
                    [("✏️ تغییر نام", "ng:arename")],
                    [("⬆️ ظرفیت اعضا", "ng:aemembers"), ("⬆️ ظرفیت خزانه", "ng:aetreasury")],
                    [("🚫 اخراج عضو", f"ng:akicklist:{aid}")],
                    [("🗑 انحلال اتحاد", f"ng:adissolve:{aid}")],
                    back_row(),
                ]
                await out("⚙️ مدیریت اتحاد", ik(rows))
                return
            if data == "ng:arename":
                _pending[pid] = {"kind": "ally_rename"}
                await out(f"نام جدید را بنویسید (هزینه {RENAME_COST:,}):")
                return
            if data == "ng:aemembers":
                _pending[pid] = {"kind": "ally_emembers"}
                await out("ظرفیت جدید اعضا (بزرگ‌تر از فعلی):")
                return
            if data == "ng:aetreasury":
                _pending[pid] = {"kind": "ally_etreasury"}
                await out("ظرفیت جدید خزانه:")
                return
            if data.startswith("ng:akicklist:"):
                aid = int(data.split(":")[-1])
                mems = await game.alliances.members(aid)
                rows = []
                for m in mems:
                    if m["role"] == "founder":
                        continue
                    label = await game.country_label(m["country_code"])
                    rows.append([(f"اخراج {label}", f"ng:akick:{m['country_code']}")])
                rows.append(back_row())
                await out("عضو برای اخراج:", ik(rows) if rows else main_kb(owner))
                return
            if data.startswith("ng:akick:"):
                try:
                    await out(await game.alliances.kick(pid, data.split(":")[-1]))
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:adissolve:"):
                aid = int(data.split(":")[-1])
                rows = [[("✅ تأیید انحلال", f"ng:adissolveyes:{aid}"), ("❌ انصراف", "ng:home")]]
                await out("اتحاد منحل شود؟ خزانه به بنیان‌گذار برمی‌گردد.", ik(rows))
                return
            if data.startswith("ng:adissolveyes:"):
                try:
                    await out(await game.alliances.dissolve(pid, int(data.split(":")[-1]), is_owner=owner))
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:oapool":
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                try:
                    st = await game.alliance_groups.stats()
                except Exception as e:
                    log.exception("oapool")
                    await out(f"❌ {e}", force_new=True)
                    return
                lines = [
                    "🏷 گروه‌های رزرو اتحاد",
                    "━━━━━━━━━━━━━━",
                    f"کل: {st['total']}",
                    f"آزاد: {st['free']}",
                    f"اختصاص‌یافته: {st['assigned']}",
                    f"در حال رزرو: {st.get('holding', 0)}",
                    f"غیرقابل استفاده: {st['unusable']}",
                    "",
                ]
                rows = [[("➕ ثبت گروه رزرو", "ng:oapool:add")], [("🔄 بروزرسانی", "ng:oapool")]]
                for r in (st.get("rows") or [])[:20]:
                    aid = r.get("alliance_id")
                    aname = ""
                    if aid:
                        try:
                            a = await game.alliances.get(int(aid))
                            aname = (a or {}).get("name") or str(aid)
                        except Exception:
                            aname = str(aid)
                    lines.append(
                        f"#{r['id']} | {r.get('status')} | chat={r.get('chat_id')}"
                        + (f" | اتحاد: {aname}" if aname else "")
                    )
                    if r.get("status") == "unusable":
                        rows.append([(f"♻️ آزاد #{r['id']}", f"ng:oapool:free:{r['id']}")])
                    elif r.get("status") == "free":
                        rows.append([(f"🚫 غیرفعال #{r['id']}", f"ng:oapool:bad:{r['id']}")])
                rows.append(back_row())
                await out(chr(10).join(lines), ik(rows), force_new=True)
                return
            if data == "ng:oapool:add":
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                _pending[pid] = {"kind": "oapool_add"}
                await out(
                    "یوزرنیم گروه را با @ بفرستید (پیشنهادی)."
                    + chr(10)
                    + "مثال: @my_alliance_pool"
                    + chr(10)
                    + "یا شناسه عددی گروه"
                    + chr(10)
                    + "اختیاری: @user|نام رزرو"
                    + chr(10) + chr(10)
                    + "خودکار: اگر نام گروه دقیقاً c. باشد و ربات ادمین باشد، خودش به مخزن اضافه می‌شود.",
                    ik([cancel_row()]),
                    force_new=True,
                )
                return
            if data.startswith("ng:oapool:free:"):
                if not owner:
                    return
                try:
                    msg = await game.alliance_groups.set_status(pid, int(data.split(":")[-1]), "free")
                    await out(msg, force_new=True)
                except Exception as e:
                    await out(f"❌ {e}", force_new=True)
                return
            if data.startswith("ng:oapool:bad:"):
                if not owner:
                    return
                try:
                    msg = await game.alliance_groups.set_status(pid, int(data.split(":")[-1]), "unusable")
                    await out(msg, force_new=True)
                except Exception as e:
                    await out(f"❌ {e}", force_new=True)
                return

            if data == "ng:oally":
                allies = await game.alliances.list_active()
                lines = [f"🌐 اتحادهای فعال: {len(allies)}"]
                rows = []
                for a in allies[:30]:
                    mems = await game.alliances.members(a["id"])
                    lines.append(
                        f"#{a['id']} {a['name']} | {len(mems)}/{a['max_members']} | خزانه {int(float(a['treasury'])):,}"
                    )
                    rows.append([
                        (f"جزئیات {a['name']}", f"ng:oallyv:{a['id']}"),
                        (f"منحل #{a['id']}", f"ng:oallyd:{a['id']}"),
                    ])
                rows.append(back_row())
                await out("\n".join(lines), ik(rows))
                return
            if data.startswith("ng:oallyv:"):
                aid = int(data.split(":")[-1])
                a = await game.alliances.get(aid)
                if not a:
                    await out("نیست")
                    return
                mems = await game.alliances.members(aid)
                labels = {m["country_code"]: await game.country_label(m["country_code"]) for m in mems}
                await out(game.alliances.card_text(a, mems, labels))
                return
            if data.startswith("ng:oallyd:"):
                try:
                    await out(await game.alliances.dissolve(pid, int(data.split(":")[-1]), is_owner=True))
                except (AllianceError, GameError) as e:
                    await out(f"❌ {e}")
                return


            if data.startswith("ng:claim:"):
                try:
                    code_c = (data.split(":")[-1] or "").upper()
                    c = await game.claim(pid, code_c)
                    # apply saved referral code (from /start deep-link or pending DB)
                    try:
                        preset = None
                        st_ref = _pending.get(pid) or {}
                        if st_ref.get("kind") == "ref_code" and st_ref.get("preset"):
                            preset = st_ref.get("preset")
                        if not preset:
                            try:
                                prow = await game.db.fetchrow(
                                    "SELECT code FROM ng_pending_referral WHERE player_id=$1",
                                    (pid,),
                                )
                                if prow:
                                    preset = prow.get("code")
                            except Exception:
                                pass
                        if preset:
                            try:
                                ref_msg = await game.apply_referral_code(pid, str(preset))
                                await _clear_pending(game, pid)
                                try:
                                    await game.db.execute(
                                        "DELETE FROM ng_pending_referral WHERE player_id=$1",
                                        (pid,),
                                    )
                                except Exception:
                                    pass
                                await out(ref_msg)
                            except GameError as e_ref:
                                await out(f"🎟 کد دعوت: {e_ref}")
                    except Exception:
                        log.exception("post-claim referral")

                    if False and str((c or {}).get("country_code") or "").upper() == HACKER_CODE:
                        pass
                    else:
                        await out("✅ کشور ثبت شد" + chr(10) + chr(10) + await game.country_card(c["country_code"]))
                except GameError as e:
                    await out(f"❌ {e}")
                except Exception as e:
                    log.exception("claim callback")
                    await out(f"❌ خطا در انتخاب کشور: {e}")
                return

            if data.startswith("ng:go:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                go = data.split(":")[-1]
                if go == "inv":
                    await out(await game.inventory_text(code))
                elif go == "eco":
                    c = await game.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (code,))
                    await out(f"خزانه: {int(float(c['treasury'])):,}\nدرآمد: {int(float(c['daily_income'])):,}")
                elif go == "rep":
                    rows = await game.db.fetch(
                        "SELECT summary FROM ng_activity WHERE country_code=$1 ORDER BY id DESC", (code,)
                    )
                    await out("\n".join(["گزارش"] + [f"• {r['summary'][:100]}" for r in rows[:10]]))
                return

            # shop

            # ── Phase 4 UI routes ─────────────────────────────────
            if data == "ng:v4:more:hub" or data == "ng:v4:more:home":
                nav_push(pid, "more")
                await out(v4ui.more_hub_text(), ik(v4ui.more_hub_rows()))
                return
            if data == "ng:v4:more:mil":
                await out("⚔️ عملیات نظامی", ik(v4ui.mil_menu_rows()))
                return
            if data == "ng:v4:more:diplo":
                await out("🕊 دیپلماسی", ik(v4ui.diplo_menu_rows()))
                return
            if data == "ng:v4:more:oil":
                if not code:
                    await out("هنوز کشوری نداری.")
                    return
                try:
                    txt = await game.oil_panel_text(code)
                except Exception:
                    txt = "🛢 نفت"
                await out(txt, ik([
                    [("🛒 خرید نفت/منابع", "ng:v4:shop:mine")],
                    [("🤝 فروش نفت", "ng:oil:sell")],
                    [("🔙 بازگشت", "ng:v4:more:hub")],
                ]))
                return
            if data == "ng:v4:more:industry":
                await out("🏭 صنعت و تجارت", ik(v4ui.industry_menu_rows()))
                return
            if data == "ng:v4:more:docs":
                await out("📜 قانون و بیانیه", ik(v4ui.docs_menu_rows()))
                return
            if data == "ng:v4:more:info":
                await out("📊 گزارش و اطلاعات", ik(v4ui.info_menu_rows()))
                return
            if data == "ng:v4:more:support":
                await out("💎 حمایت از بازی", ik([
                    [("💎 حمایت مالی", "ng:more:donate")],
                    [("🔙 بازگشت", "ng:v4:more:hub")],
                ]))
                return

            if data.startswith("ng:v4:inv:"):
                if not code:
                    await out("کشور ندارید.")
                    return
                cat = data.split(":")[-1]
                from modules.ng.inventory_service import format_qty_display
                rows_db = await game.db.fetch(
                    "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0 ORDER BY item_code",
                    (code,),
                )
                lines = [f"📦 انبار — {cat}", ""]
                shown = 0
                for r in rows_db:
                    meta = game._cat.get(r["item_code"]) or {}
                    c = meta.get("category") or "other"
                    if cat != "all" and c != cat:
                        continue
                    q = float(r["quantity"] or 0)
                    if q <= 0:
                        continue
                    lines.append(f"• {meta.get('name_fa') or r['item_code']}: {format_qty_display(q)}")
                    shown += 1
                if shown == 0:
                    lines.append("در این دسته چیزی نیست.")
                await out("\n".join(lines), ik([
                    [("⬅️ دسته‌های انبار", "ng:v4:invhub")],
                    back_row(),
                ]))
                return
            if data == "ng:v4:invhub" or data == "ng:go:inv":
                if not code:
                    await out("کشور ندارید.")
                    return
                nav_push(pid, "inv")
                await out(v4ui.inv_hub_text(), ik(v4ui.inv_hub_rows()))
                return

            if data == "ng:v4:shophome" or data == "ng:shophome":
                if not code:
                    await out("کشور ندارید.")
                    return
                nav_push(pid, "shop")
                catmap = getattr(game, "_cat", {}) or {}
                await out(v4ui.shop_hub_text(), ik(v4ui.shop_hub_rows(catmap)))
                return
            if data.startswith("ng:v4:shop:"):
                if not code:
                    await out("کشور ندارید.")
                    return
                cat = data.split(":")[-1]
                catmap = getattr(game, "_cat", {}) or {}
                items = [m for m in catmap.values() if (m.get("category") or "other") == cat]
                try:
                    mult = await game.effective_shop_multiplier(pid, await game.db.fetchrow(
                        "SELECT * FROM ng_countries WHERE country_code=$1", (code,)
                    ) or {})
                except Exception:
                    mult = 1.0
                title = dict(v4ui.INV_CATS).get(cat, cat)
                await out(
                    f"🛒 {title}\nقیمت‌ها ممکن است با ضریب کشور تغییر کند.\nکالا را انتخاب کنید:",
                    ik(v4ui.shop_item_rows(items, cat, mult=mult)),
                )
                return
            if data == "ng:v4:shopback":
                await out(v4ui.shop_hub_text(), ik(v4ui.shop_hub_rows(getattr(game, "_cat", {}) or {})))
                return
            if data.startswith("ng:v4:item:"):
                ic = data.split(":")[-1]
                meta = (getattr(game, "_cat", {}) or {}).get(ic) or {}
                name = meta.get("name_fa") or ic
                price = int(float(meta.get("unit_price") or 0))
                await out(
                    f"🛍️ {name}\nقیمت واحد پایه: {price:,}\nتعداد را انتخاب کنید:",
                    ik(v4ui.shop_qty_rows(ic)),
                )
                return
            if data.startswith("ng:v4:qtyask:"):
                ic = data.split(":")[-1]
                await _set_pending(game, pid, "shop_add_qty", item=ic)
                await out("تعداد موردنظر را به‌صورت عدد بفرستید (۱ تا ۲۵۰):", ik([cancel_row()]))
                return
            if data.startswith("ng:v4:qty:"):
                parts = data.split(":")
                ic, qty_s = parts[3], parts[4]
                qty = int(qty_s)
                meta = (getattr(game, "_cat", {}) or {}).get(ic) or {}
                name = meta.get("name_fa") or ic
                unit = float(meta.get("unit_price") or 0)
                try:
                    mult = await game.effective_shop_multiplier(pid, await game.db.fetchrow(
                        "SELECT * FROM ng_countries WHERE country_code=$1", (code,)
                    ) or {})
                except Exception:
                    mult = 1.0
                total = int(unit * mult * qty)
                await out(
                    f"تأیید خرید\n\n• کالا: {name}\n• تعداد: {qty}\n• مبلغ تقریبی: {total:,}\n\nبا تأیید، به سبد اضافه می‌شود.",
                    ik(v4ui.shop_confirm_rows(ic, qty)),
                )
                return
            if data.startswith("ng:v4:buy:"):
                parts = data.split(":")
                ic, qty_s = parts[3], parts[4]
                qty = int(qty_s)
                try:
                    msg_add = await game.cart_add(pid, ic, qty)
                    await out(msg_add + "\n\nبرای پرداخت نهایی «تسویه» را بزنید.", ik([
                        [("✅ تسویه حساب", "ng:checkout"), ("🛒 سبد", "ng:cart")],
                        [("⬅️ فروشگاه", "ng:v4:shophome")],
                    ]))
                except GameError as e:
                    await out(f"❌ {e}")
                return


            if data.startswith("ng:shop:"):
                cat = data.split(":")[-1]
                try:
                    await game.ensure_shop_catalog()
                except Exception:
                    log.exception("shop catalog seed")
                items = await game.list_catalog_by_category(cat)
                title = CAT_FA.get(cat, cat)
                if not items:
                    await out(f"در دسته «{title}» محصولی نیست. ربات را یک‌بار ری‌استارت کنید.")
                    return
                disc = await game.get_shop_discount_pct()
                rows = []
                for i in items:
                    p = int(float(i.get("price_eff") or i["unit_price"]))
                    tag = f" (−{int(disc)}٪)" if disc else ""
                    rows.append([(f"{i['name_fa']} — {p:,}{tag}", f"ng:item:{i['item_code']}")])
                rows.append([("🛒 سبد", "ng:cart"), ("⬅️ دسته‌ها", "ng:shophome")])
                rows.append(back_row())
                await out(f"🛒 {title}\n{len(items)} محصول:", ik(rows))
                return
            if data == "ng:oil:sell":
                if not code:
                    await out("کشور ندارید.")
                    return
                await _set_pending(game, pid, "oil_sell_target")
                await out(
                    "🛢 فروش نفت به بازیکن\n\nکد کشور خریدار را بفرستید (مثال: US):",
                    ik([cancel_row()]),
                )
                return
            if data == "ng:shophome":
                try:
                    st = await _get_pending(game, pid)
                    if st and st.get("kind") == "shop_add_qty":
                        await _clear_pending(game, pid)
                except Exception:
                    pass
                try:
                    await game.ensure_shop_catalog()
                except Exception:
                    pass
                rows = []
                pair = []
                for cat, name in CAT_FA.items():
                    n = len(items_in_category(cat))
                    pair.append((f"{name} ({n})", f"ng:shop:{cat}"))
                    if len(pair) == 2:
                        rows.append(pair)
                        pair = []
                if pair:
                    rows.append(pair)
                rows.append([("🎁 آیتم‌های لجندری", "ng:legshop")])
                rows.append([("🛒 سبد خرید", "ng:cart"), ("✅ تسویه حساب", "ng:checkout")])
                rows.append(back_row())
                await out("🛒 فروشگاه — دسته را انتخاب کنید:", ik(rows))
                return
            if data.startswith("ng:item:"):
                ic = data.split(":")[-1]
                await game._reload_catalog_prices()
                it = game._cat.get(ic) or {}
                if not it:
                    await out("آیتم یافت نشد")
                    return
                disc = await game.get_shop_discount_pct()
                base = float(it.get("unit_price") or 0)
                eff = base * (1 - disc / 100.0) if disc else base
                price_line = f"قیمت: {int(eff):,}"
                if disc:
                    price_line += f" (پایه {int(base):,} با تخفیف {int(disc)}٪)"
                await _set_pending(game, pid, "shop_add_qty", item=ic)
                rows = [
                    [("＋۱", f"ng:add:{ic}:1"), ("＋۵", f"ng:add:{ic}:5"), ("＋۱۰", f"ng:add:{ic}:10")],
                    [("سبد", "ng:cart"), ("تسویه", "ng:checkout")],
                    back_row(),
                ]
                body = (
                    f"{it.get('name_fa')}"
                    + "\n"
                    + f"{it.get('description_fa')}"
                    + "\n"
                    + price_line
                    + "\n"
                    + f"درآمد روزانه: {int(float(it.get('daily_income') or 0)):,}"
                    + "\n"
                    + f"نگهداری: {int(float(it.get('maintenance') or 0)):,}"
                    + "\n\n"
                    + "اگر می‌خواهی می‌توانی عدد دلخواهت را از ۱ تا ۲۵۰ همین الان وارد کنی "
                    + "تا همان تعداد وارد سبد خریدت شود."
                    + "\n"
                    + "یا از دکمه‌های ＋۱ / ＋۵ / ＋۱۰ استفاده کن."
                )
                await out(body, ik(rows))
                return
            if data.startswith("ng:add:"):
                parts = data.split(":")
                if len(parts) < 4:
                    await out("دکمه نامعتبر است. دوباره کالا را از فروشگاه باز کنید.", force_new=True)
                    return
                ic, q = parts[2], parts[3]
                try:
                    await _set_pending(game, pid, "shop_add_qty", item=ic)
                except Exception:
                    log.exception("set shop pending on add")
                try:
                    add_msg = await game.cart_add(pid, ic, float(q))
                except GameError as e:
                    await out(f"❌ {e}")
                    return
                # stay in shop: show categories + cart summary (edit same message)
                cats = {}
                for it in game._cat.values():
                    cats[it.get("category") or "other"] = cats.get(it.get("category") or "other", 0) + 1
                rows = []
                pair = []
                for cat, n in list(cats.items())[:12]:
                    name = {"ground":"زمینی","air":"هوایی","sea":"دریایی","missile":"موشکی","defense":"پدافند","infra":"زیرساخت","nuclear":"هسته‌ای","mine":"منابع"}.get(cat, cat)
                    pair.append((f"{name} ({n})", f"ng:shop:{cat}"))
                    if len(pair) == 2:
                        rows.append(pair); pair = []
                if pair:
                    rows.append(pair)
                rows.append([("🛒 سبد خرید", "ng:cart"), ("✅ تسویه حساب", "ng:checkout")])
                rows.append(back_row())
                cart_txt = ""
                try:
                    if code:
                        cart_txt, _, items = await game.cart_view(pid, code)
                except Exception:
                    cart_txt = ""
                body = "🛒 فروشگاه\n\n" + str(add_msg) + "\n\n" + (cart_txt or "")
                nav_push(pid, "shop")
                await out(body, ik(rows))
                return
            if data == "ng:cart":
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                text, _, items = await game.cart_view(pid, code)
                rows = [[(f"🗑 {it['name_fa']}", f"ng:cdel:{it['item_code']}")] for it in items]
                rows.append([("✅ تسویه حساب", "ng:checkout")])
                rows.append(back_row())
                await out(text, ik(rows))
                return
            if data.startswith("ng:cdel:"):
                ic = data.split(":")[-1]
                msg_t = await game.cart_set(pid, ic, 0)
                if code:
                    text, _, items = await game.cart_view(pid, code)
                    rows = [[(f"🗑 {it['name_fa']}", f"ng:cdel:{it['item_code']}")] for it in items]
                    rows.append([("✅ تسویه", "ng:checkout")])
                    rows.append(back_row())
                    await out(msg_t + "\n\n" + text, ik(rows))
                else:
                    await out(msg_t)
                return
            if data == "ng:checkout":
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    await out(await game.checkout(pid, code))
                except GameError as e:
                    await out(f"❌ {e}")
                return


            # lucky spin
            if data == "ng:spin" or data == "ng:spin:panel":
                try:
                    txt = await game.lucky_spin_panel(pid)
                except Exception:
                    log.exception("spin panel")
                    txt = "🎰 چرخ شانس"
                await out(txt, ik([
                    [("🎲 چرخاندن چرخ", "ng:spin:go")],
                    back_row(),
                ]))
                return
            if data == "ng:spin:go":
                try:
                    msg = await game.lucky_spin(pid)
                except GameError as e:
                    await out(f"❌ {e}", ik([[("🎰 بازگشت", "ng:spin")], back_row()]), force_new=True)
                    return
                except Exception:
                    log.exception("spin go")
                    await out("❌ خطا در چرخ شانس.", ik([[("🎰 بازگشت", "ng:spin")]]), force_new=True)
                    return
                await out(
                    msg,
                    ik([
                        [("🎲 دوباره بچرخان", "ng:spin:go"), ("🎰 وضعیت", "ng:spin")],
                        back_row(),
                    ]),
                    force_new=True,
                )
                return

            if data == "ng:mnew":
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                inv = await game.db.fetch(
                    "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0 ORDER BY item_code",
                    (code,),
                )
                if not inv:
                    await out("انبار خالی است؛ چیزی برای فروش ندارید.", ik([back_row()]))
                    return
                rows = []
                for r in inv[:40]:
                    meta = game._cat.get(r["item_code"]) or {}
                    name = meta.get("name_fa") or r["item_code"]
                    q = int(float(r["quantity"] or 0))
                    rows.append([(f"{name} ×{q}", f"ng:sell:{r['item_code']}")])
                rows.append(back_row())
                await out("کدام کالا را در بازار آگهی می‌کنید؟", ik(rows))
                return

            # market
            if data.startswith("ng:sell:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                await _set_pending(game, pid, "mkt_qty", item=data.split(":")[-1])
                await out("تعداد برای فروش را بنویسید:", ik([cancel_row()]))
                return
            if data.startswith("ng:mbuy:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    await out(await game.market_buy(int(data.split(":")[-1]), code, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:mmine":
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                rows_db = await game.db.fetch(
                    "SELECT * FROM ng_market WHERE seller_country=$1 AND active=1", (code,)
                )
                lines = ["آگهی‌های من"] + [
                    f"#{r['id']} {r['item_code']} ×{int(float(r['quantity']))}" for r in rows_db
                ]
                btns = [[(f"لغو #{r['id']}", f"ng:mcancel:{r['id']}")] for r in rows_db]
                btns.append(back_row())
                await out("\n".join(lines) if rows_db else "آگهی فعالی ندارید", ik(btns))
                return
            if data.startswith("ng:mcancel:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    await out(await game.market_cancel(int(data.split(":")[-1]), code))
                except GameError as e:
                    await out(f"❌ {e}")
                return


            if data == "ng:diplo:list":
                countries = await game.list_countries()
                lines = ["🌍 وضعیت کشورها و گروهک‌ها", ""]
                owned = [c for c in countries if c.get("owner_player_id")]
                free = [c for c in countries if not c.get("owner_player_id")]
                lines.append(f"🟢 دارای رهبر: {len(owned)}")
                lines.append(f"⚪ آزاد: {len(free)}")
                lines.append("")
                for c in owned[:40]:
                    et = "گروهک" if str(c.get("entity_type") or "") == "group" else "کشور"
                    lines.append(f"{c.get('flag','')} {c.get('name_fa')} — {et} — فعال")
                if len(owned) > 40:
                    lines.append(f"... و {len(owned)-40} مورد دیگر")
                await out(chr(10).join(lines), ik([
                    [("💰 کمک مالی", "ng:trade:money"), ("📦 کمک نظامی", "ng:trade:army")],
                        [("🛢 کمک نفتی", "ng:trade:oil")],
                    back_row(),
                ]))
                return
            if data in ("ng:go:ally", "ng:ally", "ng:ally:mine", "ng:ally:list"):
                if not code:
                    await out("هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                nav_push(pid, "ally")
                mem = await game.alliances.member_of(code)
                if mem and data != "ng:ally:list":
                    a = await game.alliances.get(mem["alliance_id"])
                    if a:
                        try:
                            gate = await game.alliance_groups.membership_gate(pid, a, bot=bot)
                        except Exception:
                            log.exception("ally gate cb")
                            gate = None
                        if gate:
                            await out(gate, main_kb(owner), force_new=True)
                            return
                    mems = await game.alliances.members(mem["alliance_id"])
                    labels = {m["country_code"]: await game.country_label(m["country_code"]) for m in mems}
                    text_a = game.alliances.card_text(a, mems, labels)
                    rows = [
                        [("👥 اعضا", f"ng:amembers:{a['id']}"), ("🏦 خزانه", f"ng:atreasure:{a['id']}")],
                        [("🚪 خروج از اتحاد", "ng:aleave")],
                    ]
                    if mem.get("role") == "founder":
                        rows.insert(1, [("⚙️ مدیریت", f"ng:amgmt:{a['id']}")])
                        rows.insert(2, [("💸 تقسیم مساوی خزانه", "ng:asplit")])
                    rows.append(back_row())
                    await out(text_a, ik(rows))
                    return
                allies = await game.alliances.list_active()
                rows = [[("➕ ساخت اتحاد", "ng:acreate")]]
                for a in allies[:25]:
                    mems = await game.alliances.members(a["id"])
                    rows.append([(f"{a['name']} ({len(mems)}/{a['max_members']})", f"ng:aview:{a['id']}")])
                rows.append(back_row())
                await out("🤝 اتحادها — فهرست فعال یا ساخت اتحاد جدید:", ik(rows))
                return
            if data == "ng:ally:create":
                if not code:
                    await out("هنوز کشوری نداری — از «🗺 انتخاب کشور» شروع کن.", main_kb(owner))
                    return
                if await game.alliances.member_of(code):
                    await out("شما هم‌اکنون عضو یک اتحاد هستید.", main_kb(owner))
                    return
                _pending[pid] = {"kind": "ally_name"}
                await out("🏗 ساخت اتحاد" + chr(10)+chr(10) + "نام اتحاد را بنویسید (حداقل ۳ حرف):", ik([cancel_row()]))
                return

            # trade / aid
            if data == "ng:trade:money":
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                countries = [c for c in await game.list_countries() if c.get("owner_player_id") and c["country_code"] != code]
                rows = [[(f"{c['flag']} {c['name_fa']}", f"ng:aidm:{c['country_code']}")] for c in countries]
                rows.append(back_row())
                await out("مقصد کمک مالی:", ik(rows))
                return
            if data == "ng:trade:oil":
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                countries = [c for c in await game.list_countries() if c.get("owner_player_id") and c["country_code"] != code]
                rows = [[(f"{c['flag']} {c['name_fa']}", f"ng:aido:{c['country_code']}")] for c in countries]
                rows.append(back_row())
                await out("مقصد کمک نفتی (بشکه):", ik(rows))
                return
            if data.startswith("ng:aido:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                await _set_pending(game, pid, "aid_oil_amount", dst=data.split(":")[-1])
                try:
                    from modules.ng.oil_resource import get_stock
                    st = await get_stock(game.db, code)
                except Exception:
                    st = 0
                await out(f"موجودی نفت شما: {int(st):,} بشکه\nتعداد بشکه ارسالی را بنویسید:", ik([cancel_row()]))
                return
            if data == "ng:trade:army":
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                countries = [c for c in await game.list_countries() if c.get("owner_player_id") and c["country_code"] != code]
                rows = [[(f"{c['flag']} {c['name_fa']}", f"ng:aida:{c['country_code']}")] for c in countries]
                rows.append(back_row())
                await out("مقصد کمک نظامی:", ik(rows))
                return
            if data.startswith("ng:aidm:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                _pending[pid] = {"kind": "aid_money_amount", "dst": data.split(":")[-1]}
                await out("مبلغ کمک را بنویسید:")
                return
            if data.startswith("ng:aida:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                dst = data.split(":")[-1]
                inv = await game.db.fetch(
                    "SELECT * FROM ng_inventory WHERE country_code=$1 AND quantity>0", (code,)
                )
                mil = [r for r in inv if game._cat.get(r["item_code"], {}).get("category") in ("ground", "air", "sea", "defense")]
                rows = [[(game._cat.get(r["item_code"], {}).get("name_fa", r["item_code"]), f"ng:aiditem:{dst}:{r['item_code']}")] for r in mil]
                rows.append(back_row())
                await out("تجهیزات برای ارسال:", ik(rows) if mil else main_kb(owner))
                return
            if data.startswith("ng:aiditem:"):
                _, _, dst, item = data.split(":")
                _pending[pid] = {"kind": "aid_army_qty", "dst": dst, "item": item}
                await out("تعداد را بنویسید:")
                return

            # peace removed — redirect to alliances
            if data.startswith("ng:peace"):
                await out("پیمان صلح حذف شده. از منوی 🤝 اتحادها استفاده کنید.")
                return



            if data == "ng:noop":
                await out("این فقط یک عنوان است.")
                return

            
            # ---- legendary items ----
            if data == "ng:wallet_deposit":
                await out(
                    "💳 شارژ کیف پول\n\n"
                    "لطفاً برای شارژ کیف پول خود از طریق آیدی زیر به مالک پیام دهید و درخواست شارژ کنید.\n\n"
                    "آیدی مالک: @commander04",
                    ik([back_row()]),
                )
                return
            if data == "ng:legshop":
                await send_legendary_shop(msg, bot, game, pid, out_text=out)
                return
            if data.startswith("ng:legowned:"):
                await out(
                    "✔️ این آیتم را قبلاً خریداری کرده‌اید و هنوز استفاده باقی دارد."
                    + "\n"
                    + "نیازی به خرید مجدد نیست. پس از اتمام استفاده‌ها دوباره می‌توانید بخرید."
                )
                return
            if data.startswith("ng:legitem:"):
                code_i = data.split(":")[-1]
                d = await game.legendary.get_def(code_i)
                if not d:
                    await out("آیتم یافت نشد")
                    return
                bal = await game.legendary.ensure_wallet(pid)
                owned = await game.legendary.owns_item(pid, code_i)
                if owned:
                    kb = ik([[("✔️ خریداری شده", f"ng:legowned:{code_i}")]])
                else:
                    kb = ik([[("✅ خرید این آیتم", f"ng:legbuy:{code_i}")]])
                cache_key = f"legendary:{code_i}"
                cached_id = await game.legendary.get_media_file_id(cache_key)
                ok, new_fid = await send_photo_with_caption(
                    msg, bot, legendary_image_path(d.get("image_path")),
                    game.legendary.card_text(d, bal), kb, file_id=cached_id,
                )
                if new_fid and new_fid != cached_id:
                    try:
                        await game.legendary.set_media_file_id(cache_key, new_fid)
                    except Exception:
                        log.exception("cache file_id")
                return
            if data.startswith("ng:legbuy:"):
                code_i = (data.split(":")[-1] or "").strip()
                try:
                    if not code_i:
                        await out("❌ کد آیتم نامعتبر", force_new=True)
                        return
                    if await game.legendary.owns_item(pid, code_i):
                        await out(
                            "✔️ این آیتم را قبلاً خریده‌اید و هنوز استفاده باقی دارد."
                            + chr(10)
                            + "تا تمام شدن استفاده‌ها خرید مجدد ممکن نیست.",
                            ik([
                                [("🎁 بازگشت به فروشگاه لجندری", "ng:legshop")],
                                [("🎁 استفاده از آیتم", "ng:leguse")],
                                back_row(),
                            ]),
                            force_new=True,
                        )
                        return
                    result = await game.legendary.buy(pid, code_i)
                    await out(
                        result,
                        ik([
                            [("🎁 بازگشت به فروشگاه لجندری", "ng:legshop")],
                            [("🎁 استفاده از آیتم", "ng:leguse")],
                            back_row(),
                        ]),
                        force_new=True,
                    )
                except Exception as e:
                    log.exception("legbuy %s", code_i)
                    await out(f"❌ {e}", ik([[("🎁 فروشگاه لجندری", "ng:legshop")]]), force_new=True)
                return

            if data == "ng:leguse":
                summary = await game.legendary.inventory_summary(pid)
                if not summary:
                    await out("آیتم لجندری قابل‌استفاده‌ای ندارید.", ik([back_row()]))
                    return
                rows = []
                lines = ["🎁 لیست آیتم‌های لجندری شما:", ""]
                for s in summary:
                    lines.append(f"• {s['name_fa']} | موجودی:{s['stacks']} | استفاده:{s['uses_left']}")
                    rows.append([(f"{s['name_fa']} ({s['uses_left']})", f"ng:legpick:{s['item_code']}")])
                rows.append(back_row())
                await out("\n".join(lines), ik(rows))
                return
            if data.startswith("ng:legpick:"):
                code_i = data.split(":")[-1]
                d = await game.legendary.get_def(code_i)
                if not d:
                    await out("آیتم نامعتبر")
                    return
                mode = d.get("target_mode") or "other"
                if mode == "self":
                    rows = [[("✅ تأیید استفاده روی کشور خودم", f"ng:leggo:{code_i}:SELF")], back_row()]
                    await out(
                        f"{d['name_fa']}\n{d['power_fa']}\n\nروی کشور خودتان اعمال می‌شود. تأیید؟",
                        ik(rows),
                    )
                    return
                countries = [
                    c for c in await game.list_countries()
                    if c.get("owner_player_id") and c["country_code"] != code
                ]
                rows = [[(f"{c.get('flag','')} {c['name_fa']}", f"ng:leggo:{code_i}:{c['country_code']}")] for c in countries]
                rows.append(back_row())
                await out(f"{d['name_fa']}\n{d['power_fa']}\n\nهدف را انتخاب کنید:", ik(rows))
                return
            if data.startswith("ng:leggo:"):
                parts = data.split(":")
                if len(parts) < 4:
                    await out("❌ درخواست نامعتبر است. دوباره از منوی آیتم لجندری شروع کنید.")
                    return
                code_i = parts[2]
                tgt = parts[3]
                if not code:
                    await out("❌ ابتدا باید کشور داشته باشید.")
                    return
                if tgt == "SELF":
                    tgt = code
                if not code_i:
                    await out("❌ آیتم نامعتبر")
                    return
                try:
                    result = await game.legendary.use_item(pid, code_i, tgt)
                    try:
                        summary = await game.legendary.inventory_summary(pid)
                        left_line = ""
                        for s in summary:
                            if s["item_code"] == code_i:
                                left_line = chr(10) + f"📦 باقی‌مانده این آیتم: {s['uses_left']} استفاده"
                                break
                        if not left_line:
                            left_line = chr(10) + "📦 این آیتم دیگر استفاده باقی‌مانده ندارد (تمام شد)."
                        result = result + left_line
                    except Exception:
                        pass
                    await out(
                        result,
                        ik([
                            [("🎁 استفاده دوباره", "ng:leguse")],
                            back_row(),
                        ]),
                    )
                except Exception as e:
                    log.exception("leggo use_item %s -> %s", code_i, tgt)
                    await out(f"❌ {e}")
                return

            # owner legendary mgmt

                try:
                    if data.startswith("ng:llock:") and data.split(":")[-1] in ("0", "1"):
                        en = data.endswith(":1")
                        msg = await game.legendary.set_locked(pid, en)
                    else:
                        on = await game.legendary.is_locked()
                        msg = (
                            "🔒 محدودیت لجندری: روشن" if on else "✅ محدودیت لجندری: خاموش"
                        )
                        msg += chr(10) + (
                            "خرید و استفاده و همه اثرها غیرفعال‌اند."
                            if on else
                            "خرید و استفاده آزاد است."
                        )
                    on = await game.legendary.is_locked()
                    await out(
                        msg + chr(10) + chr(10) + ("وضعیت: 🔒 روشن" if on else "وضعیت: ✅ خاموش"),
                        ik([
                            [("🔒 روشن کردن محدودیت", "ng:llock:1")],
                            [("🔓 خاموش کردن محدودیت", "ng:llock:0")],
                            [("🔄 بررسی وضعیت", "ng:llock")],
                            [("⬅️ پنل مالک", "ng:opanel")],
                        ]),
                        force_new=True,
                    )
                except Exception as e:
                    log.exception("oleglock")
                    await out(f"❌ {e}", force_new=True)
                return
            if data == "ng:oleg" or data.startswith("ng:oleg:"):
                page = 0
                if data.startswith("ng:oleg:"):
                    try:
                        page = int(data.split(":")[-1])
                    except ValueError:
                        page = 0
                players, total = await game.list_players_page(page)
                rows = []
                for p in players:
                    name = p.get("display_name") or p.get("username") or str(p["player_id"])
                    rows.append([(f"{name} ({p['player_id']})", f"ng:olegp:{p['player_id']}")])
                nav = []
                if page > 0:
                    nav.append(("⬅️", f"ng:oleg:{page-1}"))
                if (page + 1) * game.PAGE_SIZE < total:
                    nav.append(("➡️", f"ng:oleg:{page+1}"))
                if nav:
                    rows.append(nav)
                rows.append(back_row())
                await out("🎁 مدیریت آیتم لجندری — بازیکن را انتخاب کنید:", ik(rows))
                return
            if data.startswith("ng:olegp:"):
                tid = int(data.split(":")[-1])
                try:
                    block = await game.legendary.admin_player_legendary_block(tid)
                except Exception as e:
                    block = str(e)
                defs = await game.legendary.list_defs()
                rows = [[(f"➕ {d['name_fa']}", f"ng:oleggive:{tid}:{d['item_code']}")] for d in defs]
                for d in defs:
                    rows.append([(f"➖ حذف {d['name_fa']}", f"ng:olegdel:{tid}:{d['item_code']}")])
                rows.append([("💰 شارژ کیف پول", f"ng:owalletsel:{tid}")])
                rows.append([("👤 پروفایل", f"ng:ou:{tid}")])
                rows.append(back_row())
                await out(f"بازیکن {tid}\n{block}", ik(rows))
                return
            if data.startswith("ng:oleggive:"):
                try:
                    parts = data.split(":")
                    tid = int(parts[2])
                    ic = ":".join(parts[3:]).strip() if len(parts) > 3 else ""
                    if not ic:
                        await out("❌ آیتم نامعتبر", force_new=True)
                        return
                    msg = await game.legendary.admin_give_item(pid, tid, ic, 1)
                    await out(
                        msg,
                        ik([
                            [("➕ دوباره همین آیتم", f"ng:oleggive:{tid}:{ic}")],
                            [("🎁 مدیریت لجندری این بازیکن", f"ng:olegp:{tid}")],
                            [("👤 پروفایل", f"ng:ou:{tid}")],
                        ]),
                        force_new=True,
                    )
                except Exception as e:
                    log.exception("oleggive")
                    await out(f"❌ {e}", force_new=True)
                return
            if data.startswith("ng:olegdel:"):
                try:
                    parts = data.split(":")
                    tid = int(parts[2])
                    ic = ":".join(parts[3:]).strip() if len(parts) > 3 else ""
                    msg = await game.legendary.admin_remove_item(pid, tid, ic, 1)
                    await out(msg, ik([[("🎁 مدیریت لجندری", f"ng:olegp:{tid}")]]), force_new=True)
                except Exception as e:
                    log.exception("olegdel")
                    await out(f"❌ {e}", force_new=True)
                return

            if data == "ng:owallet" or data.startswith("ng:owallet:"):
                page = 0
                if data.startswith("ng:owallet:"):
                    try:
                        page = int(data.split(":")[-1])
                    except ValueError:
                        page = 0
                page = max(0, page)
                players, total = await game.list_players_page(page)
                page_size = getattr(game, "PAGE_SIZE", 8) or 8
                pages = max(1, (total + page_size - 1) // page_size)
                if page >= pages and total > 0:
                    page = pages - 1
                    players, total = await game.list_players_page(page)
                rows = []
                for p in players:
                    name = p.get("display_name") or p.get("username") or "بدون‌نام"
                    cc = p.get("country_code") or "—"
                    pid_s = p.get("player_id")
                    rows.append([(f"{name} | {cc} | {pid_s}", f"ng:owalletsel:{pid_s}")])
                nav = []
                if page > 0:
                    nav.append(("⬅️ قبلی", f"ng:owallet:{page-1}"))
                if (page + 1) * page_size < total:
                    nav.append(("بعدی ➡️", f"ng:owallet:{page+1}"))
                if nav:
                    rows.append(nav)
                rows.append(back_row())
                await out(
                    "💰 شارژ کیف پول" + "\n"
                    + f"صفحه {page+1}/{pages} — کل بازیکن: {total}" + "\n"
                    + "بازیکن را انتخاب کنید:",
                    ik(rows),
                )
                return
            if data.startswith("ng:owalletsel:"):
                tid = int(data.split(":")[-1])
                if not game.is_owner(pid):
                    await out("❌ فقط مالک")
                    return
                bal = await game.legendary.ensure_wallet(tid)
                p = await game.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (tid,))
                name = (p or {}).get("display_name") or (p or {}).get("username") or str(tid)
                cc = (p or {}).get("country_code") or "—"
                _pending[pid] = {"kind": "owner_wallet_charge", "target": tid}
                await out(
                    "💰 شارژ کیف پول" + "\n"
                    + f"بازیکن: {name}" + "\n"
                    + f"شناسه: {tid}" + "\n"
                    + f"کشور: {cc}" + "\n"
                    + f"موجودی فعلی: {int(bal):,} تومان" + "\n\n"
                    + "مبلغ شارژ را به عدد بفرستید." + "\n"
                    + "مثال: 2000",
                    ik([cancel_row()]),
                )
                return
            if data == "ng:olegprices":
                defs = await game.legendary.list_defs()
                rows = []
                for d in defs:
                    uses = int(d.get("uses_per_unit") or 1)
                    rows.append([(
                        f"{d['name_fa']} | {int(float(d['price'])):,}ت | {uses}بار",
                        f"ng:olegcfg:{d['item_code']}",
                    )])
                rows.append(back_row())
                await out(
                    "⚙️ تنظیم فروشگاه لجندری" + "\n"
                    + "آیتم را انتخاب کنید (قیمت / تعداد استفاده):",
                    ik(rows),
                )
                return
            if data.startswith("ng:olegcfg:"):
                ic = data.split(":")[-1]
                d = await game.legendary.get_def(ic)
                if not d:
                    await out("آیتم یافت نشد")
                    return
                uses = int(d.get("uses_per_unit") or 1)
                await out(
                    f"🎁 {d['name_fa']}" + "\n"
                    + f"قیمت فعلی: {int(float(d['price'])):,} تومان" + "\n"
                    + f"استفاده فعلی هر خرید: {uses} بار" + "\n\n"
                    + "کدام را تغییر می‌دهید؟",
                    ik([
                        [("💰 تغییر قیمت", f"ng:olegprice:{ic}")],
                        [("🔢 تغییر تعداد استفاده", f"ng:oleguses:{ic}")],
                        back_row(),
                    ]),
                )
                return
            if data.startswith("ng:olegprice:"):
                ic = data.split(":")[-1]
                d = await game.legendary.get_def(ic)
                if not d:
                    await out("آیتم یافت نشد")
                    return
                _pending[pid] = {"kind": "owner_leg_price", "item": ic}
                await out(
                    f"قیمت فعلی {d['name_fa']}: {int(float(d['price'])):,} تومان" + "\n"
                    + "قیمت جدید را بنویسید:",
                    ik([cancel_row()]),
                )
                return
            if data.startswith("ng:oleguses:"):
                ic = data.split(":")[-1]
                d = await game.legendary.get_def(ic)
                if not d:
                    await out("آیتم یافت نشد")
                    return
                uses = int(d.get("uses_per_unit") or 1)
                _pending[pid] = {"kind": "owner_leg_uses", "item": ic}
                await out(
                    f"تعداد استفاده فعلی {d['name_fa']}: {uses} بار" + "\n"
                    + "عدد جدید را بنویسید (۱ تا ۱۰۰۰)." + "\n"
                    + "مثال: 20",
                    ik([cancel_row()]),
                )
                return

            # cyber / defense status
            if data == "ng:cyber" or data.startswith("ng:cyber:"):
                if not code:
                    await out("ابتدا کشور/گروهک انتخاب کنید.")
                    return
                if data == "ng:cyber":
                    rows = [
                        [("🛡 هکر پدافند", "ng:cyber:hackdef")],
                        [("💰 هکر دارایی", "ng:cyber:hackasset")],
                        [("📊 وضعیت پدافند من", "ng:mydef")],
                        back_row(),
                    ]
                    await out(
                        chr(10).join([
                            "💻 هک و امنیت",
                            "هکر پدافند: اختلال موقت ۳۰٪ پدافند هدف (۲ دقیقه)",
                            "هکر دارایی: گزارش دارایی‌های هدف (بدون تغییر)",
                        ]),
                        ik(rows),
                    )
                    return
                action = data.split(":")[-1]
                countries, _tot = await game.list_attack_targets(code, page=0, page_size=40)
                if not countries:
                    await out("هیچ کشور دارای رهبری برای هدف‌گیری نیست.", ik([back_row()]))
                    return
                if action == "hackdef":
                    rows = [[(f"{c.get('flag','')} {c['name_fa']}", f"ng:chdef:{c['country_code']}")] for c in countries]
                    rows.append(back_row())
                    await out("هدف هکر پدافند را انتخاب کنید:", ik(rows))
                    return
                if action == "hackasset":
                    rows = [[(f"{c.get('flag','')} {c['name_fa']}", f"ng:chasset:{c['country_code']}")] for c in countries]
                    rows.append(back_row())
                    await out("هدف هکر دارایی را انتخاب کنید:", ik(rows))
                    return
                return
            if data.startswith("ng:chdef:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                dst = data.split(":")[-1]
                try:
                    await out(await game.hack_defense(code, dst, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:chasset:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                dst = data.split(":")[-1]
                try:
                    await out(await game.hack_assets(code, dst, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:mydef":
                if not code:
                    await out("ابتدا کشور/گروهک انتخاب کنید.")
                    return
                try:
                    await out(await game.cyber_status_text(code), ik([
                        [("💻 هک و امنیت", "ng:cyber")],
                        back_row(),
                    ]))
                except Exception as e:
                    log.exception("mydef")
                    await out(f"❌ {e}")
                return

            # attack

            # ---- donations ----
            # ---- donations (multi-step) ----
            if data in ("ng:donate", "ng:donate:start"):
                try:
                    body = await game.donations.intro_text()
                except Exception:
                    body = "💎 حمایت مالی\n\nآیا واقعاً از حمایت کردن مطمئنی؟\nاز دادن درخواست الکی خودداری کنید."
                await out(
                    body,
                    ik([
                        [("✅ بله", "ng:donate:yes"), ("❌ خیر", "ng:donate:no")],
                        back_row(),
                    ]),
                )
                return
            if data == "ng:donate:no":
                await _clear_pending(game, pid)
                await out("لغو شد. حمایت کاملاً اختیاری است.", main_kb(owner))
                return
            if data == "ng:donate:yes":
                try:
                    await game.donations.assert_can_request(pid)
                except Exception as e:
                    await out(f"❌ {e}")
                    return
                await out(
                    "روش خود را انتخاب کنید:",
                    ik([
                        [("🎁 پاکت هدیه", "ng:donate:method:gift")],
                        [("💳 کارت‌به‌کارت", "ng:donate:method:card")],
                        [("❌ انصراف", "ng:donate:no")],
                    ]),
                )
                return
            if data.startswith("ng:donate:method:"):
                method = data.split(":")[-1]
                if method not in ("gift", "card"):
                    await out("روش نامعتبر")
                    return
                try:
                    await game.donations.assert_can_request(pid)
                except Exception as e:
                    await out(f"❌ {e}")
                    return
                _pending[pid] = {"kind": "donation_wait_pay", "method": method}
                if method == "gift":
                    body = (
                        "🎁 پاکت هدیه\n\n"
                        "لطفاً به پیوی مالک بروید و مبلغ درخواست را واریز کنید،\n"
                        "سپس روی دکمه «می‌خواهم واریز کنم» بزنید."
                    )
                else:
                    cfg = await game.donations.config()
                    body = (
                        "💳 کارت‌به‌کارت\n\n"
                        "لطفاً مبلغ دلخواه را به شماره کارت زیر واریز کنید و سپس روی «می‌خواهم واریز کنم» بزنید.\n\n"
                        f"شماره کارت: `{cfg.get('card') or '—'}`\n"
                        f"به‌نام: {cfg.get('card_name') or '—'}"
                    )
                await out(
                    body,
                    ik([
                        [("✅ می‌خواهم واریز کنم", "ng:donate:paid")],
                        [("❌ انصراف", "ng:donate:no")],
                    ]),
                )
                return
            if data == "ng:donate:paid":
                st = _pending.get(pid) or {}
                method = st.get("method") or "card"
                try:
                    await game.donations.assert_can_request(pid)
                except Exception as e:
                    await out(f"❌ {e}")
                    return
                _pending[pid] = {"kind": "donation_amount", "method": method}
                await out(
                    "مبلغ واریزی را به تومان بنویس (فقط عدد).\nمثال: 50000",
                    ik([cancel_row()]),
                )
                return
            if data.startswith("ng:donate:showname:"):
                show = data.split(":")[-1] == "1"
                st = _pending.get(pid) or {}
                if st.get("kind") not in ("donation_show_name", "donation_amount") or not st.get("amount"):
                    await out("نشست منقضی شده. دوباره از حمایت مالی شروع کن.", main_kb(owner))
                    await _clear_pending(game, pid)
                    return
                amount = float(st["amount"])
                method = st.get("method") or "card"
                try:
                    from modules.ng.donations import DonationError as _DE
                    # author from cq
                    author = getattr(cq, "from_user", None) or getattr(cq, "author", None)
                    uname = getattr(author, "username", None) if author else None
                    dname = None
                    if author:
                        dname = getattr(author, "first_name", None) or getattr(author, "name", None)
                    drow = await game.donations.submit(
                        pid,
                        amount,
                        username=str(uname or ""),
                        display_name=str(dname or uname or pid),
                        show_name=show,
                        method=method,
                    )
                    await _clear_pending(game, pid)
                    await out(
                        f"✅ درخواست حمایت ثبت شد.\nشناسه: #{drow['id']}\nمبلغ: {int(amount):,} تومان\n"
                        "پس از بررسی مالک نتیجه اعلام می‌شود.",
                        main_kb(owner),
                    )
                    try:
                        body = game.donations.owner_review_text(drow)
                        kb = ik([
                            [("✅ تأیید", f"ng:donrev:ok:{drow['id']}"), ("❌ رد", f"ng:donrev:no:{drow['id']}")],
                        ])
                        owner_ids = set()
                        try:
                            if game.owner_id:
                                owner_ids.add(int(game.owner_id))
                        except Exception:
                            pass
                        try:
                            for oid in getattr(game, "_extra_owner_ids", set()) or set():
                                owner_ids.add(int(oid))
                        except Exception:
                            pass
                        for oid in owner_ids:
                            try:
                                await bot.send_message(int(oid), body, components=kb)
                            except Exception:
                                log.exception("notify owner %s donation", oid)
                    except Exception:
                        log.exception("notify owner donation")
                except Exception as e:
                    await out(f"❌ {e}")
                return

            if data == "ng:odonate":
                if not owner:
                    await out("❌ فقط مالک")
                    return
                st = await game.donations.stats()
                cfg = await game.donations.config()
                text = (
                    "💎 مدیریت حمایت مالی\n\n"
                    f"مجموع تأییدشده: {int(st['total_approved']):,}\n"
                    f"تعداد تأیید: {st['count_approved']}\n"
                    f"در انتظار: {st['count_pending']}\n"
                    f"ردشده: {st['count_rejected']}\n\n"
                    f"کارت: {cfg['card']}\n"
                    f"صاحب کارت: {cfg['card_name']}"
                )
                await out(text, ik([
                    [("⏳ در انتظار", "ng:odonate:pending"), ("✅ تأییدشده", "ng:odonate:approved")],
                    [("❌ ردشده", "ng:odonate:rejected")],
                    [("💳 شماره کارت", "ng:odonate:card"), ("👤 نام صاحب کارت", "ng:odonate:card_name")],
                    [("📝 متن معرفی", "ng:odonate:intro"), ("📄 توضیحات", "ng:odonate:instructions")],
                    [("💰 تنظیم مجموع آمار", "ng:odonate:total")],
                    back_row(),
                ]))
                return
            if data.startswith("ng:odonate:"):
                if not owner:
                    await out("❌ فقط مالک")
                    return
                sub = data.split(":", 2)[-1]
                if sub in ("pending", "approved", "rejected"):
                    rows = await game.donations.list_by_status(sub, 20)
                    if not rows:
                        await out("موردی نیست.", ik([[("🔙 بازگشت", "ng:odonate")]]))
                        return
                    lines = [f"فهرست ({sub}):"]
                    kb_rows = []
                    for r in rows:
                        lines.append(
                            f"#{r['id']} | {int(float(r['amount'])):,} | {r.get('display_name') or r.get('username') or r['player_id']}"
                        )
                        if sub == "pending":
                            kb_rows.append([
                                (f"✅ #{r['id']}", f"ng:donrev:ok:{r['id']}"),
                                (f"❌ #{r['id']}", f"ng:donrev:no:{r['id']}"),
                            ])
                    kb_rows.append([("🔙 بازگشت", "ng:odonate")])
                    await out("\n".join(lines), ik(kb_rows))
                    return
                if sub in ("card", "card_name", "intro", "instructions"):
                    _pending[pid] = {"kind": f"donation_set_{sub}"}
                    await out("مقدار جدید را بفرستید:", ik([cancel_row()]))
                    return
                if sub == "total":
                    _pending[pid] = {"kind": "donation_set_total"}
                    await out("مبلغ کل حمایت‌های نمایشی را به عدد بنویسید:", ik([cancel_row()]))
                    return
                return

            # Owner review of financial support requests
            if data.startswith("ng:donrev:"):
                if not owner:
                    await out("❌ فقط مالک می‌تواند درخواست حمایت را بررسی کند.", force_new=True)
                    return
                parts = str(data).split(":")
                if len(parts) < 4:
                    await out("❌ داده بررسی حمایت نامعتبر است.", force_new=True)
                    return
                action = parts[2]
                try:
                    did = int(parts[3])
                except Exception:
                    await out("❌ شناسه درخواست نامعتبر است.", force_new=True)
                    return
                approve = action in ("ok", "yes", "1", "approve")
                if action not in ("ok", "yes", "1", "approve", "no", "0", "reject"):
                    await out("❌ عملیات نامعتبر.", force_new=True)
                    return
                try:
                    from modules.ng.donations import DonationError as _DE
                    drow = await game.donations.review(did, pid, approve=approve)
                    amount_i = int(float(drow.get("amount") or 0))
                    if approve:
                        await out(
                            f"✅ حمایت #{did} تأیید شد." + chr(10) + f"مبلغ: {amount_i:,} تومان",
                            ik([[("💎 مدیریت حمایت", "ng:odonate")], [("🏠 خانه", "ng:home")]]),
                            force_new=True,
                        )
                        try:
                            target = int(drow.get("player_id") or 0)
                            if target:
                                await bot.send_message(
                                    target,
                                    f"✅ درخواست حمایت #{did} تأیید شد." + chr(10)
                                    + f"مبلغ: {amount_i:,} تومان" + chr(10)
                                    + "از حمایت شما سپاسگزاریم 🙏",
                                )
                        except Exception:
                            log.exception("notify donor approved")
                        try:
                            text = game.donations.announcement_text(drow)
                            await game.broadcast_log("donation", text)
                        except Exception:
                            log.exception("broadcast donation")
                        try:
                            text = game.donations.announcement_text(drow)
                            gid = getattr(game, "group_id", None)
                            if gid and hasattr(bot, "send_message"):
                                await bot.send_message(gid, text)
                        except Exception:
                            log.exception("group donation announce")
                    else:
                        await out(
                            f"❌ حمایت #{did} رد شد.",
                            ik([[("💎 مدیریت حمایت", "ng:odonate")], [("🏠 خانه", "ng:home")]]),
                            force_new=True,
                        )
                        try:
                            target = int(drow.get("player_id") or 0)
                            if target:
                                await bot.send_message(
                                    target,
                                    f"❌ درخواست حمایت #{did} رد شد." + chr(10)
                                    + "در صورت نیاز با مالک هماهنگ کنید.",
                                )
                        except Exception:
                            log.exception("notify donor rejected")
                except _DE as e:
                    await out(f"❌ {e}", force_new=True)
                except Exception as e:
                    log.exception("donrev")
                    await out(f"❌ خطا در بررسی حمایت: {e}", force_new=True)
                return

            if data == "ng:atkmenu" or data.startswith("ng:atk:") or data.startswith("ng:fight:") or (data.startswith("ng:nuke") and not data.startswith("ng:nukego:")):
                is_un = owner and (code or "").upper() in ("UN", "UN2", "UN3")
                is_hack = False
                meta = await game.db.fetchrow("SELECT war_enabled, nuclear_enabled FROM world_meta WHERE id=1")
                if not is_un and not is_hack and (not meta or not int(meta.get("war_enabled") or 0)):
                    await out(
                        "⚠️ امکان انجام حمله وجود ندارد.\n\nدر حال حاضر وضعیت جنگ در جهان بسته است.\nسازمان ملل باید جنگ را فعال کند.",
                        force_new=True,
                    )
                    return
            
            if data == "ng:atkmenu" or data.startswith("ng:atkmenu:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                page = 0
                if data.startswith("ng:atkmenu:"):
                    try:
                        page = int(data.split(":")[-1])
                    except ValueError:
                        page = 0
                countries, total = await game.list_attack_targets(code, page=page, page_size=25)
                pages = max(1, (total + 24) // 25)
                rows = []
                for c in countries:
                    rows.append([(
                        f"{c.get('flag','')} {c['name_fa']}",
                        f"ng:atk:{c['country_code']}",
                    )])
                nav = []
                if page > 0:
                    nav.append(("⬅️ قبلی", f"ng:atkmenu:{page-1}"))
                if (page + 1) * 25 < total:
                    nav.append(("بعدی ➡️", f"ng:atkmenu:{page+1}"))
                if nav:
                    rows.append(nav)
                rows.append(back_row())
                await out(
                    "هدف حمله را انتخاب کنید:" + "\n"
                    + f"تعداد اهداف زنده: {total} — صفحه {page+1}/{pages}",
                    ik(rows) if rows else main_kb(owner),
                )
                return
            if data.startswith("ng:atk:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                ok, reason = await game.can_attack(code)
                if not ok:
                    await out(f"❌ {reason}")
                    return
                dst = data.split(":")[-1]
                rows = []
                for kind, label in (("ground", "زمینی"), ("air", "هوایی"), ("sea", "دریایی")):
                    pwr, _ = await game.available_force(code, kind)
                    if pwr > 0:
                        rows.append([(f"{label} ۳۰٪", f"ng:fight:{dst}:{kind}:30"), (f"{label} ۵۰٪", f"ng:fight:{dst}:{kind}:50")])
                        rows.append([(f"{label} ۱۰۰٪", f"ng:fight:{dst}:{kind}:100")])
                # atomic option if has bomb
                try:
                    bomb_n = await game.count_atom_bombs(code)
                except Exception:
                    bomb_n = 0.0
                if bomb_n >= 1 or ((code or "").upper() == "UN" and owner):
                    rows.append([("☢️ حمله با بمب اتم", f"ng:nuke:{dst}")])
                if not rows:
                    await out("❌ هیچ نیروی قابل‌استفاده‌ای برای انواع حمله ندارید.")
                    return
                rows.append(back_row())
                dst_name = await game.country_label(dst)
                await out(f"عملیات علیه {dst_name} — فقط انواع دارای نیرو:", ik(rows))
                return
            if data.startswith("ng:fight:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.", force_new=True)
                    return
                try:
                    parts = data.split(":")
                    dst, kind, pct = parts[2], parts[3], parts[4]
                except Exception:
                    await out("❌ داده حمله نامعتبر", force_new=True)
                    return
                try:
                    msg = await game.attack(code, dst, kind, float(pct), pid)
                    if not msg:
                        msg = "✅ حمله انجام شد. جزئیات در گزارش گروه ارسال شد."
                    await out(msg, ik([[("⚔️ منوی حمله", "ng:atkmenu")], [("🏠 خانه", "ng:home")]]), force_new=True)
                except GameError as e:
                    await out(f"❌ {e}", force_new=True)
                except Exception as e:
                    log.exception("fight")
                    err = str(e)
                    if "transaction is aborted" in err.lower() or "infailedsqltransaction" in err.lower():
                        await out(
                            "❌ خطای موقت دیتابیس در حمله. دوباره تلاش کنید.\n"
                            "اگر حمله در گروه اعلام شده، احتمالاً اعمال شده است.",
                            force_new=True,
                        )
                    else:
                        await out(f"❌ خطا در حمله: {e}", force_new=True)
                return
            if data.startswith("ng:nuke:") and not data.startswith("ng:nukego:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.", force_new=True)
                    return
                dst = data.split(":")[-1]
                rows = [
                    [("✅ تأیید حمله اتمی", f"ng:nukego:{dst}")],
                    [("❌ انصراف", "ng:atkmenu")],
                ]
                await out(
                    f"⚠️ حمله اتمی به {dst}\n"
                    "یک بمب اتم از انبار مصرف می‌شود.\n"
                    "۲۵ تا ۳۵ درصد سلامت کشور هدف به‌صورت تصادفی کاهش می‌یابد.\n"
                    "ادامه؟",
                    ik(rows),
                    force_new=True,
                )
                return
            if data.startswith("ng:nukego:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.", force_new=True)
                    return
                dst = data.split(":")[-1]
                try:
                    msg = await game.attack_nuclear(code, dst, pid)
                    if not msg:
                        msg = "✅ حمله اتمی انجام شد. جزئیات در گزارش گروه ارسال شد."
                    await out(msg, ik([[("⚔️ منوی حمله", "ng:atkmenu")], [("🏠 خانه", "ng:home")]]), force_new=True)
                except GameError as e:
                    await out(f"❌ {e}", force_new=True)
                except Exception as e:
                    log.exception("nukego")
                    err = str(e)
                    if "transaction is aborted" in err.lower() or "infailedsqltransaction" in err.lower():
                        await out(
                            "❌ خطای موقت دیتابیس در حمله اتمی. دوباره تلاش کنید.\n"
                            "اگر حمله در گروه اعلام شده، احتمالاً اعمال شده است.",
                            force_new=True,
                        )
                    else:
                        await out(f"❌ خطا در حمله اتمی: {e}", force_new=True)
                return

            # owner panel

            if data.startswith("ng:o:hub:"):
                if not owner:
                    await out("❌ دسترسی مجاز نیست.")
                    return
                hubk = data.split(":")[-1]
                if hubk == "players":
                    await out(
                        "👤 مدیریت بازیکنان\nیک گزینه را انتخاب کنید:",
                        ik([
                            [("🛡 Sethp — همه ۱۰۰۰/۱۰۰۰", "ng:ohpfull")],
                            [("📋 لیست/جستجو", "ng:o:players")],
                            [("🚫 بن کاربر", "ng:oban"), ("✅ آن‌بن", "ng:ounban")],
                            [("🔍 جستجوی کد بن", "ng:obansearch")],
                            [("🧪 حساب تستی", "ng:otest")],
                            back_row(),
                        ]),
                    )
                elif hubk == "countries":
                    await out("🗺 کشورها", ik([
                        [("وضعیت جهان", "ng:o:world"), ("❤️ دیدن HP", "ng:ohp")],
                        [("🏅 رنکینگ", "ng:orank"), ("⚖️ محکوم کردن", "ng:ocondemn")],
                        back_row(),
                    ]))
                elif hubk == "economy":
                    await out("💰 اقتصاد", ik([
                        [("💰 پرداخت درآمد روزانه", "ng:odaily"), ("💵 پول همگانی", "ng:ogiveall")],
                        [("تغییر پول کشور", "ng:omoney"), ("💰 مالیات", "ng:otax")],
                        [("🔒 قطع خرید", "ng:oshop:1"), ("🔓 آزاد خرید", "ng:oshop:0")],
                        back_row(),
                    ]))
                elif hubk == "inventory":
                    await out("📦 تجهیزات", ik([
                        [("❤️ جون همگانی", "ng:ohpall"), ("🛒 فروشگاه", "ng:shophome")],
                        back_row(),
                    ]))
                elif hubk == "diplo":
                    await out("🕊 دیپلماسی", ik([
                        [("🌐 مدیریت اتحادها", "ng:oally"), ("🏷 گروه‌های رزرو", "ng:oapool")],
                        [("بیانیه‌ها", "ng:ostmt"), ("NPT", "ng:onpt")],
                        [("📜 قوانین", "ng:olaws")],
                        back_row(),
                    ]))
                elif hubk == "wars":
                    await out("⚔️ جنگ", ik([
                        [("جنگ باز", "ng:owar:1"), ("جنگ بسته", "ng:owar:0")],
                        [("هسته‌ای فعال", "ng:onuke:1"), ("هسته‌ای خاموش", "ng:onuke:0")],
                        [("کول‌داون ۳۰ث", "ng:ocd:30"), ("۲د", "ng:ocd:120"), ("۵د", "ng:ocd:300")],
                        back_row(),
                    ]))
                elif hubk == "settings":
                    await out("⚙️ تنظیمات", ik([
                        [("📝 /start", "ng:ostart"), ("ℹ️ درباره", "ng:oabout")],
                        [("عضویت اجباری", "ng:oforce"), ("لاگ‌ها", "ng:ologs")],
                        back_row(),
                    ]))
                elif hubk == "logs":
                    await out("📋 گزارش‌ها", ik([
                        [("وضعیت جهان", "ng:o:world"), ("آمار دعوت", "ng:orefstats")],
                        back_row(),
                    ]))
                else:
                    await out("بخش نامعتبر.")
                return


            # workshop
            if data.startswith("ng:ws:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    if data == "ng:ws:status":
                        await out(await game.workshop_status(code), ik([
                            [("⚛ اورانیوم", "ng:ws:uranium"), ("🔬 تحقیق", "ng:ws:research")],
                            [("⬆️ ارتقا", "ng:ws:upgrade")], back_row()
                        ]))
                    elif data == "ng:ws:uranium":
                        await out(await game.start_uranium_job(code, pid))
                    elif data == "ng:ws:research":
                        await out(await game.start_research_job(code, pid))
                    elif data == "ng:ws:upgrade":
                        await out(await game.workshop_upgrade(code, pid))
                    elif data == "ng:ws:bomb":
                        await out(await game.craft_atom_bomb(code, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data.startswith("ng:npt:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                if await game.is_group(code):
                    await out("گروهک‌ها امکان NPT ندارند.")
                    return
                action = data.split(":")[-1]
                rows = [[("✅ تأیید درخواست", f"ng:nptgo:{action}"), ("❌ انصراف", "ng:home")]]
                label = "عضویت در NPT" if action == "join" else "خروج از NPT"
                await out(f"آیا از ارسال درخواست «{label}» مطمئن هستید؟\nپس از ارسال، مالک باید تأیید کند.", ik(rows))
                return
            if data.startswith("ng:nptgo:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    await out(await game.request_npt_change(code, pid, data.split(":")[-1]))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data == "ng:onpt":
                rows_db = await game.pending_npt_list()
                btns = []
                lines = ["درخواست‌های NPT"]
                for r in rows_db[:15]:
                    label = "عضویت" if r["request_type"] == "join" else "خروج"
                    cn = await game.country_name_only(r["country_code"])
                    lines.append(f"#{r['id']} {cn} — {label} — بازیکن {r['player_id']}")
                    btns.append([
                        (f"✅#{r['id']}", f"ng:nptok:{r['id']}"),
                        (f"❌#{r['id']}", f"ng:nptno:{r['id']}"),
                    ])
                btns.append(back_row())
                await out("\n".join(lines) if rows_db else "درخواست معلقی نیست", ik(btns))
                return
            if data.startswith("ng:nptok:"):
                try:
                    await out(await game.review_npt(int(data.split(":")[-1]), True, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:nptno:"):
                try:
                    await out(await game.review_npt(int(data.split(":")[-1]), False, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data == "ng:ostart":
                cur = await game.get_setting("start_message", game.DEFAULT_START)
                rows = [
                    [("✏️ ویرایش", "ng:ostart:edit"), ("↩️ پیش‌فرض", "ng:ostart:reset")],
                    back_row(),
                ]
                await out("📝 پیام /start فعلی:\n\n" + cur[:1500], ik(rows))
                return
            if data == "ng:ostart:edit":
                _pending[pid] = {"kind": "edit_start"}
                await out("متن جدید خوشامدگویی را ارسال کنید:")
                return
            if data == "ng:ostart:reset":
                try:
                    await out(await game.reset_setting(pid, "start_message"))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:oabout":
                cur = await game.get_setting("about_message", game.DEFAULT_ABOUT)
                rows = [
                    [("✏️ ویرایش", "ng:oabout:edit"), ("↩️ پیش‌فرض", "ng:oabout:reset")],
                    back_row(),
                ]
                await out("ℹ️ متن درباره ما:\n\n" + cur[:1500], ik(rows))
                return
            if data == "ng:oabout:edit":
                _pending[pid] = {"kind": "edit_about"}
                await out("متن جدید درباره ما را ارسال کنید:")
                return
            if data == "ng:oabout:reset":
                try:
                    await out(await game.reset_setting(pid, "about_message"))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data == "ng:oally":
                rows_db = await game.list_alliances()
                text = await game.alliances_summary_text()
                rows = []
                for p in rows_db[:20]:
                    a = await game.country_name_only(p["country_a"])
                    b = await game.country_name_only(p["country_b"])
                    rows.append([(f"#{p['id']} {a}↔{b}", f"ng:oally:{p['id']}")])
                rows.append(back_row())
                await out(text, ik(rows))
                return
            if data.startswith("ng:oally:"):
                try:
                    await out(await game.alliance_detail_text(int(data.split(":")[-1])))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:oaway":
                cur = await game.get_owner_away()
                rows = [
                    [("🔕 فعال کردن", "ng:oaway:1"), ("🔔 خاموش کردن", "ng:oaway:0")],
                    back_row(),
                ]
                st = "فعال" if cur else "غیرفعال"
                await out(f"وضعیت «در دسترس نیستم»: {st}", ik(rows))
                return
            if data.startswith("ng:oaway:"):
                en = data.endswith(":1")
                try:
                    await out(await game.set_owner_away(pid, en))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ohardcore:status":
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                on = await game.is_hardcore_mode()
                await out(
                    ("☠️ هاردکور روشن است." if on else "✅ هاردکور خاموش است.")
                    + chr(10)
                    + ("نابودشده‌ها نمی‌توانند کشور بگیرند تا خاموش شود." if on else "انتخاب کشور آزاد است."),
                    ik([
                        [("☠️ روشن کردن", "ng:ohardcore:1")],
                        [("🕊 خاموش کردن", "ng:ohardcore:0")],
                        [("⬅️ پنل مالک", "ng:opanel")],
                    ]),
                    force_new=True,
                )
                return
            if data == "ng:ohardcore" or data.startswith("ng:ohardcore:"):
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                try:
                    if data.startswith("ng:ohardcore:"):
                        tail = data.split(":")[-1].strip().lower()
                        if tail == "status":
                            en = await game.is_hardcore_mode()
                            await out(
                                ("☠️ هاردکور روشن است." if en else "✅ هاردکور خاموش است."),
                                force_new=True,
                            )
                            return
                        en = tail in ("1", "on", "true", "yes")
                    else:
                        en = not await game.is_hardcore_mode()
                    msg = await game.set_hardcore_mode(pid, en)
                    on = await game.is_hardcore_mode()
                    status = "☠️ روشن" if on else "✅ خاموش"
                    await out(
                        msg + chr(10) + chr(10) + f"وضعیت فعلی هاردکور: {status}",
                        ik([
                            [("☠️ روشن کردن هاردکور", "ng:ohardcore:1")],
                            [("🕊 خاموش کردن هاردکور", "ng:ohardcore:0")],
                            [("⬅️ پنل مالک", "ng:opanel")],
                        ]),
                        force_new=True,
                    )
                except GameError as e:
                    await out(f"❌ {e}", force_new=True)
                except Exception as e:
                    log.exception("ohardcore")
                    await out(f"❌ خطا در هاردکور: {e}", force_new=True)
                return

            if data == "ng:orefstats":
                await out(await game.referral_stats_text())
                return
            
            if data == "ng:ref" or data == "ng:ref:panel":
                try:
                    txt = await game.referral_panel_text(pid)
                except Exception as e:
                    log.exception("ref panel")
                    txt = "🎁 سیستم دعوت"
                await out(txt, ik([
                    [("📋 نمایش کد دعوت", "ng:refcode")],
                    [("✍️ وارد کردن کد دعوت", "ng:refenter")],
                    back_row(),
                ]))
                return

            if data == "ng:refcode":
                row = await game.ensure_referral_row(pid)
                code = row["referral_code"]
                await out(
                    "📋 کد دعوت شما:\n\n"
                    + code
                    + "\n\nاین کد را کپی کنید و برای دوستتان بفرستید.\n"
                    "(ربات‌ها مستقیماً کلیپ‌بورد گوشی را کنترل نمی‌کنند.)"
                )
                return
            if data == "ng:refenter":
                await _set_pending(game, pid, "ref_code")
                await out(
                    "✍️ وارد کردن کد دعوت\n\n"
                    "کد دعوت دوستت را همین‌جا بفرست.\n"
                    "مثال: WW123456\n\n"
                    "اگر هنوز کشور نداری، کد ذخیره می‌شود و بعد از انتخاب کشور اعمال می‌گردد.",
                    ik([cancel_row()]),
                )
                return

            if data == "ng:o:psearch":
                _pending[pid] = {"kind": "owner_player_search"}
                await out("آیدی عددی، @یوزرنیم یا بخشی از نام را بفرستید:", ik([cancel_row()]))
                return
            if data == "ng:o:players" or data.startswith("ng:o:players:"):
                page = 0
                if data.startswith("ng:o:players:"):
                    try:
                        page = int(data.split(":")[-1])
                    except ValueError:
                        page = 0
                try:
                    stats = await game.player_stats()
                    players, total = await game.list_players_page(page)
                    pages = max(1, (total + game.PAGE_SIZE - 1) // game.PAGE_SIZE)
                    lines = [
                        "👥 کاربران",
                        f"مجموع ثبت‌نام‌شده: {stats['total']}",
                        f"فعال امروز (/start): {stats['active_today']}",
                        f"صفحه {page+1}/{pages}",
                        "",
                    ]
                    rows = []
                    for p in players:
                        cname = p.get("country_label") or (
                            await game.country_name_only(p.get("country_code"))
                            if p.get("country_code") else "بدون کشور"
                        )
                        un = p.get("display_name") or p.get("username") or "بدون‌نام"
                        pid_s = p["player_id"]
                        label = f"{un} | {cname} | {pid_s}"
                        rows.append([(label[:48], f"ng:ou:{pid_s}")])
                    nav = []
                    if page > 0:
                        nav.append(("⬅️ قبلی", f"ng:o:players:{page-1}"))
                    if (page + 1) * game.PAGE_SIZE < total:
                        nav.append(("بعدی ➡️", f"ng:o:players:{page+1}"))
                    if nav:
                        rows.append(nav)
                    rows.append([("🔍 جستجو با @", "ng:o:psearch")])
                    rows.append(back_row())
                    await out("\n".join(lines), ik(rows))
                except Exception as e:
                    log.exception("players panel")
                    await out(f"❌ خطا در بخش کاربران: {e}")
                return

            if data == "ng:o:psearch":
                if not owner:
                    await out("❌ فقط مالک")
                    return
                _pending[pid] = {"kind": "owner_player_search"}
                await out(
                    "🔍 جستجوی بازیکن" + "\n\n"
                    + "یکی از این‌ها را بفرستید:" + "\n"
                    + "• @username" + "\n"
                    + "• نام نمایشی" + "\n"
                    + "• شناسه عددی" + "\n"
                    + "• نام یا کد کشور" + "\n\n"
                    + "مثال: @commander04",
                    ik([cancel_row()]),
                )
                return


            if data in ("ng:owners", "ng:o:owners"):
                if not game.is_primary_owner(pid):
                    await out("❌ فقط مالک اصلی می‌تواند مالکان را مدیریت کند.")
                    return
                try:
                    body = await game.owners_panel_text()
                except Exception as e:
                    body = f"مدیریت مالکان\n{e}"
                rows = await game.db.fetch(
                    "SELECT player_id, un_code FROM ng_extra_owners WHERE COALESCE(active,1)=1 ORDER BY un_code"
                )
                kb = [[("➕ افزودن با آیدی عددی", "ng:owners:add")]]
                for r in rows:
                    kb.append([(f"🗑 حذف {r['player_id']} ({r['un_code']})", f"ng:owners:del:{r['player_id']}")])
                kb.append(back_row())
                await out(body, ik(kb))
                return
            if data == "ng:owners:add":
                if not game.is_primary_owner(pid):
                    await out("❌ فقط مالک اصلی")
                    return
                _pending[pid] = {"kind": "add_co_owner"}
                await out(
                    "شناسه عددی کاربر را برای افزودن به‌عنوان مالک بنویس.\nمثال: 123456789",
                    ik([cancel_row()]),
                )
                return
            if data.startswith("ng:owners:del:"):
                if not game.is_primary_owner(pid):
                    await out("❌ فقط مالک اصلی می‌تواند حذف کند.")
                    return
                try:
                    tid = int(data.split(":")[-1])
                    msg = await game.remove_co_owner(pid, tid)
                    await out(msg)
                except Exception as e:
                    await out(f"❌ {e}")
                return

            if data == "ng:o:world":
                await out(await game.world_status_text(for_owner=owner))
                return

            if data.startswith("ng:oueq:"):
                try:
                    tid = int(str(data).split(":")[-1])
                except Exception:
                    await out("❌ شناسه نامعتبر")
                    return
                code = await game.resolve_country_for_player(tid)
                if not code:
                    p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                    code = (p or {}).get("country_code")
                if not code:
                    await out("❌ این بازیکن کشور ندارد. اول کشور/ریکاوری لازم است.")
                    return
                _pending[pid] = {"kind": "owner_eq_grant", "target": tid, "code": code}
                await out(
                    "🪖 تنظیم تجهیزات\n\n"
                    f"بازیکن: {tid}\nکشور: {await game.country_label(code)}\n\n"
                    "لیست را مثل نمونه بفرست (هر خط یک قلم):\n\n"
                    "۱۰ تا بی۲\n"
                    "۱۰ تا اف۲۲\n"
                    "ناو جرالد فورد\n"
                    "۵ تا ناوچه رزمی\n"
                    "۲ تا بمب اتم\n"
                    "۳ تا پالایشگاه نفت\n\n"
                    "برای لغو: لغو",
                    ik([[("❌ انصراف", f"ng:ou:{tid}")]]),
                )
                return

            if data.startswith("ng:dcd:"):
                try:
                    tid = int(str(data).split(":")[-1])
                except Exception:
                    await out("❌ شناسه نامعتبر")
                    return
                try:
                    msg = await game.clear_destroy_cooldown(pid, tid)
                    log.info("dcd cleared by=%s target=%s", pid, tid)
                    await out(msg, ik([[("👤 بازگشت به کاربر", f"ng:ou:{tid}")], [("🏠 خانه", "ng:home")]]))
                except GameError as e:
                    await out(f"❌ {e}", ik([[("👤 بازگشت", f"ng:ou:{tid}")]]))
                except Exception as e:
                    log.exception("ng:dcd")
                    await out(f"❌ خطا در رفع محدودیت: {e}")
                return


            # ---- Owner: manual set country (index-based callbacks; reliable on Bale) ----
            if (
                data.startswith("ng:ousetcty:")
                or data.startswith("ng:sc:")
                or data.startswith("ng:scgo:")
                or data.startswith("ng:ousetctygo:")
                or data.startswith("ng:ousetctytype:")
                or data.startswith("ng:scpage:")
            ):
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                # list / page: ng:ousetcty:TID  | ng:ousetcty:TID:PAGE | ng:sc:TID:PAGE
                if data.startswith("ng:ousetctytype:"):
                    try:
                        tid = int(str(data).split(":")[-1])
                    except Exception:
                        await out("❌ شناسه نامعتبر", force_new=True)
                        return
                    _pending[pid] = {"kind": "owner_set_country", "target": tid}
                    await out(
                        f"کد کشور را بفرستید برای بازیکن {tid} (مثال: IR یا US):",
                        ik([[("👤 انصراف", f"ng:ou:{tid}")]]),
                        force_new=True,
                    )
                    return
                if data.startswith("ng:scgo:") or data.startswith("ng:ousetctygo:"):
                    parts = str(data).split(":")
                    # ng:scgo:TID:CODE  (preferred)  or legacy ng:scgo:TID:IDX
                    try:
                        tid = int(parts[2])
                    except Exception:
                        await out("❌ شناسه نامعتبر", force_new=True)
                        return
                    code = ""
                    if len(parts) > 3:
                        raw = ":".join(parts[3:]).strip()
                        if raw.isdigit() and data.startswith("ng:scgo:"):
                            # legacy index into in-memory cache
                            idx = int(raw)
                            codes = _set_country_cache.get(int(pid)) or []
                            if 0 <= idx < len(codes):
                                code = codes[idx]
                            else:
                                await out(
                                    "❌ لیست منقضی شده. دوباره «تنظیم کشور» را باز کنید.",
                                    ik([[("🗺 تنظیم کشور", f"ng:ousetcty:{tid}")], [("👤 بازگشت", f"ng:ou:{tid}")]]),
                                    force_new=True,
                                )
                                return
                        else:
                            code = raw.upper()
                    if not code:
                        await out("❌ کد کشور خالی است", force_new=True)
                        return
                    try:
                        await out("⏳ در حال تنظیم کشور…", force_new=True)
                        msg = await game.admin_assign_country(pid, tid, code)
                        await out(
                            msg,
                            ik([[("👤 پروفایل", f"ng:ou:{tid}")], [("🏠 خانه", "ng:home")]]),
                            force_new=True,
                        )
                    except GameError as e:
                        await out(
                            f"❌ {e}",
                            ik([[("🗺 دوباره", f"ng:ousetcty:{tid}")], [("👤 بازگشت", f"ng:ou:{tid}")]]),
                            force_new=True,
                        )
                    except Exception as e:
                        log.exception("set country go")
                        await out(f"❌ خطا در تنظیم کشور: {e}", force_new=True)
                    return
                # list page
                parts = str(data).split(":")
                try:
                    tid = int(parts[2])
                except Exception:
                    await out("❌ شناسه نامعتبر", force_new=True)
                    return
                page = 0
                if len(parts) >= 4 and str(parts[3]).isdigit():
                    page = int(parts[3])
                try:
                    countries, total = await game.list_free_countries_for_assign(page=page, page_size=12)
                    codes = [str(c["country_code"]).upper() for c in countries]
                    # store full page codes under owner pid for index callbacks
                    base = page * 12
                    full_cache = _set_country_cache.get(int(pid)) or []
                    # keep simple: replace cache with this page mapped by absolute index
                    # rebuild cache as only current page codes; idx is page-local
                    _set_country_cache[int(pid)] = codes
                    if not countries:
                        await out(
                            "کشور آزادی برای تخصیص نیست.",
                            ik([[("👤 بازگشت", f"ng:ou:{tid}")]]),
                            force_new=True,
                        )
                        return
                    rows = []
                    for i, c in enumerate(countries):
                        flag = c.get("flag") or ""
                        name = c.get("name_fa") or c["country_code"]
                        dest = "(نابودشده) " if int(c.get("is_destroyed") or 0) else ""
                        label = f"{flag} {dest}{name}".strip()[:40]
                        cc = str(c.get("country_code") or "").upper()
                        # embed code directly so Railway multi-instance / restart cannot lose selection
                        cb = f"ng:scgo:{tid}:{cc}"
                        if len(cb) > 64:
                            cb = f"ng:scgo:{tid}:{i}"
                            # keep index fallback in cache
                        rows.append([(label, cb)])
                    nav = []
                    if page > 0:
                        nav.append(("⬅️ قبلی", f"ng:ousetcty:{tid}:{page-1}"))
                    if (page + 1) * 12 < total:
                        nav.append(("بعدی ➡️", f"ng:ousetcty:{tid}:{page+1}"))
                    if nav:
                        rows.append(nav)
                    rows.append([("✍️ ورود کد", f"ng:ousetctytype:{tid}")])
                    rows.append([("👤 بازگشت", f"ng:ou:{tid}")])
                    await out(
                        f"🗺 تنظیم کشور برای {tid}" + chr(10)
                        + f"یک کشور را لمس کنید — صفحه {page+1}" + chr(10)
                        + f"آزاد: {total}",
                        ik(rows),
                        force_new=True,
                    )
                except Exception as e:
                    log.exception("ousetcty list")
                    await out(f"❌ خطا در لیست کشورها: {e}", force_new=True)
                return

            if data.startswith("ng:orec:") and not data.startswith("ng:orecgo:"):
                try:
                    tid = int(str(data).split(":")[-1])
                except Exception:
                    await out("❌ شناسه نامعتبر")
                    return
                try:
                    snap = await game.get_latest_destroy_snapshot(tid)
                    if not snap:
                        await out(
                            "❌ اسنپ‌شات نابودی برای این بازیکن پیدا نشد.\n"
                            "می‌توانید با «🗺 تنظیم کشور» دستی کشور بدهید.",
                            ik([
                                [("🗺 تنظیم کشور", f"ng:ousetcty:{tid}")],
                                [("👤 بازگشت", f"ng:ou:{tid}")],
                            ]),
                            force_new=True,
                        )
                        return
                    cname = await game.country_label(snap["country_code"])
                    hp_full = int(float(snap.get("max_hp") or 1000) or 1000)
                    hp_full = int(float(snap.get("max_hp") or 1000) or 1000)
                    treas = int(float(snap.get("treasury") or 0))
                    inv_n = 0
                    try:
                        inv_n = len(__import__("json").loads(snap.get("inventory_json") or "[]"))
                    except Exception:
                        inv_n = 0
                    body = (
                        "♻️ ریکاوری ۶ ساعته\n\n"
                        f"بازیکن: {tid}\n"
                        f"کشور: {cname}\n"
                        f"خزانه بازگردانی: {treas:,}\n"
                        f"تجهیزات: {inv_n} نوع\n"
                        f"HP بعد از ریکاوری: {hp_full} (کامل)\n"
                        f"زمان نابودی: {snap.get('destroyed_at')}\n\n"
                        "همه چیز به حالت اوج (قبل از غنیمت) برمی‌گردد."
                    )
                    await out(body, ik([[("✅ تأیید ریکاوری", f"ng:orecgo:{tid}"), ("❌ انصراف", f"ng:ou:{tid}")]]))
                except Exception as e:
                    log.exception("ng:orec")
                    await out(f"❌ خطا: {e}")
                return

            if data.startswith("ng:orecgo:"):
                try:
                    tid = int(str(data).split(":")[-1])
                except Exception:
                    await out("❌ شناسه نامعتبر")
                    return
                try:
                    await out("⏳ در حال ریکاوری…", force_new=True)
                    msg = await game.recover_destroyed_player(pid, tid)
                    await out(
                        msg,
                        ik([
                            [("👤 پروفایل", f"ng:ou:{tid}")],
                            [("🗺 تنظیم کشور", f"ng:ousetcty:{tid}")],
                            [("🏠 خانه", "ng:home")],
                        ]),
                        force_new=True,
                    )
                except GameError as e:
                    await out(f"❌ {e}", ik([[("👤 بازگشت", f"ng:ou:{tid}")]]))
                except Exception as e:
                    log.exception("ng:orecgo")
                    await out(f"❌ خطا در ریکاوری: {e}")
                return

            if data.startswith("ng:ocd:"):
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                try:
                    sec = int(data.split(":")[-1])
                    msg = await game.set_attack_cooldown_sec(pid, sec)
                    # if 30 requested, also set nuke to 60 for consistency when using std preset buttons
                    if sec == 30:
                        try:
                            await game.set_nuke_cooldown_sec(pid, 60)
                            msg += chr(10) + "✅ کول‌داون اتمی هم ۶۰ث شد."
                        except Exception:
                            pass
                    got = await game.attack_cooldown_sec()
                    await out(msg + chr(10) + f"مقدار ذخیره‌شده: {got} ثانیه", force_new=True)
                except Exception as e:
                    log.exception("ocd set")
                    await out(f"❌ {e}", force_new=True)
                return
            if data == "ng:oshop" or data.startswith("ng:oshop:"):
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                try:
                    if data.startswith("ng:oshop:"):
                        locked = data.endswith(":1")
                    else:
                        locked = not await game.is_shop_locked_by_owner()
                    msg = await game.set_shop_locked(pid, locked)
                    await out(msg, force_new=True)
                except GameError as e:
                    await out(f"❌ {e}", force_new=True)
                except Exception as e:
                    log.exception("oshop")
                    await out(f"❌ خطا در قفل فروشگاه: {e}", force_new=True)
                return

            if data.startswith("ng:owar:"):
                await out(await game.set_war(pid, data.endswith(":1")))
                return
            if data.startswith("ng:onuke:"):
                await out(await game.set_nuclear(pid, data.endswith(":1")))
                return
            if data == "ng:ostmt":
                rows_db = await game.db.fetch("SELECT * FROM ng_statements WHERE status='pending'")
                btns = []
                for s in rows_db[:15]:
                    cn = await game.country_name_only(s["country_code"])
                    btns.append([
                        (f"✅#{s['id']} {cn}", f"ng:sapp:{s['id']}"),
                        (f"❌#{s['id']}", f"ng:srej:{s['id']}"),
                    ])
                btns.append(back_row())
                await out("بیانیه‌های در انتظار", ik(btns) if rows_db else main_kb(owner))
                return
            if data.startswith("ng:sapp:"):
                try:
                    await out(await game.review_statement(int(data.split(":")[-1]), True, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:srej:"):
                try:
                    await out(await game.review_statement(int(data.split(":")[-1]), False, pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ologs":
                if not owner:
                    await out("❌ فقط مالک")
                    return
                flags = await game.get_log_flags()
                cur = await game.get_log_group()
                rows = []
                rows.append([("📡 تنظیم گروه لاگ", "ng:osetlogg")])
                for k, v in flags.items():
                    rows.append([(f"{'🟢' if v else '🔴'} {k}", f"ng:logtoggle:{k}")])
                rows.append(back_row())
                main_g = await game.get_main_group()
                text = (
                    "📜 تنظیم لاگ‌ها\n\n"
                    f"گروه لاگ (همه لاگ‌ها):\n{game.format_log_group(cur)}\n\n"
                    f"گروه اصلی (بیانیه‌ها هم اینجا):\n{main_g or '—'}\n\n"
                    "📢 بیانیه‌ها در هر دو گروه ارسال می‌شوند.\n"
                    "📝 بقیه لاگ‌ها فقط در گروه لاگ می‌روند.\n\n"
                    "انواع لاگ (لمس = تغییر وضعیت):"
                )
                await out(text, ik(rows))
                return
            if data == "ng:osetlogg":
                if not owner:
                    await out("❌ فقط مالک")
                    return
                cur = await game.get_log_group()
                main_g = await game.get_main_group()
                _pending[pid] = {"kind": "set_log_group"}
                await out(
                    "📡 تنظیم گروه لاگ\n\n"
                    f"گروه لاگ فعلی: {game.format_log_group(cur)}\n"
                    f"گروه اصلی: {main_g or '—'}\n\n"
                    "ربات باید در گروه لاگ عضو و ادمین باشد.\n"
                    "لاگ‌های عادی فقط به گروه لاگ می‌روند.\n"
                    "بیانیه‌ها همزمان در گروه اصلی و گروه لاگ ارسال می‌شوند.\n\n"
                    "آیدی عددی یا @یوزرنیم گروه لاگ را بفرستید:",
                    ik([cancel_row()]),
                    force_new=True,
                )
                return
            if data.startswith("ng:logtoggle:"):
                kind = data.split(":")[-1]
                flags = await game.get_log_flags()
                try:
                    await out(await game.set_log_flag(pid, kind, not flags.get(kind, True)))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:oban":
                await _set_pending(game, pid, "ban_wizard_target")
                await out(
                    "🚫 بن کاربر\n\nآیدی عددی یا @username بازیکن را بفرستید:",
                    ik([cancel_row()]),
                )
                return
            if data == "ng:obansearch":
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                await _set_pending(game, pid, "ban_search_code")
                await out("کد بن را وارد کنید:", ik([cancel_row()]), force_new=True)
                return
            if data == "ng:ounban":
                _pending[pid] = {"kind": "unban_user"}
                await out("آیدی عددی یا @username برای رفع بن:")
                return

            # ── Tickets (user + owner) ────────────────────────────────
            if data == "ng:tix:mine":
                rows_t = await game.list_tickets_for_user(pid)
                if not rows_t:
                    await out("هنوز تیکتی ندارید.", ik(ticket_user_inline()), force_new=True)
                    return
                kb = []
                for t in rows_t[:15]:
                    stt = "🟢 باز" if (t.get("status") == "open") else "🔒 بسته"
                    title = (t.get("subject") or "بدون موضوع")[:28]
                    kb.append([(f"#{t['id']} | {stt} | {title}", f"ng:tix:open:{t['id']}")])
                kb.append([("✍️ تیکت جدید", "ng:tix:new")])
                kb.append(back_row())
                await out("📬 تیکت‌های شما:", ik(kb), force_new=True)
                return
            if data == "ng:tix:new":
                await _set_pending(game, pid, "ticket_new_body")
                await out("✍️ متن تیکت را بنویسید:\n(حداقل ۳ کاراکتر)", ik([cancel_row()]), force_new=True)
                return
            if data.startswith("ng:tix:open:"):
                tid = int(data.split(":")[-1])
                t = await game.get_ticket(tid)
                if not t or int(t["player_id"]) != int(pid):
                    await out("❌ تیکت یافت نشد.", force_new=True)
                    return
                msgs = await game.ticket_messages(tid)
                body = game.format_ticket_thread(t, msgs)
                rows = []
                if t.get("status") == "open":
                    rows.append([("✉️ پاسخ", f"ng:tix:reply:{tid}")])
                rows.append(back_row())
                await out(body, ik(rows), force_new=True)
                return
            if data.startswith("ng:tix:reply:"):
                tid = int(data.split(":")[-1])
                t = await game.get_ticket(tid)
                if not t or int(t["player_id"]) != int(pid):
                    await out("❌ تیکت یافت نشد.", force_new=True)
                    return
                if t.get("status") != "open":
                    await out("این تیکت بسته است.", force_new=True)
                    return
                await _set_pending(game, pid, "ticket_reply_body", ticket_id=tid, is_admin=False)
                await out("پیام خود را بنویسید:", ik([cancel_row()]), force_new=True)
                return

            if data == "ng:otix":
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                await out("🎫 مدیریت تیکت‌ها\nیک بخش را انتخاب کنید:", ik(ticket_owner_menu_kb()), force_new=True)
                return
            if data == "ng:otix:openlist":
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                rows_t = await game.list_open_tickets()
                if not rows_t:
                    await out("تیکت بازی نیست.", ik([[("🎫 تیکت‌ها", "ng:otix")], back_row()]), force_new=True)
                    return
                kb = [[(f"#{t['id']} | u:{t['player_id']} | {(t.get('subject') or '')[:20]}", f"ng:otix:view:{t['id']}")] for t in rows_t[:20]]
                kb.append([("🎫 تیکت‌ها", "ng:otix")])
                kb.append(back_row())
                await out("تیکت‌های باز:", ik(kb), force_new=True)
                return
            if data == "ng:otix:unans":
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                rows_t = await game.list_unanswered_tickets()
                if not rows_t:
                    await out("مورد جواب‌نداده‌ای نیست.", ik([[("🎫 تیکت‌ها", "ng:otix")], back_row()]), force_new=True)
                    return
                kb = [[(f"#{t['id']} | u:{t['player_id']} | {(t.get('subject') or '')[:20]}", f"ng:otix:view:{t['id']}")] for t in rows_t[:20]]
                kb.append([("🎫 تیکت‌ها", "ng:otix")])
                kb.append(back_row())
                await out("تیکت‌های جواب‌داده‌نشده:", ik(kb), force_new=True)
                return
            if data.startswith("ng:otix:view:") or data.startswith("ng:otix:open:"):
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                try:
                    tid = int(str(data).split(":")[-1])
                except Exception:
                    await out("❌ شناسه تیکت نامعتبر.", force_new=True)
                    return
                t = await game.get_ticket(tid)
                if not t:
                    await out("تیکت یافت نشد.", ik(ticket_owner_menu_kb()), force_new=True)
                    return
                msgs = await game.ticket_messages(tid)
                body = game.format_ticket_thread(t, msgs)
                is_open = (t.get("status") == "open")
                await out(body, ik(ticket_owner_view_kb(tid, is_open=is_open)), force_new=True)
                return
            if data.startswith("ng:otix:reply:"):
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                tid = int(data.split(":")[-1])
                _pending[pid] = {"kind": "ticket_reply_body", "ticket_id": tid, "is_admin": True}
                await out("پاسخ ادمین را بنویسید:", ik([cancel_row()]), force_new=True)
                return
            if data.startswith("ng:otix:close:"):
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                try:
                    tid = int(str(data).split(":")[-1])
                except Exception:
                    await out("❌ شناسه تیکت نامعتبر.", force_new=True)
                    return
                try:
                    result = await game.close_ticket(tid, pid)
                    try:
                        if hasattr(cq, "answer"):
                            await cq.answer(text="تیکت بسته شد", show_alert=True)
                    except Exception:
                        pass
                    try:
                        tclosed = await game.get_ticket(tid)
                        if tclosed and hasattr(bot, "send_message"):
                            await bot.send_message(
                                int(tclosed["player_id"]),
                                f"🔒 تیکت #{tid} توسط پشتیبانی بسته شد.",
                                components=banned_kb(),
                            )
                    except Exception:
                        log.exception("notify user ticket closed")
                    await out(
                        f"✅ {result}\nتیکت #{tid} بسته شد.",
                        ik(ticket_owner_menu_kb()),
                        force_new=True,
                    )
                except GameError as e:
                    await out(f"❌ {e}", ik(ticket_owner_menu_kb()), force_new=True)
                except Exception:
                    log.exception("otix close failed data=%s", data)
                    await out("❌ بستن تیکت ناموفق بود. دوباره تلاش کنید.", ik(ticket_owner_menu_kb()), force_new=True)
                return
            if data == "ng:ohpall":
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                _pending[pid] = {"kind": "owner_hp_all"}
                await out(
                    "❤️ جون همگانی" + chr(10)
                    + "مقدار تغییر HP برای همه کشورهای بازیکن را بنویسید:" + chr(10) + chr(10)
                    + "مثال افزایش: 100 یا +100" + chr(10)
                    + "مثال کاهش: -100" + chr(10) + chr(10)
                    + "بدون سقف برای افزایش (max_hp در صورت نیاز بالا می‌رود).",
                    ik([cancel_row()]),
                    force_new=True,
                )
                return

            if data == "ng:ogiveall":
                _pending[pid] = {"kind": "owner_give_all"}
                await out(
                    "💵 پول همگانی (واریز / کسر)" + chr(10)
                    + "مبلغ یکسان برای همه کشورهای بازیکن را بنویسید:" + chr(10) + chr(10)
                    + "مثال واریز: 5000000" + chr(10)
                    + "مثال کسر از همه: -10000" + chr(10) + chr(10)
                    + "عدد منفی = کم کردن از خزانه‌ی همه",
                    ik([cancel_row()]),
                )
                return
            if data == "ng:odaily":
                try:
                    targets = await game.list_daily_payout_targets()
                    n = await game.daily_payout_all(force=True)
                    if n:
                        await out(
                            "✅ پرداخت دستی درآمد روزانه انجام شد." + "\n"
                            + f"تعداد کشورها: {n}" + "\n"
                            + "فقط کشورهای زندهٔ دارای رهبر (غیرنابود، غیرریست، غیر بن) پرداخت شدند." + "\n"
                            + "اگر دوباره بزنید، دوباره پرداخت می‌شود."
                        )
                    else:
                        await out(
                            "ℹ️ کشوری برای پرداخت نیست." + "\n"
                            + f"کشورهای واجد شرایط الان: {len(targets)}" + "\n"
                            + "(نابود / بدون رهبر / بن‌شده حساب نمی‌شوند)"
                        )
                except Exception as e:
                    log.exception("odaily")
                    await out(f"❌ {e}")
                return
            if data == "ng:omoney":
                _pending[pid] = {"kind": "admin_money"}
                await out("فرمت: CODE مبلغ\nمثال: IR 1000000")
                return
            if data == "ng:oreset1":
                await out(
                    "⚠ تمام داده‌های جهان پاک می‌شود.\nادامه؟",
                    ik([[("تأیید مرحله بعد", "ng:oreset2")], back_row()]),
                )
                return
            if data == "ng:oreset2":
                _pending[pid] = {"kind": "reset_phrase"}
                await out("عبارت زیر را دقیق بنویسید:\nریست کامل جهان")
                return


            if data == "ng:joincheck":
                ok = await require_membership(pid, cq, True, force=True)
                if ok:
                    await out(
                        "✅ عضویت تأیید شد." + chr(10) + "حالا می‌توانید از ربات استفاده کنید.",
                        main_kb(owner, bool(code)),
                    )
                return
            if data.startswith("ng:joinlink:"):
                chats = await game.list_forced_chats()
                try:
                    cid = int(data.split(":")[-1])
                except Exception:
                    await out("❌ شناسه نامعتبر")
                    return
                ch = next((c for c in chats if int(c["id"]) == cid), None)
                if not ch:
                    await out("❌ مورد یافت نشد")
                    return
                link = (ch.get("invite_link") or "").strip()
                if not link:
                    raw = str(ch.get("chat_id") or "")
                    if raw.startswith("@"):
                        link = "https://ble.ir/" + raw.lstrip("@")
                title = ch.get("title") or ch.get("chat_id")
                if link:
                    await out(
                        f"📥 لینک عضویت «{title}»:" + chr(10) + str(link) + chr(10) + chr(10)
                        + "عضو شوید سپس «عضو شدم — تأیید» را بزنید.",
                        ik([
                            [("📥 باز کردن لینک", link)],
                            [("✅ عضو شدم — تأیید", "ng:joincheck")],
                        ]),
                    )
                else:
                    await out(
                        f"شناسه: {ch.get('chat_id')}" + chr(10) + "لینک ثبت نشده. از جست‌وجوی بله عضو شوید.",
                        ik([[("✅ عضو شدم — تأیید", "ng:joincheck")]]),
                    )
                return




            # ---- Country control ----
            if data == "ng:ctrl":
                nav_push(pid, "ctrl")
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                text_c = await game.control.panel_text(code)
                rows = [
                    [("📜 تصویب قوانین", "ng:ctrl:laws")],
                    [("🌊 کنترل تنگه‌ها", "ng:ctrl:straits")],
                    [("✈️ پروازها", "ng:ctrl:flights"), ("🚢 دریایی", "ng:ctrl:maritime")],
                    [("🌐 اینترنت", "ng:ctrl:net")],
                    back_row(),
                ]
                await out(text_c, ik(rows))
                return
            if data == "ng:ctrl:flights":
                rows = [[("✈️ باز کردن", "ng:ctrl:fly:1"), ("⛔ توقف", "ng:ctrl:fly:0")], back_row()]
                await out("مدیریت پروازها:", ik(rows))
                return
            if data.startswith("ng:ctrl:fly:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    await out(await game.control.toggle_flights(code, pid, data.endswith(":1")))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ctrl:maritime":
                rows = [[("🚢 باز کردن", "ng:ctrl:sea:1"), ("⛔ توقف", "ng:ctrl:sea:0")], back_row()]
                await out("مدیریت سفر دریایی:", ik(rows))
                return
            if data.startswith("ng:ctrl:sea:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    await out(await game.control.toggle_maritime(code, pid, data.endswith(":1")))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ctrl:net":
                rows = [[("🌐 وصل", "ng:ctrl:net:1"), ("⛔ قطع", "ng:ctrl:net:0")], back_row()]
                await out("مدیریت اینترنت:", ik(rows))
                return
            if data.startswith("ng:ctrl:net:") and data.count(":") == 3:
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    await out(await game.control.toggle_internet(code, pid, data.endswith(":1")))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ctrl:straits":
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                rows = []
                straits = await game.control.list_controllable_straits(code)
                if not straits:
                    await out("کشور شما اختیار کنترل هیچ تنگه استراتژیکی را ندارد.", ik([back_row()]))
                    return
                for s in straits:
                    st = "بسته ⛔" if int(s["closed"]) else "باز ✅"
                    rows.append([(f"{s['name_fa']} ({st})", f"ng:strait:{s['strait_code']}")])
                rows.append(back_row())
                await out("تنگه‌های تحت اختیار شما:", ik(rows))
                return
            if data.startswith("ng:strait:") and data.count(":") == 2:
                sc = data.split(":")[-1]
                rows = [
                    [("⛔ بستن تنگه", f"ng:straitclose:{sc}"), ("✅ باز کردن", f"ng:straitopen:{sc}")],
                    back_row(),
                ]
                await out("عملیات تنگه:", ik(rows))
                return
            if data.startswith("ng:straitclose:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    await out(await game.control.toggle_strait(code, pid, data.split(":")[-1], True))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:straitopen:"):
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                try:
                    await out(await game.control.toggle_strait(code, pid, data.split(":")[-1], False))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ctrl:laws":
                rows = [
                    [("✍️ قانون جدید", "ng:lawnew")],
                    [("📋 قوانین فعال من", "ng:lawmine")],
                    back_row(),
                ]
                await out("📜 تصویب قوانین\nهر کشور حداکثر ۳ قانون در روز. با ثبت هر قانون ۵٬۰۰۰٬۰۰۰ به خزانه اضافه می‌شود (جدا از درآمد روزانه).", ik(rows))
                return
            if data == "ng:lawnew":
                _pending[pid] = {"kind": "law_title"}
                await out("عنوان قانون را بنویسید:", ik([cancel_row()]))
                return
            if data == "ng:lawmine":
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                laws = await game.control.active_laws_for(code)
                if not laws:
                    await out("قانون فعالی ندارید.")
                    return
                lines = ["قوانین فعال:"]
                for L in laws:
                    lines.append(f"• #{L['id']} {L['title']} (+{int(float(L['income_bonus'] or 0)):,}/روز)")
                await out("\n".join(lines))
                return
            if data == "ng:olaws":
                laws = await game.control.pending_laws()
                rows = []
                lines = [f"📜 قوانین در انتظار: {len(laws)}"]
                for L in laws[:20]:
                    name = await game.country_label(L["country_code"])
                    lines.append(f"#{L['id']} {name}: {L['title']}")
                    rows.append([
                        (f"✅ #{L['id']}", f"ng:lawok:{L['id']}"),
                        (f"❌ #{L['id']}", f"ng:lawno:{L['id']}"),
                    ])
                rows.append(back_row())
                await out("\n".join(lines), ik(rows))
                return
            if data.startswith("ng:lawok:"):
                lid = int(data.split(":")[-1])
                _pending[pid] = {"kind": "law_bonus", "law_id": lid}
                await out("در صورت تمایل، پاداش درآمد روزانه این قانون را به عدد بنویسید (۰ تا ۵ میلیون). برای بدون پاداش ۰ بفرستید:")
                return
            if data.startswith("ng:lawno:"):
                try:
                    await out(await game.control.review_law(int(data.split(":")[-1]), pid, False))
                except ControlError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:go:eco":
                if not code:
                    await out("هنوز کشوری تحت فرمان شما نیست.")
                    return
                await out(await game.economy_card(code))
                return



            if data == "ng:oprices":
                rows = []
                pair = []
                for cat, name in CAT_FA.items():
                    pair.append((name, f"ng:opricecat:{cat}"))
                    if len(pair) == 2:
                        rows.append(pair)
                        pair = []
                if pair:
                    rows.append(pair)
                rows.append(back_row())
                await out("🏷 قیمت فروشگاه\nدسته را انتخاب کنید:", ik(rows))
                return
            if data.startswith("ng:opricecat:"):
                cat = data.split(":")[-1]
                items = await game.list_catalog_by_category(cat)
                rows = []
                for i in items[:40]:
                    rows.append([(
                        f"{i['name_fa']} | {int(float(i['unit_price'])):,}",
                        f"ng:opriceitem:{i['item_code']}",
                    )])
                rows.append([("⬅️ دسته‌ها", "ng:oprices")])
                rows.append(back_row())
                await out(f"آیتم‌های {CAT_FA.get(cat, cat)} — روی مورد بزنید تا قیمت جدید بدهید:", ik(rows))
                return
            if data.startswith("ng:opriceitem:"):
                ic = data.split(":")[-1]
                await game._reload_catalog_prices()
                it = game._cat.get(ic) or {}
                _pending[pid] = {"kind": "set_shop_price", "item": ic}
                await out(
                    f"قیمت فعلی «{it.get('name_fa', ic)}»: {int(float(it.get('unit_price') or 0)):,}\n"
                    f"قیمت جدید را به عدد بنویسید:",
                    ik([cancel_row()]),
                )
                return
            if data == "ng:odiscount":
                cur = await game.get_shop_discount_pct()
                status = (
                    f"تخفیف فعلی: {int(cur)}٪ فعال"
                    if cur > 0
                    else "تخفیف فعلی: خاموش (قیمت پایه)"
                )
                rows = [
                    [("۱۰٪", "ng:odiscon:10"), ("۲۰٪", "ng:odiscon:20")],
                    [("۳۰٪", "ng:odiscon:30"), ("۴۰٪", "ng:odiscon:40")],
                    [("۵۰٪", "ng:odiscon:50"), ("۶۰٪", "ng:odiscon:60")],
                    [("۷۰٪", "ng:odiscon:70")],
                    [("❌ غیرفعال کردن تخفیف", "ng:odiscoff")],
                    back_row(),
                ]
                await out(
                    "🏷 تخفیف سراسری فروشگاه" + "\n"
                    + status + "\n\n"
                    + "تخفیف روی قیمت پایه همه کالاها اعمال می‌شود." + "\n"
                    + "قیمت پایه در دیتابیس عوض نمی‌شود." + "\n"
                    + "آیتم جدید و تغییر قیمت هم شامل تخفیف می‌شوند." + "\n"
                    + "با خاموش کردن، همه به قیمت پایه برمی‌گردند.",
                    ik(rows),
                )
                return
            if data.startswith("ng:odiscon:"):
                pct = float(data.split(":")[-1])
                try:
                    await out(await game.set_shop_discount(pid, pct))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:odiscoff":
                try:
                    await out(await game.set_shop_discount(pid, 0))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            # ---- Double HP (owner only) ----
            if data == "ng:odblhp":
                countries = await game.list_countries()
                owned = [c for c in countries if c.get("owner_player_id")]
                if not owned:
                    await out("هیچ کشور دارای مالکی نیست.", main_kb(owner))
                    return
                rows = []
                for c in owned[:35]:
                    try:
                        on = int(c.get("double_hp") or 0) == 1
                    except Exception:
                        on = False
                    mark = "✅×۲" if on else "—"
                    rows.append([(
                        f"{mark} {c.get('flag') or ''} {c['name_fa']}".strip(),
                        f"ng:odbl:{c['country_code']}",
                    )])
                rows.append(back_row())
                await out("🧬 جان ۲ برابر\nکشور را انتخاب کنید:", ik(rows))
                return

            if data.startswith("ng:odbl:") and data.count(":") == 2 and not data.startswith("ng:odblon") and not data.startswith("ng:odbloff"):
                code = data.split(":")[-1]
                c = await game.db.fetchrow(
                    "SELECT * FROM ng_countries WHERE country_code=$1", (code,)
                )
                if not c:
                    await out("کشور یافت نشد")
                    return
                on = int(c.get("double_hp") or 0) == 1
                st = "فعال ✅" if on else "غیرفعال"
                rows = [
                    [
                        ("✅ فعال کردن ×۲", f"ng:odblon:{code}"),
                        ("❌ خاموش کردن", f"ng:odbloff:{code}"),
                    ],
                    back_row(),
                ]
                await out(
                    f"{c.get('flag') or ''} {c['name_fa']}\n"
                    f"جان ۲ برابر: {st}\n"
                    f"سلامت: {int(float(c['hp']))}/{int(float(c['max_hp']))}",
                    ik(rows),
                )
                return

            if data.startswith("ng:odblon:"):
                code = data.split(":")[-1]
                try:
                    await out(await game.set_double_hp(pid, code, True))
                except GameError as e:
                    await out(f"❌ {e}")
                except Exception:
                    log.exception("double_hp on")
                    await out("❌ خطا در فعال‌سازی جان ۲ برابر")
                return

            if data.startswith("ng:odbloff:"):
                code = data.split(":")[-1]
                try:
                    await out(await game.set_double_hp(pid, code, False))
                except GameError as e:
                    await out(f"❌ {e}")
                except Exception:
                    log.exception("double_hp off")
                    await out("❌ خطا در خاموش کردن جان ۲ برابر")
                return

            if data.startswith("ng:oudblon:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow(
                    "SELECT country_code FROM ng_players WHERE player_id=$1", (tid,)
                )
                code = (p or {}).get("country_code")
                if not code:
                    await out("این کاربر کشور ندارد.")
                    return
                try:
                    await out(await game.set_double_hp(pid, code, True))
                except GameError as e:
                    await out(f"❌ {e}")
                except Exception:
                    log.exception("oudbl on")
                    await out("❌ خطا در فعال‌سازی جان ۲ برابر")
                return

            if data.startswith("ng:oudbloff:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow(
                    "SELECT country_code FROM ng_players WHERE player_id=$1", (tid,)
                )
                code = (p or {}).get("country_code")
                if not code:
                    await out("این کاربر کشور ندارد.")
                    return
                try:
                    await out(await game.set_double_hp(pid, code, False))
                except GameError as e:
                    await out(f"❌ {e}")
                except Exception:
                    log.exception("oudbl off")
                    await out("❌ خطا در خاموش کردن جان ۲ برابر")
                return

            if data == "ng:ohp" or data.startswith("ng:ohp:"):
                page = 0
                if data.startswith("ng:ohp:"):
                    try:
                        page = int(data.split(":")[-1])
                    except ValueError:
                        page = 0
                text_hp, total = await game.list_owned_countries_hp(page=page, page_size=12)
                nav = []
                pages = max(1, (total + 11) // 12)
                if page > 0:
                    nav.append(("⬅️ قبلی", f"ng:ohp:{page-1}"))
                if page + 1 < pages:
                    nav.append(("بعدی ➡️", f"ng:ohp:{page+1}"))
                rows = []
                if nav:
                    rows.append(nav)
                rows.append([("🛡 بازگشت پنل مالک", "ng:opanel")])
                await out(text_hp, ik(rows))
                return
            if data == "ng:orank" or data.startswith("ng:orank:"):
                page = 0
                if data.startswith("ng:orank:"):
                    try:
                        page = int(data.split(":")[-1])
                    except ValueError:
                        page = 0
                try:
                    text_r, total = await game.ranking_power(page=page, page_size=10)
                except Exception as e:
                    log.exception("orank")
                    await out(f"❌ خطا در رنکینگ: {e}", force_new=True)
                    return
                nav = []
                pages = max(1, (total + 9) // 10)
                if page > 0:
                    nav.append(("⬅️ قبلی", f"ng:orank:{page-1}"))
                if page + 1 < pages:
                    nav.append(("بعدی ➡️", f"ng:orank:{page+1}"))
                rows = []
                if nav:
                    rows.append(nav)
                rows.append([("🔄 بروزرسانی", f"ng:orank:{page}")])
                rows.append([("🛡 بازگشت پنل مالک", "ng:opanel")])
                await out(text_r, ik(rows), force_new=True)
                return

            if data == "ng:ohpfull":
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                try:
                    msg = await game.admin_set_all_hp_full(pid)
                    await out(msg, force_new=True)
                except GameError as e:
                    await out(f"❌ {e}", force_new=True)
                except Exception as e:
                    log.exception("ohpfull")
                    await out(f"❌ {e}", force_new=True)
                return
            if data == "ng:opanel":
                rows = []
                if game.is_primary_owner(pid):
                    rows.append([("➕ افزودن مالک جدید", "ng:owners"), ("🛡 لیست مالکان", "ng:owners")])
                try:
                    hc = await game.is_hardcore_mode()
                    hc_label = "☠️ هاردکور: روشن — خاموش کن" if hc else "☠️ هاردکور: خاموش — روشن کن"
                except Exception:
                    hc_label = "☠️ هاردکور روشن/خاموش"
                rows += [
                    [("بازیکنان", "ng:o:players"), ("وضعیت جهان", "ng:o:world")],
                    [(hc_label, "ng:ohardcore")],
                    [("🔒 قطع/فعال خرید فروشگاه", "ng:oshop")],
                    [("💵 پول همگانی", "ng:ogiveall"), ("❤️ جون همگانی", "ng:ohpall")],
                    [("💰 پرداخت درآمد روزانه", "ng:odaily")],
                    [("❤️ دیدن HP ها", "ng:ohp"), ("🏅 رنکینگ", "ng:orank")],
                    [("🧬 جان ۲ برابر کشورها", "ng:odblhp")],
                    [("🎁 مدیریت لجندری", "ng:oleg"), ("💰 شارژ کیف پول", "ng:owallet")],
                    [("⚙️ قیمت و استفاده لجندری", "ng:olegprices")],
                    [("🔒 محدودیت لجندری روشن", "ng:llock:1")],
                    [("🔓 محدودیت لجندری خاموش", "ng:llock:0")],
                    [("🔒 وضعیت محدودیت لجندری", "ng:llock")],
                    [("⬅️ بستن", "ng:home")],
                ]
                await out("🛡 پنل مالک / سازمان ملل", ik(rows))
                return
            if data.startswith("ng:osethp:"):
                if not owner:
                    await out("❌ فقط مالک")
                    return
                try:
                    tid = int(data.split(":")[-1])
                except ValueError:
                    await out("❌ شناسه نامعتبر")
                    return
                # live country for status text
                try:
                    code = await game.resolve_country_for_player(tid)
                except Exception:
                    code = None
                cur_hp = "—"
                max_hp = "—"
                cname = "بدون کشور"
                if code:
                    c = await game.db.fetchrow(
                        "SELECT name_fa, flag, hp, max_hp FROM ng_countries WHERE country_code=$1",
                        (code,),
                    )
                    if c:
                        cname = f"{c.get('flag') or ''} {c.get('name_fa') or code}".strip()
                        cur_hp = int(float(c.get("hp") or 0))
                        max_hp = int(float(c.get("max_hp") or 1000))
                _pending[pid] = {"kind": "owner_set_hp", "target": tid}
                await out(
                    "❤️ تنظیم HP" + "\n"
                    + f"بازیکن: {tid}" + "\n"
                    + f"کشور: {cname}" + "\n"
                    + f"HP فعلی: {cur_hp} / {max_hp}" + "\n\n"
                    + "فرمت را این‌طور بفرستید:" + "\n"
                    + "فعلی/سقف" + "\n"
                    + "مثال: 300/1000" + "\n"
                    + "مثال: 4000/4000" + "\n"
                    + "(بدون محدودیت عددی)",
                    ik([cancel_row()]),
                )
                return

            async def _owner_player_profile_kb(tid: int):
                fast_on = False
                try:
                    fast_on = await game.has_fast_attack_cd(int(tid))
                except Exception:
                    log.exception("has_fast_attack_cd profile")
                    fast_on = False
                cd_row = (
                    [("🕊 خاموش کردن CD30", f"ng:oucd30off:{tid}")]
                    if fast_on
                    else [("⚡ روشن کردن CD30", f"ng:oucd30on:{tid}")]
                )
                return [
                    [("🚫 بن", f"ng:ouban:{tid}"), ("✅ آن‌بن", f"ng:ouunban:{tid}")],
                    [("📦 دارایی‌ها", f"ng:ouinv:{tid}"), ("💰 پول", f"ng:oum:{tid}")],
                    [("NPT وضعیت", f"ng:ounpt:{tid}")],
                    [("➕ NPT", f"ng:ounptadd:{tid}"), ("➖ NPT", f"ng:ounptdel:{tid}")],
                    [("❤️ تنظیم HP", f"ng:osethp:{tid}")],
                    [("💵 دادن پول", f"ng:ougive:{tid}"), ("💸 گرفتن پول", f"ng:outake:{tid}")],
                    [("🧾 مالیات از کاربر", f"ng:outax:{tid}")],
                    [("🧬 جان ×۲ روشن", f"ng:oudblon:{tid}"), ("🧬 جان ×۲ خاموش", f"ng:oudbloff:{tid}")],
                    *cd_row,
                    [("⏱ رفع محدودیت ۳۰دقیقه", f"ng:dcd:{tid}")],
                    [("♻️ ریکاوری نابودی", f"ng:orec:{tid}")],
                    [("🗺 تنظیم کشور", f"ng:ousetcty:{tid}")],
                    [("🪖 تنظیم تجهیزات", f"ng:oueq:{tid}")],
                    [("🎁 آیتم لجندری", f"ng:olegp:{tid}")],
                    [("♻️ ریست کردن کاربر", f"ng:oureset:{tid}")],
                    [("⬅️ لیست کاربران", "ng:o:players:0")],
                ]


            if data.startswith("ng:ou:"):
                if not owner:
                    await out("❌ فقط مالک", force_new=True)
                    return
                try:
                    tid = int(str(data).split(":")[-1])
                except Exception:
                    await out("❌ شناسه نامعتبر", force_new=True)
                    return
                try:
                    try:
                        await game.ensure_player_flags_table()
                    except Exception:
                        pass
                    card = await game.player_admin_card(tid)
                    rows = await _owner_player_profile_kb(tid)
                    await out(card, ik(rows), force_new=True)
                except GameError as e:
                    await out(f"❌ {e}", force_new=True)
                except Exception as e:
                    log.exception("open player profile ng:ou tid=%s", data)
                    await out(f"❌ خطا در باز کردن پروفایل: {e}", force_new=True)
                return


            if data.startswith("ng:oureset:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT * FROM ng_players WHERE player_id=$1", (tid,))
                if not p:
                    await out("بازیکن یافت نشد")
                    return
                code = p.get("country_code")
                cname = await game.country_label(code) if code else "بدون کشور"
                rows = [
                    [("✅ تأیید ریست", f"ng:ouresetgo:{tid}"), ("❌ انصراف", f"ng:ou:{tid}")],
                ]
                text = (
                    f"آیا مطمئن هستید؟\n\nکاربر: {tid}\nکشور: {cname}\n\n"
                    "با ریست کردن این کاربر:\n"
                    "• کشور فعلی او آزاد می‌شود.\n"
                    "• مالکیت کشور حذف می‌شود.\n"
                    "• دارایی‌ها و پیشرفت کشور بازنشانی می‌شود.\n"
                    "• کاربر بدون کشور از ابتدا شروع می‌کند.\n"
                    "• بن بودن تغییر نمی‌کند.\n"
                    "• لاگ‌ها و سوابق مالی حفظ می‌شوند.\n\n"
                    "این عملیات قابل بازگشت نیست."
                )
                await out(text, ik(rows))
                return
            if data.startswith("ng:ouresetgo:"):
                try:
                    tid = int(data.split(":")[-1])
                except Exception:
                    await out("❌ شناسه نامعتبر", force_new=True)
                    return
                try:
                    msg = await game.reset_player(pid, tid)
                    await out(
                        msg,
                        ik([[("👤 بازیکنان", "ng:ousers")], [("🏠 خانه", "ng:home")]]),
                        force_new=True,
                    )
                except GameError as e:
                    await out(f"❌ {e}", force_new=True)
                except Exception as e:
                    log.exception("ouresetgo")
                    await out(f"❌ خطا در ریست کاربر: {e}", force_new=True)
                return

            if data.startswith("ng:ouban:"):
                if not owner:
                    await out("❌ فقط مالک")
                    return
                try:
                    tid = int(data.split(":")[-1])
                except Exception:
                    await out("❌ شناسه نامعتبر")
                    return
                # auto ban code; ask duration first
                import time as _time
                auto_code = str(int(_time.time()) % 1000000)
                while await game.is_ban_code_taken(auto_code):
                    auto_code = str((int(auto_code) + 1) % 1000000)
                await _set_pending(
                    game, pid, "ban_wizard_duration",
                    target=tid, ban_code=auto_code,
                )
                await out(
                    f"🚫 بن کاربر {tid}\n\n"
                    f"کد بن خودکار: #{auto_code}\n\n"
                    "چند روز بن باشد؟\nعدد روز را بفرست یا بنویس: دائم",
                    ik([cancel_row()]),
                )
                return
            if data.startswith("ng:ouunban:"):
                tid = int(data.split(":")[-1])
                try:
                    await out(await game.unban(pid, tid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:ouinv:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                await out(await game.inventory_text(code))
                return
            if data.startswith("ng:oum:"):
                tid = int(data.split(":")[-1])
                code = await game.resolve_country_for_player(tid)
                if not code:
                    await out("کشور نامشخص / مالکیت هم‌خوان نیست")
                    return
                c = await game.db.fetchrow(
                    "SELECT treasury, currency_name_fa, owner_player_id FROM ng_countries WHERE country_code=$1",
                    (code,),
                )
                cname = await game.country_label(code)
                await out(
                    f"💰 موجودی {cname}\nکد: {code}\nمالک: {c.get('owner_player_id')}\n"
                    f"خزانه: {int(float(c['treasury'])):,} {c.get('currency_name_fa') or ''}"
                )
                return
            if data.startswith("ng:ounpt:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                c = await game.db.fetchrow("SELECT npt_member, name_fa FROM ng_countries WHERE country_code=$1", (code,))
                st = "عضو" if int(c["npt_member"]) else "غیرعضو"
                await out(f"NPT — {c['name_fa']}: {st}")
                return
            if data.startswith("ng:ounptadd:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                try:
                    await out(await game.admin_set_npt(pid, code, True))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:ounptdel:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                try:
                    await out(await game.admin_set_npt(pid, code, False))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:ougive:"):
                tid = int(data.split(":")[-1])
                code = await game.resolve_country_for_player(tid)
                if not code:
                    await out("این کاربر کشور معتبری ندارد؛ اول باید کشور انتخاب کند.")
                    return
                c = await game.db.fetchrow(
                    "SELECT treasury, name_fa, currency_name_fa, owner_player_id FROM ng_countries WHERE country_code=$1",
                    (code,),
                )
                _pending[pid] = {"kind": "user_give_money", "code": code, "tid": tid}
                await out(
                    f"💵 افزودن پول به {(c or {}).get('name_fa') or code}\n"
                    f"موجودی فعلی: {int(float((c or {}).get('treasury') or 0)):,}\n\n"
                    f"مبلغ را به عدد بنویسید (مثال: 5000000):",
                    ik([cancel_row()]),
                )
                return
            if data.startswith("ng:outake:"):
                tid = int(data.split(":")[-1])
                code = await game.resolve_country_for_player(tid)
                if not code:
                    await out("این کاربر کشور معتبری ندارد.")
                    return
                c = await game.db.fetchrow(
                    "SELECT treasury, name_fa, owner_player_id FROM ng_countries WHERE country_code=$1", (code,)
                )
                _pending[pid] = {"kind": "user_take_money", "code": code, "tid": tid}
                await out(
                    f"💸 برداشت از {(c or {}).get('name_fa') or code}\n"
                    f"موجودی فعلی: {int(float((c or {}).get('treasury') or 0)):,}\n\n"
                    f"مبلغ برداشت را بنویسید:",
                    ik([cancel_row()]),
                )
                return
            if data.startswith("ng:outax:"):
                tid = int(data.split(":")[-1])
                p = await game.db.fetchrow("SELECT country_code FROM ng_players WHERE player_id=$1", (tid,))
                code = (p or {}).get("country_code")
                if not code:
                    await out("کشور نامشخص")
                    return
                _pending[pid] = {"kind": "user_tax", "code": code}
                await out("مبلغ مالیات اختصاصی را بنویسید:")
                return

            if data == "ng:otax":
                _pending[pid] = {"kind": "global_tax_amount"}
                await out("لطفاً مبلغ مالیات را به عدد وارد کنید:\nمثال: 10000")
                return
            if data == "ng:ocondemn":
                countries = [c for c in await game.list_countries(for_owner=True) if c.get("country_code") != "UN"]
                rows = [[(f"{c.get('flag','')} {c['name_fa']}", f"ng:ocondemn:{c['country_code']}")] for c in countries]
                rows.append(back_row())
                await out("کشور هدف محکومیت را انتخاب کنید:", ik(rows))
                return
            if data.startswith("ng:ocondemn:"):
                code = data.split(":")[-1]
                _pending[pid] = {"kind": "condemn_speech", "code": code}
                await out("لطفاً متن سخنرانی سازمان ملل را بنویسید:")
                return

            if data == "ng:otest":
                active = await game.is_test_mode(pid)
                rows = [
                    [("🟢 فعال‌سازی تست", "ng:otest:on") if not active else ("🔴 خاموش کردن تست", "ng:otest:off")],
                    back_row(),
                ]
                await out(f"🧪 حساب تستی: {'فعال' if active else 'خاموش'}", ik(rows))
                return
            if data == "ng:otest:on":
                try:
                    await out(await game.enable_test_mode(pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:otest:off":
                try:
                    await out(await game.disable_test_mode(pid))
                except GameError as e:
                    await out(f"❌ {e}")
                return

            if data == "ng:oforce":
                if not owner:
                    await out("❌ فقط مالک")
                    return
                enabled = await game.membership_enabled()
                chats = await game.list_forced_chats()
                lines = [
                    "⚙️ عضویت اجباری",
                    f"وضعیت: {'🟢 فعال' if enabled else '🔴 خاموش'}",
                    "",
                    "فهرست گروه/کانال‌ها:",
                ]
                if not chats:
                    lines.append("— موردی ثبت نشده —")
                for c in chats:
                    kind_fa = "کانال" if str(c.get("kind")) == "channel" else "گروه"
                    st = "🟢" if int(c.get("active") or 0) else "🔴"
                    lines.append(
                        f"{st} #{c['id']} | {c.get('title') or '-'} | {kind_fa} | {c.get('chat_id')}"
                    )
                lines.append("")
                lines.append("برای افزودن: ربات باید عضو و ادمین گروه/کانال باشد.")
                rows = [
                    [("🟢 فعال", "ng:oforce:on"), ("🔴 خاموش", "ng:oforce:off")],
                    [("➕ افزودن گروه/کانال", "ng:oforce:add")],
                    [("➕ افزودن @warworld3", "ng:oforce:adddefault")],
                ]
                for c in chats:
                    label = f"🗑 حذف #{c['id']} {c.get('title') or c.get('chat_id')}"
                    rows.append([(label[:60], f"ng:oforce:del:{c['id']}")])
                rows.append(back_row())
                await out("\n".join(lines), ik(rows), force_new=True)
                return
            if data == "ng:oforce:on":
                if not owner:
                    await out("❌ فقط مالک")
                    return
                await out(await game.set_membership_enabled(pid, True))
                return
            if data == "ng:oforce:off":
                if not owner:
                    await out("❌ فقط مالک")
                    return
                await out(await game.set_membership_enabled(pid, False))
                return
            if data == "ng:oforce:add":
                if not owner:
                    await out("❌ فقط مالک")
                    return
                await _set_pending(game, pid, "force_add_chat")
                await out(
                    "➕ افزودن گروه یا کانال به عضویت اجباری\n\n"
                    "شرایط:\n"
                    "• ربات باید در گروه/کانال عضو باشد\n"
                    "• ربات باید ادمین باشد\n"
                    "• هم گروه و هم کانال پشتیبانی می‌شود\n\n"
                    "آیدی عددی یا @یوزرنیم را بفرستید:\n"
                    "مثال: @warworld3\n"
                    "مثال: -1001234567890",
                    ik([cancel_row()]),
                    force_new=True,
                )
                return
            if data == "ng:oforce:adddefault":
                if not owner:
                    await out("❌ فقط مالک")
                    return
                try:
                    msg = await game.add_forced_chat(
                        pid, "@warworld3", "WORLD WAR", "https://ble.ir/warworld3", "group", bot=bot
                    )
                    await out(msg)
                except GameError as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:oforce:del:"):
                if not owner:
                    await out("❌ فقط مالک")
                    return
                try:
                    msg = await game.remove_forced_chat(pid, int(data.split(":")[-1]))
                    await out(msg)
                except GameError as e:
                    await out(f"❌ {e}")
                return


            if data == "ng:ohack" or data == "ng:ohack:menu":
                try:
                    txt = await game.hacker.admin_profile_text()
                except Exception as e:
                    log.exception("ohack profile")
                    txt = f"❌ {e}"
                rows = [
                    [("🔄 تازه‌سازی", "ng:ohack")],
                    [("⬆️ تنظیم لول", "ng:ohack:level"), ("⭐ تنظیم XP", "ng:ohack:xp")],
                    [("💰 تنظیم خزانه", "ng:ohack:treasury")],
                    [("🟢 فعال", "ng:ohack:on"), ("🔴 غیرفعال", "ng:ohack:off")],
                    [("⏱ پاک‌کردن کول‌داون", "ng:ohack:cd")],
                    [("⬅️ پنل مالک", "ng:home")],
                ]
                await out(txt, ik(rows))
                return
            if data == "ng:ohack:level":
                _pending[pid] = {"kind": "hacker_admin_level"}
                await out("عدد لول جدید را بفرستید (۱ تا ۵۰):", ik([cancel_row()]))
                return
            if data == "ng:ohack:xp":
                _pending[pid] = {"kind": "hacker_admin_xp"}
                await out("مقدار XP را بفرستید:", ik([cancel_row()]))
                return
            if data == "ng:ohack:treasury":
                _pending[pid] = {"kind": "hacker_admin_treasury"}
                await out("مبلغ خزانه جدید گروه هکری را بفرستید:", ik([cancel_row()]))
                return
            if data == "ng:ohack:on":
                try:
                    await out(await game.hacker.admin_set_active(pid, True), ik([[("🎭 بازگشت", "ng:ohack")]]))
                except Exception as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ohack:off":
                try:
                    await out(await game.hacker.admin_set_active(pid, False), ik([[("🎭 بازگشت", "ng:ohack")]]))
                except Exception as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:ohack:cd":
                try:
                    await out(await game.hacker.admin_clear_cooldowns(pid), ik([[("🎭 بازگشت", "ng:ohack")]]))
                except Exception as e:
                    await out(f"❌ {e}")
                return

            # ---- Anonymous Hacker Group ----
            if data.startswith("ng:hack") or data.startswith("ng:hbuy") or data.startswith("ng:hbuyc") or data.startswith("ng:hbuy5"):
                await out(
                    "سیستم ویژه هکری حذف شده است." + chr(10)
                    + "آنانیموسم مثل بقیه کشورهاست: فروشگاه، حمله، کول‌داون و قوانین جنگ یکسان.",
                    ik([back_row()]),
                    force_new=True,
                )
                return

            if data in ("ng:hack:menu", "ng:hack:home"):
                await out(
                    "🎭 منوی گروه هکری آنانیموس",
                    ik([
                        [("👤 پروفایل", "ng:hack:profile")],
                        [("💰 دزدی از کشورها", "ng:hack:steal"), ("🏦 دزدی از بانک جهانی", "ng:hack:bank")],
                        [("🌍 دیدن کشورها", "ng:hack:countries"), ("📢 بیانیه دادن", "ng:hack:stmt")],
                        [("🛒 فروشگاه (مثل بقیه کشورها)", "ng:shophome")],
                        back_row(),
                    ]),
                )
                return
            if data == "ng:hack:profile":
                try:
                    txt = await game.hacker.profile_text(pid)
                    await out(txt, ik([
                        [("⬆️ لول‌آپ", "ng:hack:lvlup")],
                        [("🔙 بازگشت", "ng:hack:menu")],
                    ]))
                except Exception as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:hack:lvlup":
                try:
                    txt = await game.hacker.levelup_preview(pid)
                    await out(txt, ik([
                        [("✅ تأیید ارتقا", "ng:hack:lvlup:yes")],
                        [("🔙 بازگشت", "ng:hack:profile")],
                    ]))
                except Exception as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:hack:lvlup:yes":
                try:
                    await out(await game.hacker.level_up(pid), ik([[("🔙 پروفایل", "ng:hack:profile")]]))
                except Exception as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:hack:steal":
                try:
                    await game.hacker.assert_owner(pid)
                    countries = [
                        c for c in await game.list_countries()
                        if c.get("owner_player_id") and str(c.get("country_code") or "").upper() != "ANON"
                    ]
                    rows = []
                    for c in countries[:30]:
                        rows.append([(
                            f"{c.get('flag','')} {c.get('name_fa')} | 💰{int(float(c.get('treasury') or 0)):,}",
                            f"ng:hack:stv:{c['country_code']}",
                        )])
                    rows.append([("🔙 بازگشت", "ng:hack:menu")])
                    await out("💰 انتخاب کشور هدف:", ik(rows), force_new=True)
                except Exception as e:
                    await out(f"❌ {e}")
                return
            if data.startswith("ng:hack:stv:"):
                target = data.split(":")[-1]
                c = await game.db.fetchrow("SELECT * FROM ng_countries WHERE country_code=$1", (target,))
                if not c:
                    await out("کشور یافت نشد")
                    return
                inv = await game.db.fetch(
                    "SELECT COUNT(*) AS n FROM ng_inventory WHERE country_code=$1 AND quantity>0",
                    (target,),
                )
                n_eq = int((inv[0]["n"] if inv else 0) or 0)
                hp = float(c.get("hp") or 0)
                mx = float(c.get("max_hp") or 1000) or 1000
                txt = (
                    f"هدف: {c.get('flag','')} {c.get('name_fa')}\n"
                    f"HP: {int(hp)}/{int(mx)} ({int(100*hp/mx)}%)\n"
                    f"خزانه: {int(float(c.get('treasury') or 0)):,}\n"
                    f"تجهیزات (نوع): {n_eq}\n"
                    f"مالک: {c.get('owner_player_id')}"
                )
                await out(txt, ik([
                    [("💰 انجام دزدی", f"ng:hack:do:{target}")],
                    [("🔙 بازگشت", "ng:hack:steal")],
                ]))
                return
            if data.startswith("ng:hack:do:"):
                target = data.split(":")[-1]
                try:
                    msg = await game.hacker.steal_country(pid, target)
                    await out(
                        msg,
                        ik([[("💰 دزدی دوباره", "ng:hack:steal"), ("🔙 منو", "ng:hack:menu")]]),
                        force_new=True,
                    )
                except (HackerError, GameError) as e:
                    await out(f"❌ {e}", ik([[("🔙 منو", "ng:hack:menu")]]), force_new=True)
                except Exception as e:
                    log.exception("hack steal do")
                    await out(f"❌ خطا در دزدی: {e}", force_new=True)
                return

            if data == "ng:hack:stmt":
                try:
                    await game.hacker.assert_owner(pid)
                    _pending[pid] = {"kind": "hacker_statement"}
                    await out("متن بیانیه را بنویسید:", ik([cancel_row()]))
                except Exception as e:
                    await out(f"❌ {e}")
                return
            if data == "ng:hack:shop":
                # Same shared shop as every other country
                try:
                    await game.hacker.assert_owner(pid)
                except Exception as e:
                    await out(f"❌ {e}", force_new=True)
                    return
                cats = {}
                for it in (game._cat or {}).values():
                    cats[it.get("category") or "other"] = cats.get(it.get("category") or "other", 0) + 1
                rows = []
                pair = []
                for cat, n in list(cats.items())[:12]:
                    name = {
                        "ground": "زمینی", "air": "هوایی", "sea": "دریایی", "missile": "موشکی",
                        "defense": "پدافند", "infra": "زیرساخت", "nuclear": "هسته‌ای", "mine": "منابع",
                        "cyber": "هک و امنیت",
                    }.get(cat, cat)
                    pair.append((f"{name} ({n})", f"ng:shop:{cat}"))
                    if len(pair) == 2:
                        rows.append(pair)
                        pair = []
                if pair:
                    rows.append(pair)
                rows.append([("🛒 سبد خرید", "ng:cart"), ("✅ تسویه حساب", "ng:checkout")])
                rows.append([("🔙 منوی هکری", "ng:hack:menu")])
                rows.append(back_row())
                await out(
                    "🛒 فروشگاه (مشترک با همه کشورها)" + chr(10) + chr(10)
                    + "دسته را انتخاب کنید، به سبد اضافه کنید، سپس تسویه حساب.",
                    ik(rows),
                    force_new=True,
                )
                return

            if data.startswith("ng:hack:sc:"):
                cat = data.split(":")[-1]
                items = [
                    it for it in (game._cat or {}).values()
                    if str(it.get("category") or "") == cat
                ]
                rows = []
                for it in items[:25]:
                    rows.append([(
                        f"{it.get('name_fa') or it.get('item_code')} | {int(float(it.get('unit_price') or 0)):,}",
                        f"ng:item:{it.get('item_code')}",
                    )])
                rows.append([("🛒 سبد", "ng:cart"), ("⬅️ دسته‌ها", "ng:shophome")])
                rows.append([("🔙 منوی هکری", "ng:hack:menu")])
                rows.append(back_row())
                name = {
                    "ground": "زمینی", "air": "هوایی", "sea": "دریایی", "missile": "موشکی",
                    "defense": "پدافند", "infra": "زیرساخت", "nuclear": "هسته‌ای", "mine": "منابع",
                }.get(cat, cat)
                await out(f"🛒 فروشگاه — {name}" + chr(10) + "آیتم را انتخاب کنید:", ik(rows), force_new=True)
                return

            if data.startswith("ng:hbuyc:") or data.startswith("ng:hbuy:") or data.startswith("ng:hack:item:") or data.startswith("ng:buy:"):
                try:
                    await game.hacker.assert_owner(pid)
                    raw = data.split(":")[-1]
                    ic = None
                    qty = 1.0
                    # direct code: ng:hbuyc:ITEM_CODE
                    if data.startswith("ng:hbuyc:"):
                        ic = data.split(":", 2)[-1].strip()
                    # indexed buy: ng:hbuy:3
                    elif data.startswith("ng:hbuy:") and raw.isdigit():
                        codes = _hacker_shop_cache.get(int(pid)) or []
                        idx = int(raw)
                        if 0 <= idx < len(codes):
                            ic = codes[idx]
                        else:
                            await out(
                                "لیست فروشگاه منقضی شده. دوباره دسته را باز کنید.",
                                ik([[("🚀 فروشگاه", "ng:hack:shop")]]),
                                force_new=True,
                            )
                            return
                    else:
                        parts = data.split(":")
                        if parts[-1].isdigit() and len(parts) >= 4:
                            qty = float(parts[-1])
                            ic = parts[-2]
                        else:
                            ic = raw
                    if not ic:
                        await out("❌ کد آیتم نامعتبر", force_new=True)
                        return
                    msg = await game.hacker.buy_item(pid, ic, qty)
                    rows = [
                        [("＋۱ دوباره", f"ng:hbuyc:{ic}"), ("＋۵", f"ng:hbuy5c:{ic}")],
                        [("🚀 ادامه خرید", "ng:hack:shop"), ("👤 منو هکر", "ng:hack:menu")],
                    ]
                    await out(msg, ik(rows), force_new=True)
                except (GameError, HackerError) as e:
                    await out(f"❌ {e}", ik([[("🚀 فروشگاه", "ng:hack:shop")]]), force_new=True)
                except Exception as e:
                    log.exception("hacker buy")
                    await out(f"❌ خطا در خرید: {e}", ik([[("🚀 فروشگاه", "ng:hack:shop")]]), force_new=True)
                return

            if data.startswith("ng:hbuy5c:") or data.startswith("ng:hbuy5:"):
                try:
                    await game.hacker.assert_owner(pid)
                    raw = data.split(":")[-1]
                    ic = None
                    if data.startswith("ng:hbuy5c:"):
                        ic = data.split(":", 2)[-1].strip()
                    elif raw.isdigit():
                        codes = _hacker_shop_cache.get(int(pid)) or []
                        idx = int(raw)
                        if 0 <= idx < len(codes):
                            ic = codes[idx]
                    else:
                        ic = raw
                    if not ic:
                        await out("لیست فروشگاه منقضی شده. دوباره باز کنید.", force_new=True)
                        return
                    msg = await game.hacker.buy_item(pid, ic, 5.0)
                    await out(msg, ik([[("🚀 فروشگاه", "ng:hack:shop")]]), force_new=True)
                except Exception as e:
                    log.exception("hbuy5")
                    await out(f"❌ {e}", force_new=True)
                return

            if data == "ng:hack:bank":
                try:
                    await game.hacker.assert_owner(pid)
                    txt = await game.hacker.bank_info(pid)
                    rows = [
                        [("✅ اجرای دزدی بانک جهانی", "ng:hack:bankgo")],
                        [("🔙 بازگشت", "ng:hack:menu")],
                    ]
                    await out(txt, ik(rows), force_new=True)
                except Exception as e:
                    log.exception("hack bank info")
                    await out(f"❌ {e}", force_new=True)
                return

            if data == "ng:hack:bankgo":
                try:
                    await game.hacker.assert_owner(pid)
                    msg = await game.hacker.bank_heist(pid)
                    await out(
                        msg,
                        ik([
                            [("🏦 دوباره", "ng:hack:bankgo")],
                            [("🔙 منو هکر", "ng:hack:menu")],
                        ]),
                        force_new=True,
                    )
                except (HackerError, GameError) as e:
                    await out(f"❌ {e}", ik([[("🔙 منو", "ng:hack:menu")]]), force_new=True)
                except Exception as e:
                    log.exception("hack bankgo")
                    await out(f"❌ خطا در دزدی بانک: {e}", force_new=True)
                return

                        # Fallback: never fail silently
            log.warning("unhandled callback data=%s pid=%s", (data or "")[:80], pid)
            try:
                await out(
                    "این دکمه پیدا نشد یا منقضی شده است."
                    + chr(10)
                    + "از منوی اصلی دوباره وارد شوید.",
                    ik([back_row(), [("🏠 خانه", "ng:home")]]),
                )
            except Exception:
                pass

        except Exception:
            log.exception("on_callback")
