import logging
import random
import config
from database import Database
from telegram_poster import TelegramPoster
from ai_processor import AIProcessor

logger = logging.getLogger(__name__)

class PollManager:
    def __init__(self, db: Database, poster: TelegramPoster, ai: AIProcessor):
        self.db     = db
        self.poster = poster
        self.ai     = ai

    def should_post_poll(self) -> bool:
        """Чи можна ще публікувати опитування сьогодні?"""
        today_count = self.db.polls_today()
        if today_count >= config.MAX_POLLS_PER_DAY:
            return False
        # Додатковий рандом — не при кожній слушній нагоді (≈40%)
        return random.random() < 0.4

    def post_poll(self, topic: str, reply_to: int = None) -> int | None:
        """Генерує та публікує опитування."""
        poll_data = self.ai.generate_poll(topic)
        if not poll_data:
            return None

        msg_id = self.poster.send_poll(
            question=poll_data["question"],
            options=poll_data["options"],
            reply_to=reply_to,
        )
        if msg_id:
            self.db.save_poll(msg_id)
            logger.info(f"Poll posted: {poll_data['question']}")
        return msg_id

    def post_match_poll(self, home_team: str, away_team: str,
                        reply_to: int = None) -> int | None:
        """Опитування 'Хто виграє матч?' перед грою."""
        # Не рахуємо матчеві опитування в ліміт дня
        msg_id = self.poster.send_poll(
            question=f"Хто виграє матч?",
            options=[
                f"🏆 {home_team}",
                f"🤝 Нічия",
                f"⚔️ {away_team}",
            ],
            reply_to=reply_to,
        )
        if msg_id:
            self.db.save_poll(msg_id)
        return msg_id
