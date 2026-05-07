import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Threads
THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN")
THREADS_USER_ID = os.getenv("THREADS_USER_ID")
THREADS_API_BASE = "https://graph.threads.net/v1.0"

# Scheduling
POST_INTERVAL_HOURS = int(os.getenv("POST_INTERVAL_HOURS", "6"))
COMMENTS_CHECK_MINUTES = int(os.getenv("COMMENTS_CHECK_MINUTES", "5"))
