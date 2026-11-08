# Copy to config.py for local/Termux only. Do NOT commit config.py.
# On Railway, set environment variables instead of using this file.

BALE_TOKEN = "YOUR_BALE_BOT_TOKEN"
OWNER_ID = 1967315238

# sqlite | postgres
# If DATABASE_URL is set and DATABASE_MODE is empty, postgres is used automatically.
DATABASE_MODE = "sqlite"
DATABASE_URL = ""

# Optional SQLite path (Railway volume example: /data/world_war.db)
# SQLITE_PATH = ""

LOG_LEVEL = "INFO"
