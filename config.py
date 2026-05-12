import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY")
FOOTBALL_API_KEY    = os.getenv("FOOTBALL_API_KEY")

# ─── Футбол ──────────────────────────────────────────────────────────────────
# Знайти правильний ID: зайди на https://dashboard.api-football.com/
# → Teams → пошук "Буковина" → скопіюй ID
BUKOVYNA_TEAM_ID = 10385   # ← уточни через API Dashboard

# Ukrainian First League (Перша ліга)
UKRAINE_FIRST_LEAGUE_ID = 334

# ─── RSS-джерела ─────────────────────────────────────────────────────────────
RSS_FEEDS = [
    # Чернівці
    "https://www.0372.ua/rss/news",
    "https://chernivtsi.online/feed/",
    # Загальноукраїнські
    "https://suspilne.media/rss/",
    "https://ukrinform.ua/rss/block-society",
    "https://www.epravda.com.ua/rss/",
    "https://tsn.ua/rss/full.rss",
    "https://www.rbc.ua/ukr/rss.xml",
    # Економіка / ціни
    "https://mind.ua/rss",
    "https://biz.liga.net/rss",
]

# ─── Розклад ─────────────────────────────────────────────────────────────────
NEWS_FETCH_INTERVAL_MIN     = 20   # перевіряти новини кожні N хвилин
FOOTBALL_CHECK_INTERVAL_MIN = 3    # під час матчу перевіряти кожні N хвилин
MORNING_DIGEST_TIME         = "08:00"
EVENING_DIGEST_TIME         = "20:00"

MAX_POSTS_PER_CYCLE = 2   # максимум постів за один цикл
MAX_POLLS_PER_DAY   = 2   # максимум опитувань на день
