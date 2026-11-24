"""Reusable 30-second interactive menu session timeout."""
from __future__ import annotations

import time
from typing import Any

DEFAULT_TTL = 30.0


class MenuSessionStore:
    """Tracks last interaction per (player_id, message_id) menu."""

    def __init__(self, ttl: float = DEFAULT_TTL):
        self.ttl = float(ttl)
        self._sessions: dict[tuple[int, int], dict[str, Any]] = {}

    def touch(self, pid: int, message_id: int | None, meta: dict | None = None) -> None:
        if message_id is None:
            return
        key = (int(pid), int(message_id))
        prev = self._sessions.get(key) or {}
        data = dict(prev)
        if meta:
            data.update(meta)
        data["ts"] = time.time()
        data["pid"] = int(pid)
        data["message_id"] = int(message_id)
        self._sessions[key] = data

    def is_alive(self, pid: int, message_id: int | None) -> bool:
        if message_id is None:
            return True
        key = (int(pid), int(message_id))
        s = self._sessions.get(key)
        if not s:
            return False
        return (time.time() - float(s.get("ts") or 0)) <= self.ttl

    def expire(self, pid: int, message_id: int | None) -> None:
        if message_id is None:
            return
        self._sessions.pop((int(pid), int(message_id)), None)

    def cleanup(self) -> int:
        now = time.time()
        dead = [k for k, v in self._sessions.items() if now - float(v.get("ts") or 0) > self.ttl]
        for k in dead:
            self._sessions.pop(k, None)
        return len(dead)


MENU_SESSIONS = MenuSessionStore(DEFAULT_TTL)
EXPIRED_MENU_TEXT = "⌛ این منو به دلیل عدم فعالیت به مدت ۳۰ ثانیه بسته شد."
