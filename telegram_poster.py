import requests
import logging
import config

logger = logging.getLogger(__name__)

BASE_URL = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"

class TelegramPoster:

    def send_message(self, text: str, parse_mode: str = "HTML",
                     reply_to: int = None) -> int | None:
        """Надсилає повідомлення в канал. Повертає message_id або None."""
        payload = {
            "chat_id":    config.TELEGRAM_CHANNEL_ID,
            "text":       text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }
        if reply_to:
            payload["reply_to_message_id"] = reply_to

        try:
            r = requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=15)
            data = r.json()
            if data.get("ok"):
                msg_id = data["result"]["message_id"]
                logger.info(f"Sent message {msg_id}")
                return msg_id
            else:
                logger.error(f"Telegram error: {data}")
                return None
        except Exception as e:
            logger.error(f"send_message exception: {e}")
            return None

    def send_photo(self, image_url: str, caption: str,
                   parse_mode: str = "HTML", reply_to: int = None) -> int | None:
        """Надсилає фото з підписом. При помилці — відправляє текстом."""
        payload = {
            "chat_id":    config.TELEGRAM_CHANNEL_ID,
            "photo":      image_url,
            "caption":    caption[:1024],
            "parse_mode": parse_mode,
        }
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        try:
            r = requests.post(f"{BASE_URL}/sendPhoto", json=payload, timeout=20)
            data = r.json()
            if data.get("ok"):
                msg_id = data["result"]["message_id"]
                logger.info(f"Sent photo {msg_id}")
                return msg_id
            # Telegram не зміг завантажити картинку — падаємо на текст
            logger.warning(f"Photo failed: {data.get('description')} — sending as text")
            return self.send_message(caption, parse_mode, reply_to)
        except Exception as e:
            logger.error(f"send_photo exception: {e}")
            return self.send_message(caption, parse_mode, reply_to)

    def send_post(self, text: str, image_url: str = None,
                  parse_mode: str = "HTML", reply_to: int = None) -> int | None:
        """Універсальний метод: якщо є картинка — фото, якщо ні — текст."""
        if image_url:
            return self.send_photo(image_url, text, parse_mode, reply_to)
        return self.send_message(text, parse_mode, reply_to)

    def send_poll(self, question: str, options: list[str],
                  reply_to: int = None) -> int | None:
        """Надсилає опитування в канал."""
        payload = {
            "chat_id":    config.TELEGRAM_CHANNEL_ID,
            "question":   question[:300],
            "options":    [o[:100] for o in options[:10]],
            "is_anonymous": True,
        }
        if reply_to:
            payload["reply_to_message_id"] = reply_to

        try:
            r = requests.post(f"{BASE_URL}/sendPoll", json=payload, timeout=15)
            data = r.json()
            if data.get("ok"):
                msg_id = data["result"]["message_id"]
                logger.info(f"Sent poll {msg_id}")
                return msg_id
            else:
                logger.error(f"Telegram poll error: {data}")
                return None
        except Exception as e:
            logger.error(f"send_poll exception: {e}")
            return None
