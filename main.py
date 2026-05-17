import schedule
import time
import logging
from datetime import datetime

from database import Database
from news_fetcher import NewsFetcher
from ai_processor import AIProcessor
from telegram_poster import TelegramPoster
from football_tracker import FootballTracker
from poll_manager import PollManager
from alarm_monitor import AlarmMonitor
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# ─── Ініціалізація ────────────────────────────────────────────────────────────
db       = Database()
fetcher  = NewsFetcher()
ai       = AIProcessor()
poster   = TelegramPoster()
football = FootballTracker()
polls    = PollManager(db, poster, ai)
alarm    = AlarmMonitor(db, poster, ai)

# ─── Флаги стану ─────────────────────────────────────────────────────────────
_football_tracking = False   # чи ведемо зараз live-трекінг матчу


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАДАЧІ
# ═══════════════════════════════════════════════════════════════════════════════

def task_fetch_news():
    """Основна задача: тягнемо новини, фільтруємо через AI, публікуємо."""
    logger.info("▶ task_fetch_news started")
    articles     = fetcher.fetch_all()
    new_articles = [a for a in articles if not db.is_published(a["url"])]

    if not new_articles:
        logger.info("No new articles")
        return

    logger.info(f"{len(new_articles)} new articles → AI filter")
    selected = ai.filter_and_rank(new_articles)

    posted = 0
    for article in selected:
        if posted >= config.MAX_POSTS_PER_CYCLE:
            break

        # Антидублі по змісту
        if db.is_similar_title(article.get("title", "")):
            logger.info(f"Duplicate content skipped: {article['title'][:50]}")
            continue

        formatted = ai.format_post(article)
        if not formatted:
            continue

        # Підтягуємо картинку (RSS або og:image зі сторінки)
        article = fetcher.enrich_with_image(article)

        msg_id = poster.send_post(
            text=formatted["text"],
            image_url=article.get("image_url"),
            parse_mode=formatted.get("parse_mode", "HTML"),
        )
        if msg_id:
            db.mark_published(article["url"], msg_id, article.get("category"), article.get("title"))
            posted += 1
            logger.info(f"Posted: {article['title'][:60]}")

            # Опитування (якщо є ідея та ліміт не вичерпано)
            poll_idea = article.get("poll_idea")
            if poll_idea and polls.should_post_poll():
                time.sleep(2)
                polls.post_poll(poll_idea, reply_to=msg_id)

        time.sleep(3)   # невелика пауза між постами

    logger.info(f"▶ task_fetch_news done: posted {posted}")


def task_football_live():
    """Перевіряємо рахунок live-матчу та публікуємо зміни."""
    global _football_tracking

    state = db.get_football_state()
    if not state:
        return  # немає анонсованого матчу

    match = football.get_live_match()
    if not match:
        # Перевіряємо чи матч завершився (статус FT)
        if _football_tracking:
            logger.info("Live match ended or not found")
            _football_tracking = False
        return

    _football_tracking = True
    current_score = f"{match['home_score']}-{match['away_score']}"

    if current_score != state["last_score"]:
        logger.info(f"Score changed: {state['last_score']} → {current_score}")
        formatted = ai.format_score_update(match)
        poster.send_message(
            formatted["text"],
            parse_mode=formatted.get("parse_mode", "HTML"),
            reply_to=state["announce_msg_id"],
        )
        db.update_football_score(current_score, match["status"])

    # Матч завершився
    if match["status"] in ("FT", "AET", "PEN"):
        logger.info("Match finished, clearing state")
        db.update_football_score(current_score, "FT")
        _football_tracking = False


def task_check_upcoming_match():
    """Щодня вранці перевіряємо чи є матч Буковини сьогодні/завтра і робимо анонс."""
    state = db.get_football_state()
    match = football.get_upcoming_match()

    if not match:
        return

    # Якщо вже анонсували цей матч — пропускаємо
    if state and state.get("match_id") == match["id"]:
        return

    logger.info(f"Announcing match: {match['home_team']} vs {match['away_team']}")
    formatted = ai.format_match_announcement(match)
    msg_id = poster.send_message(
        formatted["text"],
        parse_mode=formatted.get("parse_mode", "HTML"),
    )
    if msg_id:
        db.set_football_announce(match["id"], msg_id)
        # Одразу після анонсу — опитування "Хто виграє?"
        time.sleep(2)
        polls.post_match_poll(match["home_team"], match["away_team"], reply_to=msg_id)



# ═══════════════════════════════════════════════════════════════════════════════
# ДАЙДЖЕСТ / СТАТИСТИКА
# ═══════════════════════════════════════════════════════════════════════════════

def task_morning_digest():
    """Ранковий дайджест о 08:00 — топ новин за ніч."""
    if db.digest_sent_today():
        return

    posts = db.get_today_posts()
    if not posts:
        return

    lines = ["<b>🌅 Ранковий дайджест — Чернівці Now</b>\n"]
    for i, p in enumerate(posts[:5], 1):
        title = p["title"] or "Без назви"
        msg_id = p["message_id"]
        lines.append(f"{i}. <a href=\"https://t.me/chernivtsi_now/{msg_id}\">{title}</a>")

    lines.append("\n<a href=\"https://t.me/chernivtsi_now\">📢 Чернівці Now</a>")
    text = "\n".join(lines)

    msg_id = poster.send_message(text, parse_mode="HTML")
    if msg_id:
        db.mark_digest_sent()
        logger.info("Morning digest posted")


def task_weekly_stats():
    """Щонеділі о 18:00 — статистика тижня."""
    from datetime import datetime
    if datetime.now().weekday() != 6:  # тільки неділя
        return

    posts = db.get_week_top_posts()
    if not posts:
        return

    # Рахуємо категорії
    cats = {}
    for p in posts:
        c = p.get("category", "other") or "other"
        cats[c] = cats.get(c, 0) + 1

    cat_map = {
        "city": "🏙️ Місто", "sport": "⚽ Спорт",
        "utilities": "💡 Тарифи", "prices": "📈 Ціни",
        "national": "🇺🇦 Країна", "urgent": "⚠️ Терміново"
    }

    lines = ["<b>📊 Підсумки тижня — Чернівці Now</b>\n"]
    lines.append("Найпопулярніші теми:")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        label = cat_map.get(cat, cat)
        lines.append(f"  {label} — {count} постів")

    lines.append("\nТопові матеріали тижня:")
    for i, p in enumerate(posts[:3], 1):
        title = p["title"] or "Без назви"
        msg_id = p["message_id"]
        lines.append(f"{i}. <a href=\"https://t.me/chernivtsi_now/{msg_id}\">{title}</a>")

    lines.append("\n<a href=\"https://t.me/chernivtsi_now\">📢 Чернівці Now</a>")
    text = "\n".join(lines)

    msg_id = poster.send_message(text, parse_mode="HTML")
    if msg_id:
        logger.info("Weekly stats posted")


def setup_schedule():
    schedule.every(config.NEWS_FETCH_INTERVAL_MIN).minutes.do(task_fetch_news)
    schedule.every(config.FOOTBALL_CHECK_INTERVAL_MIN).minutes.do(task_football_live)
    schedule.every().day.at(config.MORNING_DIGEST_TIME).do(task_check_upcoming_match)
    schedule.every().day.at("13:00").do(task_check_upcoming_match)
    schedule.every(1).minutes.do(alarm.check)
    # Дайджест о 08:05 (після перевірки матчів)
    schedule.every().day.at("08:05").do(task_morning_digest)
    # Статистика щонеділі о 18:00
    schedule.every().day.at("18:00").do(task_weekly_stats)


def main():
    logger.info("═══ Chernivtsi Bot starting ═══")

    setup_schedule()

    task_fetch_news()
    task_check_upcoming_match()

    logger.info("Scheduler running. Ctrl+C to stop.")
    while True:
        try:
            schedule.run_pending()
            time.sleep(15)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Unhandled error in main loop: {e}", exc_info=True)
            time.sleep(60)


if __name__ == "__main__":
    main()
