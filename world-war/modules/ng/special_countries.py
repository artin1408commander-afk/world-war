"""Restricted / personalized playable countries (not generic groups)."""
from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

# Iran (Pahlavi government) — only one player may claim it
PAHLAVI_CODE = "IRP"
PAHLAVI_NAME_FA = "ایران(حکومت پهلوی)"
PAHLAVI_NAME_EN = "Iran (Pahlavi)"
PAHLAVI_FLAG = "🦁"
PAHLAVI_ALLOWED_PID = 1775019829
PAHLAVI_ENTITY = "special"  # shown in personalized section; behaves like a normal country

# registry for future personalized countries
PERSONALIZED: dict[str, dict[str, Any]] = {
    PAHLAVI_CODE: {
        "code": PAHLAVI_CODE,
        "name_fa": PAHLAVI_NAME_FA,
        "name_en": PAHLAVI_NAME_EN,
        "flag": PAHLAVI_FLAG,
        "allowed_pid": PAHLAVI_ALLOWED_PID,
        "entity_type": PAHLAVI_ENTITY,
        "capital_fa": "تهران",
        "leader_fa": "محمدرضا پهلوی",
        "leader_title_fa": "شاه",
        "currency_code": "IRR",
        "currency_name_fa": "تومان",
        "npt": 1,
    },
}


def is_personalized_code(code: str | None) -> bool:
    return (code or "").upper() in PERSONALIZED


def allowed_pid_for(code: str | None) -> Optional[int]:
    meta = PERSONALIZED.get((code or "").upper())
    if not meta:
        return None
    try:
        return int(meta["allowed_pid"])
    except Exception:
        return None


def can_claim_personalized(code: str, pid: int) -> bool:
    allowed = allowed_pid_for(code)
    if allowed is None:
        return True
    return int(pid) == int(allowed)


async def ensure_personalized_countries(db) -> None:
    """Insert missing personalized countries without resetting ownership/treasury."""
    for code, meta in PERSONALIZED.items():
        try:
            row = await db.fetchrow(
                "SELECT country_code, owner_player_id FROM ng_countries WHERE country_code=$1",
                (code,),
            )
            if not row:
                await db.execute(
                    """
                    INSERT INTO ng_countries (
                        country_code, name_fa, name_en, flag, capital_fa, leader_fa, leader_title_fa,
                        currency_code, currency_name_fa, npt_member, owner_player_id, treasury,
                        hp, max_hp, is_destroyed, entity_type
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NULL,0,1000,1000,0,$11)
                    """,
                    (
                        meta["code"],
                        meta["name_fa"],
                        meta["name_en"],
                        meta["flag"],
                        meta["capital_fa"],
                        meta["leader_fa"],
                        meta["leader_title_fa"],
                        meta["currency_code"],
                        meta["currency_name_fa"],
                        int(meta.get("npt") or 1),
                        meta["entity_type"],
                    ),
                )
                log.info("seeded personalized country %s", code)
            else:
                # keep ownership/treasury; only refresh display fields + entity_type
                await db.execute(
                    """
                    UPDATE ng_countries
                    SET name_fa=$1, name_en=$2, flag=$3, entity_type=$4,
                        capital_fa=COALESCE(NULLIF(capital_fa,''), $5),
                        leader_fa=COALESCE(NULLIF(leader_fa,''), $6),
                        leader_title_fa=COALESCE(NULLIF(leader_title_fa,''), $7),
                        currency_code=COALESCE(NULLIF(currency_code,''), $8),
                        currency_name_fa=COALESCE(NULLIF(currency_name_fa,''), $9)
                    WHERE country_code=$10
                    """,
                    (
                        meta["name_fa"],
                        meta["name_en"],
                        meta["flag"],
                        meta["entity_type"],
                        meta["capital_fa"],
                        meta["leader_fa"],
                        meta["leader_title_fa"],
                        meta["currency_code"],
                        meta["currency_name_fa"],
                        code,
                    ),
                )
        except Exception:
            log.exception("ensure personalized %s", code)
