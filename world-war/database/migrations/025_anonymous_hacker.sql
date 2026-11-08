-- Anonymous Hacker Group (additive, non-destructive)

CREATE TABLE IF NOT EXISTS ng_hacker_groups (
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
);

CREATE TABLE IF NOT EXISTS ng_hacker_ops (
    id INTEGER PRIMARY KEY,
    op_key TEXT NOT NULL UNIQUE,
    country_code TEXT NOT NULL,
    op_type TEXT NOT NULL,
    target_code TEXT,
    amount REAL NOT NULL DEFAULT 0,
    xp_gain INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ng_hacker_tx (
    id INTEGER PRIMARY KEY,
    country_code TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount REAL NOT NULL,
    balance_after REAL NOT NULL,
    meta TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ng_hacker_announcements (
    id INTEGER PRIMARY KEY,
    country_code TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    sent_ok INTEGER NOT NULL DEFAULT 0,
    sent_fail INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
