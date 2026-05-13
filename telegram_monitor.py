import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)

# Канали для тривог (реальний час)
ALERT_CHANNELS = [
    "goodchernivtsi",
    "radar_chernivtsi",
]

# Канал для масованих атак
MASSIVE_ATTACK_CHANNELS = [
    "siriykardynal",
]

ALERT_KEYWORDS = [
    "тривога", "ракет", "шахед", "удар", "атака",
    "вибух", "дрон", "загроза", "відбій", "повітряна"
]

MASSIVE_KEYWORDS = [
    "масована атака", "масштабна атака", "бомбардувальник",
    "іскандер", "калібр", "кинджал", "балістич",
    "х-101", "ту-95", "ту-160", "до 50", "до 30"
]


class TelegramMonitor:
    def __init__(self, db, poster, ai):
        self.db     = db
        self.poster = poster
        self.ai     = ai
        self.client = None

    async def start(self):
        api_id   = int(os.environ.get("TELEGRAM_API_ID", 0))
        api_hash = os.environ.get("TELEGRAM_API_HASH", "")
        session  = os.environ.get("TELEGRAM_SESSION", "")  # StringSession

        if not api_id or not api_hash:
            logger.warning("TELEGRAM_API_ID/HASH not set — monitor disabled")
            return

        self.client = TelegramClient(
            StringSession(session) if session else StringSession(),
            api_id,
            api_hash
        )

        await self.client.start(bot_token=None)

        # Зберігаємо сесію в лог при першому запуску
        if not session:
            session_str = self.client.session.save()
            logger.info(f"TELEGRAM_SESSION (add to Railway vars):\n{session_str}")

        all_channels = ALERT_CHANNELS + MASSIVE_ATTACK_CHANNELS

        @self.client.on(events.NewMessage(chats=all_channels))
        async def handler(event):
            await self._handle_message(event)

        logger.info(f"Telegram monitor started, watching: {all_channels}")
        await self.client.run_until_disconnected()

    async def _handle_message(self, event):
        try:
            msg   = event.message
            text  = (msg.message or "").lower()
            url   = f"tg://msg?id={msg.id}"
            chat  = await event.get_chat()
            channel_name = getattr(chat, 'username', '') or ''

            # Перевірка на свіжість (останні 10 хвилин)
            if datetime.now(timezone.utc) - msg.date > timedelta(minutes=10):
                return

            is_alert   = channel_name in ALERT_CHANNELS
            is_massive = channel_name in MASSIVE_ATTACK_CHANNELS

            matched = False
            if is_alert and any(kw in text for kw in ALERT_KEYWORDS):
                matched = True
            if is_massive and any(kw in text for kw in MASSIVE_KEYWORDS):
                matched = True

            if not matched:
                return

            # Унікальний ключ для дедублікації
            unique_url = f"tg://{channel_name}/{msg.id}"
            if self.db.is_published(unique_url):
                return

            # Формуємо пост через AI
            article = {
                "title":     msg.message[:100] if msg.message else "Термінове повідомлення",
                "summary":   msg.message or "",
                "url":       unique_url,
                "source":    f"t.me/{channel_name}",
                "image_url": None,
            }

            formatted = self.ai.format_post(article)
            if not formatted:
                return

            msg_id = self.poster.send_post(
                text=formatted["text"],
                parse_mode=formatted.get("parse_mode", "HTML"),
            )
            if msg_id:
                self.db.mark_published(unique_url, msg_id, "urgent")
                logger.info(f"Alert posted from {channel_name}: {msg.message[:60]}")

        except Exception as e:
            logger.error(f"Telegram monitor handler error: {e}")


def run_monitor(db, poster, ai):
    """Запускає монітор в окремому event loop."""
    monitor = TelegramMonitor(db, poster, ai)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(monitor.start())
    except Exception as e:
        logger.error(f"Monitor stopped: {e}")
    finally:
        loop.close()
