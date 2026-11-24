"""Reusable 30-second interactive menu session timeout + ownership."""
from __future__ import annotations

import time
from typing import Any

DEFAULT_TTL = 30.0


class MenuSessionStore:
    """Tracks last interaction per (player_id, message_id) menu."""

    def __init__(self, ttl: float = DEFAULT_TTL):
        self.ttl = float(ttl)
        self._sessions: dict[tuple[int, int], dict[str, Any]] = {}
        self._owner_by_message: dict[int, int] = {}

    def touch(self, pid: int, message_id: int | None, meta: dict | None = None) -> None:
        if message_id is None:
            return
        mid = int(message_id)
        pid = int(pid)
        key = (pid, mid)
        prev = self._sessions.get(key) or {}
        data = dict(prev)
        if meta:
            data.update(meta)
        data["ts"] = time.time()
        data["pid"] = pid
        data["message_id"] = mid
        self._sessions[key] = data
        self._owner_by_message[mid] = pid

    def is_alive(self, pid: int, message_id: int | None) -> bool:
        if message_id is None:
            return True
        key = (int(pid), int(message_id))
        s = self._sessions.get(key)
        if not s:
            return False
        if int(s.get("pid") or 0) != int(pid):
            return False
        return (time.time() - float(s.get("ts") or 0)) <= self.ttl

    def owned_by(self, pid: int, message_id: int | None) -> bool:
        if message_id is None:
            return True
        owner = self._owner_by_message.get(int(message_id))
        if owner is None:
            return True  # unclaimed — first interaction may claim
        return int(owner) == int(pid)

    def expire(self, pid: int, message_id: int | None) -> None:
        if message_id is None:
            return
        mid = int(message_id)
        self._sessions.pop((int(pid), mid), None)
        if self._owner_by_message.get(mid) == int(pid):
            self._owner_by_message.pop(mid, None)

    def cleanup(self) -> int:
        now = time.time()
        dead = [k for k, v in self._sessions.items() if now - float(v.get("ts") or 0) > self.ttl]
        for k in dead:
            self._sessions.pop(k, None)
            mid = k[1]
            if self._owner_by_message.get(mid) == k[0]:
                self._owner_by_message.pop(mid, None)
        return len(dead)


MENU_SESSIONS = MenuSessionStore(DEFAULT_TTL)
EXPIRED_MENU_TEXT = "⌛ این منو به دلیل عدم فعالیت به مدت ۳۰ ثانیه بسته شد."
FORBIDDEN_MENU_TEXT = "⛔ این منو متعلق به شما نیست."
