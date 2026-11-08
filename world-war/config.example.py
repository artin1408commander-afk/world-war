# =============================================================================
# WORLD WAR — local configuration example
# Copy to config.py (gitignored) for Termux/local runs.
# On Railway: set the same names as environment variables — do not commit secrets.
# =============================================================================

# --- Bot (required) ---
BALE_TOKEN = "YOUR_BALE_BOT_TOKEN"
# BOT_TOKEN = ""  # optional alias for BALE_TOKEN
OWNER_ID = 1967315238
# ADMIN_IDS = "123,456"  # optional extra admin numeric IDs (comma-separated)

BOT_USERNAME = ""
BOT_NAME = "WORLD WAR"
SUPPORT_USERNAME = ""
MAIN_GROUP = "@warworld3"

# --- Database (PostgreSQL ONLY — Railway) ---
# Runtime never uses SQLite. DATABASE_URL is required.
# Prefer setting DATABASE_URL in Railway environment variables.
DATABASE_MODE = "postgres"
DATABASE_URL = ""  # e.g. postgresql://user:pass@host:5432/railway
# SQLITE_PATH is ignored at runtime (offline migration tools only)
SQLITE_PATH = ""

# Discrete Postgres parts (used only if DATABASE_URL is empty)
POSTGRES_HOST = ""
POSTGRES_PORT = "5432"
POSTGRES_DB = ""
POSTGRES_USER = ""
POSTGRES_PASSWORD = ""
POSTGRES_SSLMODE = ""

DATABASE_POOL_MIN_SIZE = 1
DATABASE_POOL_MAX_SIZE = 10
DATABASE_CONNECT_TIMEOUT = 30
DATABASE_COMMAND_TIMEOUT = 60
DATABASE_STATEMENT_TIMEOUT_MS = 0

# --- Runtime / Railway ---
LOG_LEVEL = "INFO"
PORT = 8080
PYTHONUNBUFFERED = "1"
MISE_PYTHON_GITHUB_ATTESTATIONS = "false"

# --- World time (from original settings) ---
WORLD_START_DATE = "2020-01-01"
REAL_DAYS_PER_GAME_YEAR = 15

# --- Combat / economy (defaults recovered from modules/ng/game.py) ---
ATTACK_COOLDOWN_SEC = 120
CYBER_HACK_COOLDOWN_SEC = 180
DAILY_INCOME_BASE = 20000000
UN_STARTING_TREASURY = 200000000
MAX_LOOT_ABS = 2000000
REF_INVITEE_REWARD = 30000000
REF_REFERRER_REWARD = 30000000
BOMB_MONEY_COST = 15000000

# --- Workshop ---
WS_UPGRADE_BASE = 2000000
WS_URANIUM_BASE_COST = 500000
WS_URANIUM_BASE_AMOUNT = 10
WS_URANIUM_BASE_MINUTES = 30
WS_RESEARCH_BASE_COST = 800000
WS_RESEARCH_BASE_POINTS = 1
WS_RESEARCH_BASE_MINUTES = 45

# --- Alliances (defaults from modules/ng/alliances.py) ---
ALLIANCE_BASE_CREATE_COST = 2000000
ALLIANCE_COST_PER_EXTRA_MEMBER = 200000
ALLIANCE_COST_PER_100M_TREASURY = 150000
ALLIANCE_BASE_MEMBER_SLOTS = 2
ALLIANCE_BASE_TREASURY_CAP = 100000000
ALLIANCE_MIN_MEMBERS = 2
ALLIANCE_MAX_MEMBERS = 20
ALLIANCE_MIN_TREASURY_CAP = 50000000
ALLIANCE_MAX_TREASURY_CAP = 5000000000
ALLIANCE_MAX_CREATE_COST = 7000000
ALLIANCE_RENAME_COST = 5000000
ALLIANCE_BETRAYAL_WINDOW_SEC = 10800
ALLIANCE_BETRAYAL_PENALTY_SEC = 21600
ALLIANCE_DESTROY_WAIT_SEC = 1800

# --- Donations (defaults from modules/ng/donations.py) ---
DONATION_MAX_REQUESTS_PER_DAY = 3
DONATION_COOLDOWN_HOURS = 3
DONATION_MIN_AMOUNT = 1000
