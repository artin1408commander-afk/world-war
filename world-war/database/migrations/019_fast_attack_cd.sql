-- Per-player 30s attack cooldown flag (owner panel)
-- Compatible with existing ng_player_flags from 018_alliance_system_v2.sql
ALTER TABLE ng_player_flags ADD COLUMN IF NOT EXISTS fast_attack_cd INTEGER NOT NULL DEFAULT 0;
