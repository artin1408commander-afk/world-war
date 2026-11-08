-- Donations, co-owners, destroy recovery snapshots, player cash (additive)

CREATE TABLE IF NOT EXISTS ng_donations (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL,
    username TEXT,
    display_name TEXT,
    amount REAL NOT NULL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewed_by INTEGER,
    show_name INTEGER NOT NULL DEFAULT 1,
    method TEXT DEFAULT 'card'
);

CREATE TABLE IF NOT EXISTS ng_donation_limits (
    player_id INTEGER PRIMARY KEY,
    cooldown_until TEXT,
    day_key TEXT,
    day_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ng_extra_owners (
    player_id INTEGER PRIMARY KEY,
    un_code TEXT NOT NULL UNIQUE,
    added_by INTEGER,
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ng_destroy_snapshots (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL,
    country_code TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    destroyed_at TEXT NOT NULL,
    recoverable_until TEXT NOT NULL,
    recovered INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ng_defense_hits (
    country_code TEXT NOT NULL,
    item_code TEXT NOT NULL,
    hits INTEGER NOT NULL DEFAULT 0,
    max_hits INTEGER NOT NULL DEFAULT 30,
    PRIMARY KEY (country_code, item_code)
);

CREATE TABLE IF NOT EXISTS ng_finance_ops (
    id INTEGER PRIMARY KEY,
    op_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
