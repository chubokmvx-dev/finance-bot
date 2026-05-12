import schedule
import time
import logging
import os
print("ANTHROPIC KEY:", os.environ.get("ANTHROPIC_API_KEY", "NOT FOUND")[:10])
from datetime import datetime

from database import Database
from news_fetcher import NewsFetcher
from ai_processor import AIProcessor
from telegram_poster import TelegramPoster
from football_tracker import FootballTracker
from poll_manager import PollManager
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
            db.mark_published(article["url"], msg_id, article.get("category"))
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
# ПЛАНУВАЛЬНИК
# ═══════════════════════════════════════════════════════════════════════════════

def setup_schedule():
    # Новини кожні N хвилин
    schedule.every(config.NEWS_FETCH_INTERVAL_MIN).minutes.do(task_fetch_news)

    # Live-рахунок кожні N хвилин (якщо немає матчу — виклик безпечний і швидкий)
    schedule.every(config.FOOTBALL_CHECK_INTERVAL_MIN).minutes.do(task_football_live)

    # Перевірка анонсів матчів вранці та опівдні
    schedule.every().day.at(config.MORNING_DIGEST_TIME).do(task_check_upcoming_match)
    schedule.every().day.at("13:00").do(task_check_upcoming_match)


def main():
    logger.info("═══ Chernivtsi Bot starting ═══")

    setup_schedule()

    # Перший запуск одразу
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
            time.sleep(60)   # після помилки — пауза хвилину


if __name__ == "__main__":
    main()
