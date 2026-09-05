import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)

LEGACY_DB_NAME = str(DATABASE_DIR / "jobs_database.db")
DB_NAME = str(BASE_DIR / "shadan_database.db")
DATABASE_URL = os.getenv("DATABASE_URL", "")

BOT_TOKEN = os.getenv("SHADAN_BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("SHADAN_ADMIN_ID", "0"))
ADMIN_GROUP_ID = int(os.getenv("SHADAN_ADMIN_GROUP_ID", "0"))
CHANNEL_USERNAME = os.getenv("SHADAN_CHANNEL_USERNAME", "@forsaaIQ")
SUBSCRIPTION_CHANNEL_USERNAME = os.getenv("SHADAN_SUBSCRIPTION_CHANNEL", CHANNEL_USERNAME)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

QI_MERCHANT_ID = os.getenv("QI_MERCHANT_ID", "")
QI_API_KEY = os.getenv("QI_API_KEY", "")
QI_BASE_URL = os.getenv("QI_BASE_URL", "https://backend.qi.iq/api/v1")
PUBLIC_BASE_URL = os.getenv(
    "SHADAN_PUBLIC_BASE_URL",
    os.getenv("RENDER_EXTERNAL_URL", "https://your-domain.com"),
)
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
BOT_USERNAME = os.getenv("SHADAN_BOT_USERNAME", "your_bot_username")
