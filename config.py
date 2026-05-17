import os

TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY")
FOOTBALL_API_KEY    = os.environ.get("FOOTBALL_API_KEY", "")

BUKOVYNA_TEAM_ID = 10385
UKRAINE_FIRST_LEAGUE_ID = 334

RSS_FEEDS = [
    "https://www.0372.ua/rss/news",
    "https://chernivtsi.online/feed/",
    "https://molbuk.ua/rss.xml",
    "https://cheline.com.ua/rss",
    "https://suspilne.media/chernivtsi/rss/",
    "https://suspilne.media/rss/",
    "https://ukrinform.ua/rss/block-society",
    "https://www.epravda.com.ua/rss/",
    "https://tsn.ua/rss/full.rss",
    "https://mind.ua/rss",
    "https://www.facebook.com/feeds/page.php?id=chernivcity&format=rss",
    "https://cv.npu.gov.ua/rss",          # поліція Чернівців  
    "https://cv.dsns.gov.ua/rss",          # ДСНС Чернівці
    "https://www.facebook.com/feeds/page.php?id=CVODAofficial&format=rss",
    "https://www.pravda.com.ua/rss/",
    "https://nv.ua/rss/all.xml",
    "https://hromadske.ua/rss",
    "https://zaxid.net/rss",              # захід України
    "https://www.google.com/alerts/feeds/05075569442616117815/6081417593725650416",
    "https://www.google.com/alerts/feeds/05075569442616117815/5242000540027592511",
    "https://www.google.com/alerts/feeds/05075569442616117815/8763462206768633624",
    "https://www.google.com/alerts/feeds/05075569442616117815/9002716388982372892",
    
]
URGENT_RSS_FEEDS = [
    "https://rsshub.app/telegram/channel/goodchernivtsi",
    "https://rsshub.app/telegram/channel/radar_chernivtsi",
]

MASSIVE_ATTACK_RSS_FEEDS = [
    "https://rsshub.app/telegram/channel/siriykardynal",
]



NEWS_FETCH_INTERVAL_MIN     = 15
FOOTBALL_CHECK_INTERVAL_MIN = 3
MORNING_DIGEST_TIME         = "08:00"
EVENING_DIGEST_TIME         = "20:00"
MAX_POSTS_PER_CYCLE = 1
MAX_POLLS_PER_DAY   = 2
