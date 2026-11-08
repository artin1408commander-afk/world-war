# WORLD WAR

## Database policy (mandatory)

**Railway PostgreSQL is the only permanent data store at runtime.**

- `DATABASE_URL` is required (environment variable preferred).
- SQLite is **not** used when the bot runs.
- There is **no** automatic fallback to local files or JSON.
- Offline migration helper: `tools/migrate_sqlite_to_postgres.py`


**Repository (canonical):** https://github.com/artin1408commander-afk/world-war

Application root inside the repo: **`world-war/`**

| محیط | مسیر |
|------|------|
| GitHub | `artin1408commander-afk/world-war` |
| کد بازی | `world-war/` (Root Directory در Railway) |
| SQLite روی اندروید | `/storage/emulated/0/worldwarbot/DB/world_war.db` |
| PostgreSQL | فقط با `DATABASE_URL` روی Railway |

```bash
git clone https://github.com/artin1408commander-afk/world-war.git
cd world-war/world-war
cp config.example.py config.py
pip install -r requirements.txt
python main.py
```

---

# WORLD WAR — Railway deployment

## Root Directory
Set Railway **Root Directory** to: `world-war`

## Start command
`python main.py` (also in `Procfile` / `railway.toml`)

## Required environment variables
| Variable | Required | Description |
|----------|----------|-------------|
| `BALE_TOKEN` | yes | Bale bot token (never commit) |
| `OWNER_ID` | yes | Primary owner numeric ID |
| `DATABASE_URL` | yes on Railway | Railway PostgreSQL URL |
| `DATABASE_MODE` | optional | `postgres` or `sqlite` (auto: postgres if `DATABASE_URL` set) |
| `MISE_PYTHON_GITHUB_ATTESTATIONS` | recommended | set to `false` |
| `LOG_LEVEL` | optional | default `INFO` |
| `SQLITE_PATH` | optional | only if using SQLite on a volume |

## Security
- `config.py` is **gitignored**. Use `config.example.py` locally.
- Never put real tokens in git.
- Revoke any token that was previously committed.

## Database
- **PostgreSQL**: primary production backend when `DATABASE_URL` is set.
- **SQLite**: local Termux / optional volume via `SQLITE_PATH`.
- Schema is applied from `database/migrations/*.sql` on startup, then module `ensure_tables()`.

## Local Termux
```bash
cd world-war
cp config.example.py config.py   # put your token only here
pip install -r requirements.txt
python main.py
```

---

# WORLD WAR

Multiplayer geopolitical & country-management simulation bot for **Bale**.

- Shared world on **Railway + PostgreSQL**
- Local world on **Android / Pydroid3 + SQLite**
- Explicit `DATABASE_MODE` — **no silent fallback**

## Game clock

- Epoch: **2020-01-01**
- **15 real days = 1 in-game year**
- Server-authoritative (`world_state` table)

## Setup

### Local / Termux (still needs PostgreSQL URL)

```bash
pip install -r requirements.txt
cp .env.example .env
# BALE_TOKEN=...
# DATABASE_MODE=postgres
# DATABASE_URL=postgresql://...
python main.py
```

Requires `DATABASE_URL` pointing at PostgreSQL (no local SQLite runtime).

### Railway + PostgreSQL

1. Create Railway project + PostgreSQL plugin.
2. Set env:
   - `DATABASE_MODE=postgres`
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`
   - `BALE_TOKEN=...`
3. Deploy from this repo (`Procfile` worker).

If PostgreSQL is unreachable, the process **exits with error** (does not switch to SQLite).

## Tests

```bash
pip install pytest aiosqlite
pytest -q
```

## Structure

See `bot/`, `engine/`, `database/`, `modules/` for modular layout.

## License

Private / project license TBD by owner.

## Configuration priority

1. Environment variables (`BALE_TOKEN`, `OWNER_ID`, `DATABASE_MODE`, `DATABASE_URL`, ...)
2. Local `config.py` in project root (for Pydroid3 / manual runs)

`config.example.py` shows the shape of `config.py`.

Never log the bot token.

## New Generation (نسل جدید)

نقطه ورود: `python main.py`

- بدون کشور هوش مصنوعی؛ فقط بازیکن واقعی
- انتخاب اتمیک کشور + سرمایه اولیه متعادل ۵۰–۱۰۰ میلیون
- فروشگاه، سبد، انبار، بازار، کمک مالی، صلح، جنگ انتزاعی
- درآمد روزانه ساعت‌به‌ساعت بررسی می‌شود (تقویم تهران، یک‌بار در روز)
- پنل مالک: جنگ باز/بسته، هسته‌ای بازی، بیانیه، ریست کامل
- گروه لاگ هدف: `@warworld3` (نیازمند عضویت ربات)

`config.py` محلی (gitignore) یا env: `BALE_TOKEN`, `OWNER_ID`, `DATABASE_MODE`, `DATABASE_URL`


## Complete configuration

All runtime options live in:
- `config/settings.py` (loader)
- `config.example.py` / `.env.example` (documented names)

Environment variables override `config.py`. See `.env.example` for the full list including economy, alliances, donations, and PostgreSQL pool settings.
