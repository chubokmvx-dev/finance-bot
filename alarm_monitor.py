import requests
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# alerts.in.ua — безкоштовний API без ключа
# Чернівецька область — ID 23
CHERNIVTSI_REGION_ID = 23
ALERTS_API_URL = "https://alerts.in.ua/api/alerts/active.json"

_last_alarm_state = None


class AlarmMonitor:
    def __init__(self, db, poster, ai):
        self.db     = db
        self.poster = poster
        self.ai     = ai

    def check(self):
        global _last_alarm_state

        try:
            r = requests.get(ALERTS_API_URL, timeout=10)
            if r.status_code != 200:
                logger.warning(f"Alarm API status: {r.status_code}")
                return

            data = r.json()
            alerts = data.get("alerts", [])

            # Шукаємо повітряну тривогу по Чернівецькій області
            air_alert = any(
                a.get("regionId") == CHERNIVTSI_REGION_ID and
                a.get("type") == "air"
                for a in alerts
            )

            current_state = "ALERT" if air_alert else "NO_ALERT"

            if current_state == _last_alarm_state:
                return

            prev_state = _last_alarm_state
            _last_alarm_state = current_state

            if prev_state is None:
                return  # перший запуск — не публікуємо

            if current_state == "ALERT":
                self._post_alert_start()
            else:
                self._post_alert_end()

        except Exception as e:
            logger.error(f"AlarmMonitor error: {e}")

    def _post_alert_start(self):
        text = (
            "<b>⚠️ ПОВІТРЯНА ТРИВОГА У ЧЕРНІВЕЦЬКІЙ ОБЛАСТІ</b>\n\n"
            "Чернівчани, увага! Оголошено повітряну тривогу.\n\n"
            "🔴 Негайно прямуйте до укриття\n"
            "📵 Зарядіть телефони та павербанки\n"
            "💡 Підготуйте ліхтарики\n"
            "🔇 Не ігноруйте сирену\n\n"
            "<a href=\"https://t.me/chernivtsi_now\">📢 Чернівці Now</a>"
        )
        unique_url = f"alarm://chernivtsi/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
        if not self.db.is_published(unique_url):
            msg_id = self.poster.send_message(text, parse_mode="HTML")
            if msg_id:
                self.db.mark_published(unique_url, msg_id, "urgent")
                logger.info("Air alert START posted")

    def _post_alert_end(self):
        text = (
            "<b>✅ Відбій тривоги у Чернівецькій області</b>\n\n"
            "Повітряна тривога скасована. Можна виходити з укриття.\n\n"
            "Залишайтесь обережними — слідкуйте за оновленнями.\n\n"
            "<a href=\"https://t.me/chernivtsi_now\">📢 Чернівці Now</a>"
        )
        unique_url = f"alarm_end://chernivtsi/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
        if not self.db.is_published(unique_url):
            msg_id = self.poster.send_message(text, parse_mode="HTML")
            if msg_id:
                self.db.mark_published(unique_url, msg_id, "urgent")
                logger.info("Air alert END posted")

