# Railway setup (WORLD WAR)

## Required variables (Dashboard → Variables)

Set these on the **bot service** (not only Postgres):

| Name | Value |
|------|--------|
| `BALE_TOKEN` | your Bale bot token |
| `OWNER_ID` | `1967315238` |
| `DATABASE_URL` | from Railway Postgres plugin (`${{Postgres.DATABASE_URL}}`) |
| `DATABASE_MODE` | `postgres` |

## Root Directory

`world-war`

## Start command

`python main.py`

## Important

- Do **not** commit `config.py` (it is gitignored).
- `*.railway.internal` hostnames work **only inside Railway**.
- For Termux/local you need the **public** Postgres URL from Railway (not `.internal`).
- Link the Postgres service to the bot so `DATABASE_URL` is injected automatically.

## After deploy

1. Redeploy the bot service.
2. Check logs for: `PostgreSQL pool ready` and `DATABASE_BACKEND=postgresql`.
3. If connection fails, copy the public `DATABASE_URL` from the Postgres service variables.
