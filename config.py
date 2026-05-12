import os

TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY")
FOOTBALL_API_KEY    = os.environ.get("FOOTBALL_API_KEY", "")

BUKOVYNA_TEAM_ID = 10385
UKRAINE_FIRST_LEAGUE_ID = 334

RSS_FEEDS = [
    "https://www.0372.ua/rss/news",
    "https://suspilne.media/rss/",
    "https://ukrinform.ua/rss/block-society",
    "https://www.epravda.com.ua/rss/",
    "https://tsn.ua/rss/full.rss",
    "https://www.rbc.ua/ukr/rss.xml",
    "https://mind.ua/rss",
    "https://www.ukrainealarm.com/rss",
    "https://suspilne.media/chernivtsi/rss/",
    "https://t.me/s/ppo_alert",

]

NEWS_FETCH_INTERVAL_MIN     = 10
FOOTBALL_CHECK_INTERVAL_MIN = 3
MORNING_DIGEST_TIME         = "08:00"
EVENING_DIGEST_TIME         = "20:00"
MAX_POSTS_PER_CYCLE = 1
MAX_POLLS_PER_DAY   = 2
