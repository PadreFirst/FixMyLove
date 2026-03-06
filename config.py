import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "fixmylove")
ADMIN_USER_IDS: set[str] = {
    uid.strip() for uid in os.getenv("ADMIN_USER_ID", "").split(",") if uid.strip()
}
RESET_PHRASE = "##сброс"

DEBOUNCE_SECONDS = 3
SLIDING_WINDOW_SIZE = 15
SESSION_TIMEOUT_HOURS = 24
RATE_LIMIT_PER_HOUR = 30
RATE_LIMIT_BLOCK_MINUTES = 10
API_RETRY_ATTEMPTS = 3
API_RETRY_DELAYS = [2, 5]
SHADOW_PROFILE_MAX_SENTENCES = 10
SHADOW_PROFILE_COMPRESS_TO = 5

MODEL_FLASH_LITE = "gemini-2.5-flash-lite"
MODEL_FLASH = "gemini-2.5-flash"
MODEL_PRO = "gemini-2.5-pro"
