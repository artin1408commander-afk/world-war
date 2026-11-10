"""Central configuration for WORLD WAR.

Sources (highest priority first):
1. Environment variables (Railway / shell)
2. Optional local config.py (gitignored)
3. Safe defaults recovered from the original project code / history

Never log secrets (tokens, passwords, full DATABASE_URL credentials).
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


def _load_local_config():
    path = ROOT / "config.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("ww_local_config", path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get(local, name: str, default: str = "") -> str:
    env = os.getenv(name)
    if env is not None and str(env).strip() != "":
        return str(env).strip()
    if local is not None and hasattr(local, name):
        val = getattr(local, name)
        if val is None:
            return default
        return str(val).strip()
    return default


def _get_any(local, names: list[str], default: str = "") -> str:
    for n in names:
        v = _get(local, n, "")
        if v != "":
            return v
    return default


def _as_int(raw: str, default: int) -> int:
    if raw is None or str(raw).strip() == "":
        return default
    return int(float(str(raw).strip()))


def _as_float(raw: str, default: float) -> float:
    if raw is None or str(raw).strip() == "":
        return default
    return float(str(raw).strip())


def _as_bool(raw: str, default: bool = False) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _android_storage_root() -> Path | None:
    for c in (Path("/storage/emulated/0"), Path("/sdcard")):
        try:
            if c.exists():
                return c
        except OSError:
            continue
    return None


def _resolve_sqlite_path(explicit: str) -> Path:
    import shutil

    if explicit and str(explicit).strip():
        path = Path(str(explicit).strip())
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    for vol in (Path("/data"), Path("/app/data"), Path("/var/data")):
        try:
            if vol.exists() and vol.is_dir():
                return vol / "world_war.db"
        except OSError:
            continue

    android = _android_storage_root()
    if android is not None:
        db_dir = android / "worldwarbot" / "DB"
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            db_dir = ROOT / "DB"
            db_dir.mkdir(parents=True, exist_ok=True)
        path = db_dir / "world_war.db"
        if not path.is_file():
            for oldp in (
                ROOT / "db" / "world_war.db",
                android / "worldwarbot" / "world-war" / "db" / "world_war.db",
                android / "worldwarbot" / "world-war" / "DB" / "world_war.db",
            ):
                try:
                    if oldp.is_file():
                        shutil.copy2(oldp, path)
                        break
                except OSError:
                    continue
        return path

    db_dir = ROOT / "DB"
    db_dir.mkdir(parents=True, exist_ok=True)
    path = db_dir / "world_war.db"
    legacy = ROOT / "db" / "world_war.db"
    if not path.is_file() and legacy.is_file():
        try:
            shutil.copy2(legacy, path)
        except OSError:
            pass
    return path


def _build_database_url_from_parts(local) -> str:
    """Build postgres DSN from discrete POSTGRES_* vars when DATABASE_URL is empty."""
    host = _get(local, "POSTGRES_HOST", "")
    if not host:
        return ""
    port = _get(local, "POSTGRES_PORT", "5432") or "5432"
    db = _get_any(local, ["POSTGRES_DB", "POSTGRES_DATABASE", "PGDATABASE"], "railway")
    user = _get_any(local, ["POSTGRES_USER", "PGUSER"], "postgres")
    password = _get_any(local, ["POSTGRES_PASSWORD", "PGPASSWORD"], "")
    sslmode = _get(local, "POSTGRES_SSLMODE", "")
    user_q = quote_plus(user)
    pass_q = quote_plus(password) if password else ""
    auth = f"{user_q}:{pass_q}@" if password else f"{user_q}@"
    url = f"postgresql://{auth}{host}:{port}/{db}"
    if sslmode:
        url += f"?sslmode={sslmode}"
    return url


@dataclass(frozen=True)
class Settings:
    # --- Bot ---
    bale_token: str
    owner_id: int
    admin_ids: tuple[int, ...]
    bot_username: str
    bot_name: str
    support_username: str
    main_group: str

    # --- Database ---
    database_mode: str
    database_url: str
    sqlite_path: Path
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    # password never stored in plain Settings for logging; kept only inside database_url
    database_pool_min_size: int
    database_pool_max_size: int
    database_connect_timeout: float
    database_command_timeout: float
    database_statement_timeout_ms: int

    # --- Runtime / Railway ---
    log_level: str
    port: int
    python_unbuffered: bool
    mise_python_github_attestations: str

    # --- World / time ---
    world_start_date: str
    real_days_per_game_year: int

    # --- Combat / economy (recovered from modules/ng/game.py) ---
    attack_cooldown_sec: int
    cyber_hack_cooldown_sec: int
    daily_income_base: float
    un_starting_treasury: float
    max_loot_abs: float
    ref_invitee_reward: float
    ref_referrer_reward: float
    bomb_money_cost: float

    # --- Workshop (recovered from Game class attributes) ---
    ws_upgrade_base: float
    ws_uranium_base_cost: float
    ws_uranium_base_amount: float
    ws_uranium_base_minutes: float
    ws_research_base_cost: float
    ws_research_base_points: float
    ws_research_base_minutes: float

    # --- Alliances (recovered from modules/ng/alliances.py) ---
    alliance_base_create_cost: int
    alliance_cost_per_extra_member: int
    alliance_cost_per_100m_treasury: int
    alliance_base_member_slots: int
    alliance_base_treasury_cap: float
    alliance_min_members: int
    alliance_max_members: int
    alliance_min_treasury_cap: float
    alliance_max_treasury_cap: float
    alliance_max_create_cost: int
    alliance_rename_cost: int
    alliance_betrayal_window_sec: int
    alliance_betrayal_penalty_sec: int
    alliance_destroy_wait_sec: int

    # --- Donations (recovered from modules/ng/donations.py) ---
    donation_max_requests_per_day: int
    donation_cooldown_hours: int
    donation_min_amount: float

    @property
    def is_postgres(self) -> bool:
        return self.database_mode == "postgres"

    @property
    def is_sqlite(self) -> bool:
        # Runtime never uses SQLite
        return False

    def is_admin(self, pid: int) -> bool:
        try:
            pid = int(pid)
        except Exception:
            return False
        if pid == int(self.owner_id):
            return True
        return pid in self.admin_ids


def load_settings() -> Settings:
    local = _load_local_config()

    # Token: BALE_TOKEN preferred; BOT_TOKEN accepted as historical alias
    token = _get_any(local, ["BALE_TOKEN", "BOT_TOKEN"], "")
    if not token:
        raise ValueError(
            "BALE_TOKEN is required. Set environment variable BALE_TOKEN "
            "(or BOT_TOKEN) or create a gitignored config.py from config.example.py."
        )

    owner_id = _as_int(_get(local, "OWNER_ID", "1967315238"), 1967315238)
    if owner_id <= 0:
        raise ValueError("OWNER_ID must be a positive integer.")

    admin_raw = _get_any(local, ["ADMIN_IDS", "ADMIN_ID"], "")
    admin_ids: list[int] = []
    if admin_raw:
        for part in admin_raw.replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                admin_ids.append(int(part))
            except ValueError as exc:
                raise ValueError(f"Invalid ADMIN_IDS entry: {part!r}") from exc

    # Database: PostgreSQL ONLY (Railway). No SQLite runtime fallback.
    db_url = _get(local, "DATABASE_URL", "")
    if not db_url:
        db_url = _build_database_url_from_parts(local)

    mode_raw = _get(local, "DATABASE_MODE", "").lower().strip()
    if mode_raw and mode_raw not in ("postgres", "postgresql", "pg"):
        raise ValueError(
            f"DATABASE_MODE={mode_raw!r} is not supported. "
            "WORLD WAR runtime uses PostgreSQL only. "
            "Set DATABASE_URL (Railway) and omit SQLITE mode."
        )
    mode = "postgres"
    if not db_url:
        raise ValueError(
            "DATABASE_URL is required. Railway PostgreSQL is the only permanent data store. "
            "Set DATABASE_URL in environment variables (preferred) or gitignored config.py. "
            "SQLite/local files are not used at runtime."
        )

    # SQLITE_PATH is ignored at runtime (offline migration tools only)
    sqlite_path = Path(_get(local, "SQLITE_PATH", "") or "") if _get(local, "SQLITE_PATH", "") else Path("")

    return Settings(
        bale_token=token,
        owner_id=owner_id,
        admin_ids=tuple(admin_ids),
        bot_username=_get_any(local, ["BOT_USERNAME", "BOT_USER"], ""),
        bot_name=_get(local, "BOT_NAME", "WORLD WAR") or "WORLD WAR",
        support_username=_get_any(local, ["SUPPORT_USERNAME", "SUPPORT_USER"], ""),
        main_group=_get_any(local, ["MAIN_GROUP", "MAIN_GROUP_ID", "GROUP_ID"], "@warworld3")
        or "@warworld3",
        database_mode=mode,
        database_url=db_url,
        sqlite_path=sqlite_path,
        postgres_host=_get(local, "POSTGRES_HOST", ""),
        postgres_port=_as_int(_get(local, "POSTGRES_PORT", "5432"), 5432),
        postgres_db=_get_any(local, ["POSTGRES_DB", "POSTGRES_DATABASE"], ""),
        postgres_user=_get_any(local, ["POSTGRES_USER", "PGUSER"], ""),
        database_pool_min_size=_as_int(_get(local, "DATABASE_POOL_MIN_SIZE", "1"), 1),
        database_pool_max_size=_as_int(_get(local, "DATABASE_POOL_MAX_SIZE", "10"), 10),
        database_connect_timeout=_as_float(_get(local, "DATABASE_CONNECT_TIMEOUT", "30"), 30.0),
        database_command_timeout=_as_float(
            _get_any(local, ["DATABASE_COMMAND_TIMEOUT", "DATABASE_STATEMENT_TIMEOUT"], "60"),
            60.0,
        ),
        database_statement_timeout_ms=_as_int(
            _get(local, "DATABASE_STATEMENT_TIMEOUT_MS", "0"), 0
        ),
        log_level=(_get(local, "LOG_LEVEL", "INFO") or "INFO").upper(),
        port=_as_int(_get(local, "PORT", "8080"), 8080),
        python_unbuffered=_as_bool(_get(local, "PYTHONUNBUFFERED", "1"), True),
        mise_python_github_attestations=_get(
            local, "MISE_PYTHON_GITHUB_ATTESTATIONS", "false"
        )
        or "false",
        world_start_date=_get(local, "WORLD_START_DATE", "2020-01-01") or "2020-01-01",
        real_days_per_game_year=_as_int(_get(local, "REAL_DAYS_PER_GAME_YEAR", "15"), 15),
        # Game values recovered from source (modules/ng/game.py, alliances.py, donations.py)
        attack_cooldown_sec=_as_int(_get(local, "ATTACK_COOLDOWN_SEC", "120"), 120),
        cyber_hack_cooldown_sec=_as_int(_get(local, "CYBER_HACK_COOLDOWN_SEC", "180"), 180),
        daily_income_base=_as_float(_get(local, "DAILY_INCOME_BASE", "70000000"), 70_000_000.0),
        un_starting_treasury=_as_float(
            _get(local, "UN_STARTING_TREASURY", "200000000"), 200_000_000.0
        ),
        max_loot_abs=_as_float(_get(local, "MAX_LOOT_ABS", "2000000"), 2_000_000.0),
        ref_invitee_reward=_as_float(_get(local, "REF_INVITEE_REWARD", "30000000"), 30_000_000.0),
        ref_referrer_reward=_as_float(
            _get(local, "REF_REFERRER_REWARD", "30000000"), 30_000_000.0
        ),
        bomb_money_cost=_as_float(_get(local, "BOMB_MONEY_COST", "15000000"), 15_000_000.0),
        ws_upgrade_base=_as_float(_get(local, "WS_UPGRADE_BASE", "2000000"), 2_000_000.0),
        ws_uranium_base_cost=_as_float(_get(local, "WS_URANIUM_BASE_COST", "500000"), 500_000.0),
        ws_uranium_base_amount=_as_float(_get(local, "WS_URANIUM_BASE_AMOUNT", "10"), 10.0),
        ws_uranium_base_minutes=_as_float(_get(local, "WS_URANIUM_BASE_MINUTES", "30"), 30.0),
        ws_research_base_cost=_as_float(_get(local, "WS_RESEARCH_BASE_COST", "800000"), 800_000.0),
        ws_research_base_points=_as_float(_get(local, "WS_RESEARCH_BASE_POINTS", "1"), 1.0),
        ws_research_base_minutes=_as_float(
            _get(local, "WS_RESEARCH_BASE_MINUTES", "45"), 45.0
        ),
        alliance_base_create_cost=_as_int(_get(local, "ALLIANCE_BASE_CREATE_COST", "2000000"), 2_000_000),
        alliance_cost_per_extra_member=_as_int(
            _get(local, "ALLIANCE_COST_PER_EXTRA_MEMBER", "200000"), 200_000
        ),
        alliance_cost_per_100m_treasury=_as_int(
            _get(local, "ALLIANCE_COST_PER_100M_TREASURY", "150000"), 150_000
        ),
        alliance_base_member_slots=_as_int(_get(local, "ALLIANCE_BASE_MEMBER_SLOTS", "2"), 2),
        alliance_base_treasury_cap=_as_float(
            _get(local, "ALLIANCE_BASE_TREASURY_CAP", "100000000"), 100_000_000.0
        ),
        alliance_min_members=_as_int(_get(local, "ALLIANCE_MIN_MEMBERS", "2"), 2),
        alliance_max_members=_as_int(_get(local, "ALLIANCE_MAX_MEMBERS", "20"), 20),
        alliance_min_treasury_cap=_as_float(
            _get(local, "ALLIANCE_MIN_TREASURY_CAP", "50000000"), 50_000_000.0
        ),
        alliance_max_treasury_cap=_as_float(
            _get(local, "ALLIANCE_MAX_TREASURY_CAP", "5000000000"), 5_000_000_000.0
        ),
        alliance_max_create_cost=_as_int(_get(local, "ALLIANCE_MAX_CREATE_COST", "7000000"), 7_000_000),
        alliance_rename_cost=_as_int(_get(local, "ALLIANCE_RENAME_COST", "5000000"), 5_000_000),
        alliance_betrayal_window_sec=_as_int(
            _get(local, "ALLIANCE_BETRAYAL_WINDOW_SEC", "10800"), 3 * 3600
        ),
        alliance_betrayal_penalty_sec=_as_int(
            _get(local, "ALLIANCE_BETRAYAL_PENALTY_SEC", "21600"), 6 * 3600
        ),
        alliance_destroy_wait_sec=_as_int(
            _get(local, "ALLIANCE_DESTROY_WAIT_SEC", "1800"), 30 * 60
        ),
        donation_max_requests_per_day=_as_int(
            _get(local, "DONATION_MAX_REQUESTS_PER_DAY", "3"), 3
        ),
        donation_cooldown_hours=_as_int(_get(local, "DONATION_COOLDOWN_HOURS", "3"), 3),
        donation_min_amount=_as_float(_get(local, "DONATION_MIN_AMOUNT", "1000"), 1000.0),
    )
