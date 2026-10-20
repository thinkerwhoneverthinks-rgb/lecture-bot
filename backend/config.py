import os
import logging
from dotenv import load_dotenv

# Load local .env file if available
load_dotenv()

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("forwarder_bot")

# --- Telegram API Credentials ---
API_ID_RAW = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not API_ID_RAW or not API_HASH:
    logger.warning("API_ID or API_HASH not provided in environment! Set them in .env before running.")
    API_ID = 0
    API_HASH = ""
else:
    API_ID = int(API_ID_RAW)
    API_HASH = str(API_HASH)

# --- Bot Tokens ---
MAIN_BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "").strip()

WORKER_BOT_TOKENS_RAW = os.getenv("WORKER_BOT_TOKENS", "").strip()
WORKER_BOT_TOKENS = [
    t.strip() for t in WORKER_BOT_TOKENS_RAW.split(",") if t.strip()
]

# Combined pool for round-robin dispatch: Main token + any worker tokens
ALL_BOT_TOKENS = [MAIN_BOT_TOKEN] + [tok for tok in WORKER_BOT_TOKENS if tok != MAIN_BOT_TOKEN]
ALL_BOT_TOKENS = [t for t in ALL_BOT_TOKENS if t]

# --- Storage Identifiers ---
FORUM_CHAT_ID = int(os.getenv("FORUM_CHAT_ID", "0"))
BACKUP_CHANNEL_ID = int(os.getenv("BACKUP_CHANNEL_ID", "0"))

# --- Admin Identifier ---
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "0").strip()
ADMIN_ID = int(ADMIN_ID_RAW) if (ADMIN_ID_RAW and ADMIN_ID_RAW.lstrip("-").isdigit()) else 0

# --- Server Config ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://localhost:8080")

# --- User Storage Constants ---
PINNED_DB_TAG = "USER_DATA::"
PINNED_DB_WARNING = (
    "⚠️ DO NOT DELETE OR UNPIN - Ye aapka personal data hai. Delete karne par progress reset.\n\n"
)
DEFAULT_USER_DATA = {
    "completed_batches": [],
    "sent_lectures": [],
    "custom_group": None,
    "custom_topic": None,
    "custom_bot_token": None
}

# --- Queue Constants ---
QUEUE_DISPATCH_INTERVAL = 0.05  # 50ms per dispatch for high throughput
QUEUE_BUSY_THRESHOLD = 5         # backlog > 5 triggers generic student busy banner
RATE_LIMIT_PER_CHAT_MAX_RPM = 20 # Telegram strict per-chat limit (20 messages/minute)

# --- Force Subscribe (FSUB) Configuration ---
# Channel username (e.g. '@MyUpdatesChannel') or Chat ID (e.g. -1001234567890)
# Leave empty to disable force subscribe
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL", "").strip()
FORCE_SUB_INVITE_LINK = os.getenv("FORCE_SUB_INVITE_LINK", "").strip()

